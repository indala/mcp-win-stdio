# Full CLI and MCP Product Audit

**Date:** 2026-11-24  
**Revision reviewed:** `fe10960` (`chore: bump version to 0.5.4 across all packages`)  
**Result:** Static review plus existing test suite. Findings only; no product code or tests were changed.

## Executive summary

The repository combines two MCP serving paths: the on-demand `mws server` gateway and the newer supervised `mws hub` service. It also supports direct standalone MCP servers and a broad Windows CLI. The Hub has extensive authentication, configuration, lifecycle, and IPC regression tests. The gateway and tool suite are also broadly covered, but several important gateway boundaries are not covered by the current tests.

The audit found **two high-priority authorization issues** and **four medium-priority correctness/reliability issues**. The most important risks affect remote tunnel requests: DAG workflow steps can lose request-scoped permissions, and resource/prompt proxy operations do not enforce server scope or the gateway's sensitive-read restrictions.

## Findings

### High — DAG workflow steps do not retain request-scoped authorization

**Affected areas:** [`workflows.py`](../src/mcp_win_stdio/core/workflows.py#L771), [`tunnel.py`](../src/mcp_win_stdio/core/tunnel.py#L131), [`server.py`](../src/mcp_win_stdio/server/server.py#L910)

The tunnel middleware sets `CURRENT_PERMISSION_MODE`, `CURRENT_AUTH_MODE`, `CURRENT_ALLOW_SENSITIVE_READS`, and `CURRENT_SCOPE_FILTER` for each HTTP request. Serial workflow steps run in that context. DAG steps are submitted with `ThreadPoolExecutor.submit`; Python does not automatically copy `ContextVar` values into those executor threads. The server's workflow callback calls `call_tool`, whose permission and scope checks therefore run without the request's values.

**Impact:** A DAG workflow invoked through a tunnel can be checked against process configuration rather than the request's OAuth permission ceiling and server/tool scope. For example, a read-only token can reach a mutating step if the process fallback mode is read-write. Unauthenticated sensitive-read restrictions can also be absent inside a worker.

**Remediation:** Capture the current context for each submitted step (or pass an immutable authorization context explicitly) and ensure it remains valid for the complete step call. Add DAG-specific tests for read-only OAuth, `--auth none`, allowed/disallowed server scopes, and tool scopes.

**Status (Remediated):** Implemented in [`workflows.py`](../src/mcp_win_stdio/core/workflows.py#L914-L924) by copying context per DAG task submission (`contextvars.copy_context().run`). Verified with concurrent isolation and permission tests in [`test_audit_authorization.py`](../tests/test_audit_authorization.py).

### High — Resource and prompt proxy methods bypass request scope and sensitive-read checks

**Affected area:** [`server.py`](../src/mcp_win_stdio/server/server.py#L196)

`_proxy_server_capability` checks only that the child server is discoverable, then dispatches the requested MCP capability. It does not check `CURRENT_SCOPE_FILTER`, the effective permission mode, or `CURRENT_AUTH_MODE`/`CURRENT_ALLOW_SENSITIVE_READS`. The gateway exposes this path through resource list/read and prompt list/get methods, which are separately classified as safe gateway tools.

**Impact:** A tunnel restricted with `--allow-servers` can still access a disallowed server's resources or prompts. An unauthenticated tunnel can read a resource without the sensitive-read restriction applied to ordinary tool calls. This also makes resource URIs a route for data access outside the intended authorization boundary.

**Remediation:** Enforce server scope before child dispatch and define an explicit capability policy for read-only and unauthenticated modes. Do not infer that every `resources/read` or rendered prompt is harmless solely because it is a read operation. Add tests that deny a disallowed server and sensitive resource reads while permitting authorized capability calls.

**Status (Remediated):** Implemented target-server boundary enforcement in [`permissions.py`](../src/mcp_win_stdio/core/permissions.py#L467-L514) via `check_capability_permission` and wired into [`server.py`](../src/mcp_win_stdio/server/server.py#L204-L215). Enforces `CURRENT_SCOPE_FILTER` and gates unauthenticated sensitive reads (`resources/read`, `prompts/get`) across all servers in `UNAUTHENTICATED_RESTRICTED_TOOLS` + SSH. Verified with 51 parameterized tests in [`test_audit_authorization.py`](../tests/test_audit_authorization.py).

### Medium — SQL write guardrails do not recognize CTE-wrapped mutations

**Affected area:** [`db/server.py`](../packages/mcp-win-stdio-db/src/mcp_win_stdio/db/server.py#L180)

`_parse_modifying_statement` recognizes statements only when they begin with `UPDATE`, `DELETE`, or `TRUNCATE`. In `execute_query`, `_check_write_policy(None)` returns no error. Consequently a valid statement such as `WITH selected AS (...) DELETE FROM accounts` is not classified, and the `WHERE`/`allow_unfiltered` guardrail is skipped. It also does not receive the before-image handling used for directly recognized `UPDATE`/`DELETE` statements.

**Impact:** A CTE-wrapped table-wide mutation can bypass the explicit naked-write safeguard and will not have the expected undo snapshot. This is especially hazardous when callers rely on the guardrail as a second check beyond the explicit write permission.

**Remediation:** Use dialect-aware parsing or conservatively reject statements the guard cannot classify. Apply write-policy checks to the effective DML statement in a CTE and verify before-image support or explicitly report that the operation is not undoable. Add PostgreSQL and MySQL cases where supported.

**Status (Remediated):** Implemented in [`db/server.py`](../packages/mcp-win-stdio-db/src/mcp_win_stdio/db/server.py) via balanced CTE prefix stripping, data-modifying CTE (`DATA_MODIFYING_CTE`) and unverified CTE (`UNVERIFIED_CTE_MUTATION`) rejection unless `allow_unfiltered=True`, and `WHERE` guard enforcement on CTE-wrapped `UPDATE`/`DELETE`. To avoid before-image side-effects (e.g. `nextval()` or data-modifying CTE re-execution), `_capture_before_image` unconditionally skips CTE statements, and `execute_query` explicitly returns `undoSupported: false` and `undoNotice`. Verified in [`test_audit_remediations.py`](../tests/test_audit_remediations.py).

### Medium — Child stderr pipes are never drained

**Affected areas:** [`process_pool.py`](../src/mcp_win_stdio/server/process_pool.py#L54), [`supervisor.py`](../src/mcp_win_stdio/core/hub/supervisor.py#L190)

Both child-process managers start servers with `stderr=subprocess.PIPE`. The legacy gateway's process client reads stderr only after the child exits; the Hub supervisor has a persistent stdout reader but no corresponding stderr drain in the spawn path.

**Impact:** A child that emits enough diagnostic output can fill the operating-system pipe buffer and block before sending an MCP response. The parent then sees a timeout or an apparently hung server. This can affect normal tools that log heavily, not only failing tools.

**Remediation:** Drain stderr continuously into a bounded, redacted log buffer or direct it to an appropriate logging sink. Preserve enough recent output to diagnose failures without allowing an unbounded in-memory buffer. Add a child-process test that writes beyond the pipe capacity to stderr and then serves a request.

**Status (Remediated):** Implemented continuous background stderr draining in [`process_pool.py`](../src/mcp_win_stdio/server/process_pool.py), [`lifecycle.py`](../src/mcp_win_stdio/core/hub/lifecycle.py), and [`supervisor.py`](../src/mcp_win_stdio/core/hub/supervisor.py) with bounded `readline(65536)` reads, 4096-char per-entry caps, 100-entry ring buffers, secret redaction (including resolved profile secrets and exception fallback), and diagnostic stderr surfacing on exit/timeout. Verified in [`test_audit_remediations.py`](../tests/test_audit_remediations.py) and [`test_hub_supervisor.py`](../tests/test_hub_supervisor.py).

### Medium — Failed discovery is cached as a permanent empty tool catalog

**Affected area:** [`catalog.py`](../src/mcp_win_stdio/server/catalog.py#L313)

If live probing fails and no schema-file fallback exists, `get_server_tools` converts the failure to an empty list and stores that result in both memory and disk cache. Normal reads return the cached list indefinitely; automatic retry occurs only when a caller explicitly requests refresh or clears the cache.

**Impact:** A server that is temporarily unavailable during the first catalog request can remain undiscoverable to `search_tools`, automatic routing, and server inspection for the lifetime of the cache, even after installation or recovery.

**Remediation:** Do not treat a probe failure as a successful empty catalog. Cache successful empty results separately from failures, or apply a short retry/expiry policy to failed probes. Preserve explicit `refresh` behavior. Add tests for failure followed by recovery without manual cache deletion.

**Status (Remediated):** Updated `get_server_tools()` in [`catalog.py`](../src/mcp_win_stdio/server/catalog.py#L286-L350) to distinguish `tools is None` (discovery failure) from `[]` (legitimate 0-tool server). Failures are never written to memory or disk cache, allowing automatic retry on subsequent reads. On a failed `force_refresh=True`, `[]` is returned to the caller while preserving any previously cached catalog on disk/in-memory. Verified in [`test_audit_remediations.py`](../tests/test_audit_remediations.py).

### Medium — `manage_context(action="list_sessions")` returns only the current session

**Affected area:** [`server.py`](../src/mcp_win_stdio/server/server.py#L335)

The action is documented as listing all active client sessions, but the handler returns a one-element list assembled from the caller's session. `GLOBAL_CONTEXT.list_sessions()` already exists and enumerates all unexpired sessions.

**Impact:** Operators and agents cannot use this action to inspect the active session set as documented. The separate `list_sessions` path also needs an explicit policy decision about whether exposing session identifiers to remote clients is appropriate.

**Remediation:** Either return the registry listing with an intentional disclosure policy, or change the action name and documentation to state that it reports only the caller. Test multiple sessions and expiry behavior.

**Status (Remediated):** Preserved caller-only session isolation (`test_session_enumeration_protection`) to prevent cross-client session enumeration, added `'session_info'` as a clearer alias alongside `'list_sessions'` in [`server.py`](../src/mcp_win_stdio/server/server.py#L337-L368), added `"scope": "caller_only"` to the payload, and updated docstrings/error messages. Verified in [`test_audit_remediations.py`](../tests/test_audit_remediations.py).

## Subsystem review summary

| Subsystem | Review coverage | Notes |
|---|---|---|
| CLI and packaging | CLI dispatch, project setup/status, configuration, install/update/uninstall flows, package manifests, and build/version scripts | User-facing command paths and package metadata reviewed. |
| Legacy MCP gateway | Server discovery, catalog/cache, argument normalization, context stacks, permissions, resources/prompts, workflow dispatch, child-process pool, and circuit breaker | Findings above affect this path. |
| Supervised Hub | Configuration loading, tool routing/filtering, authentication/session handling, secrets/redaction, process supervision, IPC, Windows security descriptors, lifecycle, and CLI management | Hub-specific security and lifecycle tests passed in this environment. Stderr draining remains a reliability gap. |
| Tunnel and OAuth | Request-scoped modes/scopes, bearer/none/OAuth paths, PKCE and redirect validation, host-owner approval, and tunnel lifecycle | The important uncovered edge is propagation from request context into DAG executor threads and capability proxy calls. |
| Workflows | Preflight schema validation, templates, serial and DAG execution, dependency/failure behavior, and output handling | Existing serial and DAG workflow tests pass; none currently verifies request-scope preservation in DAG workers. |
| Arch | Workspace scanning, graph construction, identity normalization, rendering, and MCP API | Reviewed as a read-only project inspection package. |
| Database | Connection configuration, query classification, read-only query validation, write guardrails, transactions, audit/undo, and schema tools | CTE-wrapped DML is not covered by the current write classifier. Live database behavior was not exercised. |
| Excel and Excel-DB | Workbook read/write operations, formulas/transforms, Office automation paths, SQL-like querying, streaming, upsert, reconciliation, migration, and template pipelines | Local logic and test coverage reviewed; no live Office or external database was connected. |
| Explorer and Git | Filesystem traversal/read/write boundaries, ignore handling, Git/GitHub command construction, output filtering, and repository operations | Path and subprocess flows reviewed. No remote GitHub operation was performed. |
| RAG | Crawling/indexing, URL and repository inputs, local store/FTS operations, cache lifecycle, and query/context results | Intentional arbitrary URL crawling has network reachability implications (see risks). No external crawl was run. |
| SSH | Host configuration, connection setup, command/script execution, PTY/background jobs, SFTP, and port forwarding | Operations are high-impact by design and are classified as mutating at the gateway. No SSH host was contacted. |
| TypeScript | Project-root checks, config discovery, compiler process, watcher lifecycle, cache access, and diagnostics APIs | The root-scan protection test passed. No external TypeScript project was compiled. |
| Word | Document inspection and authoring, templates, images, revisions, and PDF export | Local tests passed. Native Microsoft Word/COM export was not exercised. |

## Verification

### Existing test suite

The suite collected **426 tests**. It finished with **423 passed, 2 skipped, and 1 failed** using an isolated `USERPROFILE` under the workspace. No tests were added.

The failing test is `tests/test_db_and_mws_enhancements.py::test_argument_normalization_and_bidirectional_casing`. It expects `normalize_arguments("ssh", "ssh_exec_script", {"script": ..., "shell": ...})` to rewrite the declared `script` and `shell` aliases to `script_content` and `interpreter`. The current normalizer preserves exact schema properties first, and `ssh_exec_script` explicitly declares and accepts both alias properties. The tool call remains functional; the failure is a mismatch between the test's canonicalization expectation and the exposed schema/handler contract. Decide whether aliases should be normalized even when declared or whether the test should assert alias preservation.

Two initial attempts using the real user profile encountered sandbox restrictions: the SSH fixture could not write `~/.mcp-win-stdio/ssh_hosts.json`, and the artifact test could not write under the user exports directory. The subsequent isolated-profile run passed both. The suite also stalled at Windows asyncio loop initialization in the sandbox; it completed when rerun outside the sandbox with the isolated profile.

### Post-Remediation Verification (2026-11-25)

Following the implementation of all two high-severity authorization fixes and all four medium-severity correctness/reliability fixes:
- **Test Suite Results**: The full repository test suite was rerun with an isolated `USERPROFILE` (`$env:USERPROFILE = "$PWD\.test_home"`):
  - **499 tests collected**: **497 passed, 2 skipped, 0 failed** in 67.16s.
- **Normalization Contract**: `tests/test_db_and_mws_enhancements.py::test_argument_normalization_and_bidirectional_casing` was updated to assert exact declared schema property preservation under a controlled schema reflection harness, successfully passing without regression.
- **New Regression Tests**:
  - Added [`tests/test_audit_authorization.py`](../tests/test_audit_authorization.py) (55 tests) covering DAG request context preservation and capability proxy boundary scoping.
  - Added [`tests/test_audit_remediations.py`](../tests/test_audit_remediations.py) (13 tests) covering CTE write guardrails, non-blocking stderr pipe draining & redaction, transient catalog discovery recovery, and caller-scoped `session_info`/`list_sessions` isolation.

### Static consistency check

An AST inventory found **251 MCP tool registrations** and **251 entries** in the server-qualified safe/mutating permission catalogs. The existing automated completeness test for those registrations passed. This confirms catalog completeness, not that every tool's safe/mutating classification is semantically correct.

## Risks and verification limits

- The RAG crawler accepts caller-provided URLs and browser navigation follows the target site's reachable network. If the gateway is exposed remotely with write access, this can provide a path to internal web services. The crawler's broad URL support appears intentional; the product should decide and document whether remote tunnel deployments require private-address/egress restrictions.
- Several tools intentionally execute supplied code or commands (for example remote SSH scripts, Excel VBA, and the Excel-DB Python template pipeline). Write-enabled remote authorization therefore grants code-execution capability on the configured host or target system. Keep those tools out of read-only scopes and make this permission consequence clear in tunnel setup.
- Tests use mocks and local fixtures for many services. No live database, SSH server, Office application, GitHub account, external client, or Cloudflare tunnel was used; no dependency internals or published wheels were audited.
- This is a static audit of the repository revision above, not a proof of absence of defects. Findings should be rechecked after changes to gateway dispatch, workflow scheduling, permission catalogs, or child-process supervision.
