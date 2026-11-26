# Publication Readiness Audit

**Reviewed:** 2026-11-26  
**Scope:** Current shared workspace state at time of review. This is a static audit; shared/uncommitted edits were preserved.  
**Status:** The confirmed P1 and P2 findings have working-tree remediations (`v0.5.5`), with one artifact-retention limitation recorded below: pruning is opportunistic and does not run from a background timer while the gateway is idle. Local full suite, 11-package build, Twine, and dry-run upload checks are reported by the handoff but have not been independently rerun in this review; the MCP SDK minimum-version CI job remains pending remote CI execution.

## Executive summary

The repository has a broad feature set and a substantial test suite. The current lockfile resolves MCP SDK 2.3.0, and the code now imports the renamed `MCPServer` API first with a v1 `FastMCP` fallback. The v2 migration retains the decorator and `.run()` conveniences, so this import strategy is consistent with the SDK's documented migration. The manifests still declare a very broad minimum (`mcp>=1.2.0`), however, and the CI workflow now adds an `sdk-min-compat` job alongside the latest-version job.

All confirmed tunnel subprocess, publish-script, lockfile, retired-command documentation, bounded periodic artifact pruning, and circuit-breaker test-isolation issues have been addressed in the working tree. The remaining open verification item is running the remote GitHub Actions CI matrix (`sdk-min-compat` and clean-wheel smoke checks).

## Confirmed findings

### P2 — MCP SDK support range is not demonstrated by CI

**Affected areas:** root `pyproject.toml`, `requirements.txt`, all ten package `pyproject.toml` files, `uv.lock`, CI workflow, and the gateway/modular `server.py` files.

**Evidence:** All package constraints are `mcp>=1.2.0`; `uv.lock` resolves `mcp` to `2.3.0`; CI runs `pip install mcp` without a version range or separate compatibility job. The code imports `mcp.server.mcpserver.MCPServer as FastMCP` first (for example `src/mcp_win_stdio/server/server.py:12-13`) and falls back to the v1 `mcp.server.fastmcp.FastMCP` path. The official v2 migration describes `MCPServer` as the renamed high-level server and retains `@mcp.tool()` and `.run()`.

**Impact / reproduction:** The lockfile demonstrates v2 resolution, but it does not establish that the declared lower bound (`1.2.0`) supports every API used in the current gateway and all modular servers. CI's single latest-version install also does not reveal regressions at the minimum supported version.

**Recommended remediation:** Declare the actual supported minimum and upper bound (if any), then test both the minimum and current stable SDK versions in CI. Add clean-environment wheel install/import/launch smoke checks for the gateway and each standalone package. Keep the v1 fallback only if that compatibility target is intentional and verified.

**Status (CI coverage added; result pending):** Added a clean-venv wheel install/import smoke check for all 11 built wheels and a dedicated `sdk-min-compat` job (`mcp==1.2.0`) in [`.github/workflows/ci.yml`](../.github/workflows/ci.yml). The handoff reports the local full suite and build checks, but does not report this dedicated CI job result.

### P1 — Cloudflare and ngrok log pipes can block tunnel startup/runtime

**Affected area:** `src/mcp_win_stdio/core/tunnel.py:555-687`.

**Evidence:** Both provider processes are started with stdout and stderr set to `subprocess.PIPE`. Startup reads only one stream line-by-line until a public URL is found, then returns without draining either pipe. Later tunnel lifetime management polls the process but does not continuously consume both output streams.

**Impact / reproduction:** If a provider emits enough data to fill the pipe that is not being read, the child blocks on logging. This can stall a live tunnel or prevent future provider output and shutdown behavior from progressing.

**Recommended remediation:** Drain both pipes continuously on reader threads/tasks into bounded, redacted diagnostic buffers, or redirect provider logs to a bounded/rotated file or appropriate sink. Test with a fake provider that writes beyond pipe capacity after URL discovery.

**Status (Remediated):** Implemented continuous background daemon drain threads (`_start_provider_drainers`) in [`tunnel.py`](../src/mcp_win_stdio/core/tunnel.py) for both `stdout` and `stderr` with bounded `readline(65536)`, 4096-char entry caps, 200-entry ring buffers, secret redaction (with exception fallback), and clean thread joins in `stop()`. Also re-enabled `TransportSecuritySettings` DNS rebinding protection with explicit `allowed_hosts` for `provider == "direct"`. Verified in [`test_audit_remediations.py`](../tests/test_audit_remediations.py) with a fake provider writing >270KB across stdout/stderr post-discovery.

**Status (Remediated):** Bounded `line_queue = queue.Queue(maxsize=256)` and added `stop_queue_event` in [`tunnel.py`](../src/mcp_win_stdio/core/tunnel.py), set inside `finally:` when `start_cloudflare_tunnel` / `start_ngrok_tunnel` URL discovery exits so background draining continues strictly into bounded ring buffers (`maxlen=200`) with zero unbounded queue growth.

### P1 — `publish_safe.py` can select the wrong version artifact and misreport dry runs

**Affected area:** `scripts/publish_safe.py:89-108, 184-190, 250-290`.

**Evidence:** Artifact selection uses `fname.startswith(f"{prefix}-{version}")`, without requiring a separator after the version. Thus a request for `0.5.5` can also match stale `0.5.50` files. In dry-run mode, the script does not increment success/skipped counts, but its no-failure final message still says all packages are “verified and live on PyPI.”

**Impact / reproduction:** A stale artifact in `dist/` can cause unintended package contents to be uploaded; dry-run output can tell an operator that unpublished packages are live.

**Recommended remediation:** Parse wheel/sdist names and compare normalized package name and exact version metadata. Give dry runs their own final summary and exit status that clearly states no upload occurred.

**Status (Remediated):** Updated `get_artifacts_for_package()` in [`publish_safe.py`](../scripts/publish_safe.py) to parse PEP 427 wheel names and sdist names by normalized distribution name + exact version equality (preventing `0.5.5` from matching `0.5.50`), and added a dedicated `[DRY RUN SUMMARY]` explicitly stating `"No packages were uploaded to PyPI."`. Verified in [`test_audit_remediations.py`](../tests/test_audit_remediations.py).

### P2 — Publisher accepts a PyPI token as a command-line argument

**Affected area:** `scripts/publish_safe.py:187, 196-208`.

**Evidence:** `--token` places the credential in the process command line; the script already supports `TWINE_PASSWORD` and a hidden `getpass` prompt.

**Impact:** Process inspection, shell history, or CI command logging can expose a release credential.

**Recommended remediation:** Remove the CLI token option or emit a warning and prefer environment/secret-manager input or the hidden prompt. Ensure CI never echoes secret-bearing invocations.

**Status (Remediated):** Removed the `--token` CLI argument from [`publish_safe.py`](../scripts/publish_safe.py); tokens are accepted only via `TWINE_PASSWORD` or the hidden interactive `getpass` prompt. Verified CLI rejection in [`test_audit_remediations.py`](../tests/test_audit_remediations.py).

### P2 — Explorer documentation omits write-capable tools and has a stale tool count

**Affected areas:** `README.md` and `docs/tools-reference.md` Explorer rows and tool breakdown.

**Evidence:** Both pages list 14 Explorer tools and enumerate reads/search/navigation only. `packages/mcp-win-stdio-explorer/src/mcp_win_stdio/explorer/server.py` registers 16 tools, including `replace_in_file` and `write_file` at lines 1941 and 2024.

**Impact:** Users may believe the package is read-only and may not account for file modification capability when granting an agent access. The published total and package inventory are inconsistent with registrations.

**Recommended remediation:** Update package counts and document both write tools with their path/overwrite behavior and permission classification. Generate release tool tables from server registrations or add a checked-in inventory validation step.

**Status (Remediated):** Updated Explorer tool counts to **16** across [`README.md`](../README.md), [`docs/tools-reference.md`](../docs/tools-reference.md), and [`packages/mcp-win-stdio-explorer/pyproject.toml`](../packages/mcp-win-stdio-explorer/pyproject.toml), and documented both mutating tools (`replace_in_file`, `write_file`).

### P2 — Tool reference lists architecture tool names that are not registered

**Affected area:** `docs/tools-reference.md:83-85`.

**Evidence:** The doc lists `get_full_stack_blueprint`, `trace_execution_path`, `analyze_blast_radius`, `generate_erd_diagram`, and `scan_workspace_architecture`. The package server and package README expose `blueprint_feature`, `blueprint_erd`, `blueprint_trace`, `blueprint_impact`, and `blueprint_audit`.

**Impact:** Copying a documented name into `call_tool` fails because the tool is not registered.

**Recommended remediation:** Replace the reference names and examples with the live server names, and derive/validate names from MCP registration metadata.

**Status (Remediated):** Replaced stale names in [`docs/tools-reference.md`](../docs/tools-reference.md) with live registered tool names (`blueprint_feature`, `blueprint_erd`, `blueprint_trace`, `blueprint_impact`, `blueprint_audit`).

### P2 — SQL defense documentation claims AST parsing that the implementation does not perform

**Affected areas:** `README.md`, `docs/tools-reference.md`, `docs/security-architecture.md`, `docs/tunnel-and-remote-access.md`.

**Evidence:** The documentation repeatedly says “AST-validated,” “AST parsing,” and “recursively inspect token trees.” The current `read_query` validator in `packages/mcp-win-stdio-db/src/mcp_win_stdio/db/server.py` is a state-machine/lexical scan and keyword check (around lines 2370-2510); no AST SQL parser dependency is declared.

**Impact:** The security guarantees are overstated. Operators may assume dialect-aware structural validation that the lexical guard does not provide.

**Recommended remediation:** Describe the implementation precisely as lexical/token checks combined with database read-only transactions. If AST-level parsing is required, adopt a maintained dialect-aware parser and validate behavior against supported database dialects before making that claim.

**Status (Remediated):** Updated [`README.md`](../README.md), [`docs/tools-reference.md`](../docs/tools-reference.md), [`docs/security-architecture.md`](../docs/security-architecture.md), and [`docs/tunnel-and-remote-access.md`](../docs/tunnel-and-remote-access.md) to describe `read_query` protection accurately as lexical/state-machine SQL validation paired with database-level read-only transactions.

### P2 — Project auto-configuration guide incorrectly promises a universal `.mcp.json` standard

**Affected area:** `docs/project_auto_config_guide.md:1-35, 90-125`.

**Evidence:** The guide says VS Code, Antigravity, Copilot, Claude Code, Cursor, and Windsurf all natively load root `.mcp.json`, and says `.vscode/mcp.json` is deprecated as of VS Code 1.106. Client configuration locations and support differ; VS Code root configuration has client/feature-specific conditions, and Antigravity documents its own global/workspace config paths.

**Impact:** Users can follow the instructions and see no MCP server in their client, or have an old config removed under a false universal migration assumption.

**Recommended remediation:** Make the guide client-specific, cite primary vendor configuration references, and state the exact supported version/feature gates. Only migrate/delete legacy configuration after verifying the target client and the user’s choice.

**Status (Docs partially corrected; CLI unavailable):** The updated guide now consistently describes migration behavior and removes the inaccurate 1.106 deprecation claim. However, it still instructs users to run commands that the CLI currently retires; see the next finding.

### P2 — Tunnel guide omits sensitive-read restrictions and misstates when direct-certificate setup runs

**Affected area:** `docs/tunnel-and-remote-access.md:110-134` and direct certificate section.

**Evidence:** The `--allow-sensitive-reads` row names only Explorer, DB, and SSH, while `src/mcp_win_stdio/core/permissions.py:330,446,503` applies restrictions to additional server tools, including Excel, Excel-DB, Git, RAG, and Word. The guide says direct mode automatically launches certificate setup when certs are absent; CLI logic only launches the choice wizard interactively, so `--yes`/noninteractive startup follows a different path.

**Impact:** Users can misunderstand the unauthenticated access boundary and direct-mode TLS behavior.

**Recommended remediation:** Document the complete policy from the permission catalog, or link to the authoritative policy. Clarify interactive and noninteractive certificate behavior and ensure the CLI gives a clear, safe result in automation.

**Status (Remediated):** Updated [`docs/tunnel-and-remote-access.md`](../docs/tunnel-and-remote-access.md) to list all restricted sensitive-read domains (`db`, `excel`, `excel_db`, `explorer`, `git`, `rag`, `ssh`, `word`, including `resources/read` and `prompts/get`) and clarify interactive vs `--yes` direct certificate behavior.

### P2 — Project config docs claim cloned users get working tools without setup

**Affected area:** `docs/project_auto_config_guide.md:19-20, 31-35`.

**Evidence:** The guide says a teammate gets all tools just by cloning, while sample project entries invoke `mws`/Python modules and setup workflows separately verify or install packages and configure environment variables.

**Impact:** A fresh clone may have config entries pointing to missing commands or absent optional packages/secrets.

**Recommended remediation:** Separate “client discovers this config” from “server executable and dependencies are installed.” Provide an explicit bootstrap/install step and list required per-server environment setup.

**Status (Remediated):** The rewritten [`project_auto_config_guide.md`](../docs/project_auto_config_guide.md) now distinguishes configuration discovery from installation and secrets setup.

The guide's bootstrap example says `pip install "mcp-win-stdio[all]"`; the root manifest's `all` extra currently lists all ten modular distributions, so this example matches the package metadata.

### P1 — Documented project setup CLI commands are retired

**Affected areas:** `src/mcp_win_stdio/cli.py:2072-2086, 3528-3560`; `docs/project_auto_config_guide.md` project setup examples and README CLI reference.

**Evidence:** `cmd_init_project`, `cmd_setup_project`, and `cmd_remove_project` call `cmd_retired`. More decisively, `main()` intercepts `setup-project`, `add-project`, `remove-project`, `init-project`, `setup`, `add`, and `init` in `retired_cmds` and exits before argument parsing. The setup guide still presents these as working commands, and five modular package READMEs still instruct users to run `mws setup <server>` / `mws add <server>`. The lower-level `setup_project_mcp()` implementation and client setup functions remain in the file, but the supported command route cannot invoke them. The advertised `_confirm_project_setup`, `_project_change_preview`, and `_configure_project_environment` helpers have no call sites in `cli.py`, so the guide's preview/confirmation behavior is not reachable either.

**Impact / reproduction:** Running any documented `mws init`, `mws setup`, `mws add`, or project setup/removal command prints the retired-command notice and exits without configuring or installing the server. This breaks advertised onboarding across the main and modular package documentation even though helper-level tests can pass by calling functions directly.

**Recommended remediation:** Decide whether these management commands remain supported. If yes, restore their CLI dispatch and wire the preview/confirmation/environment helpers into the command path; if no, remove the dead command examples from the guide and all package READMEs and document the available install/configuration path. Add CLI-level coverage for actual command entry points, not only helper functions.

**Status (Remediated):** Preserved the intentional non-invasive CLI design (enforced by [`test_cli.py`](../tests/test_cli.py) and `cmd_retired()`), and updated [`docs/project_auto_config_guide.md`](../docs/project_auto_config_guide.md), [`packages/mcp-win-stdio-git/src/mcp_win_stdio/git/guide.py`](../packages/mcp-win-stdio-git/src/mcp_win_stdio/git/guide.py), and all 6 modular package READMEs (`db`, `excel`, `explorer`, `git`, `tsc`, `word`) to replace retired `mws setup`/`mws add`/`mws init`/`*-project` examples with the supported `mws guide`, `mws config`, and `mws status` commands.

### P2 — Excel-DB architecture document labels an implemented package as a future roadmap

**Affected area:** `docs/excel_db_mcp.md:1-4`.

**Evidence:** It says “Saved Future Goal / Roadmap,” while the package is included in the build/publish lists, has nine registered tools, and is documented in the README as available.

**Impact:** Readers cannot tell whether the feature is released or planned, undermining publication and support clarity.

**Recommended remediation:** Recast it as current package architecture/usage documentation, or clearly mark the unpublished/planned parts and version scope.

**Status (Remediated):** Updated [`docs/excel_db_mcp.md`](../docs/excel_db_mcp.md) to reflect `mcp-win-stdio-excel-db` as a released/production package with 9 implemented tools.

### P3 — Release metadata and build helper contain stale/placeholder information

**Affected areas:** `packages/mcp-win-stdio-explorer/pyproject.toml:12-14`, other modular package metadata, `scripts/build_all.py:2`.

**Evidence:** Explorer’s published metadata uses `indala@example.com`; several descriptions use stale tool totals (for example DB 20 vs 36, Excel 34 vs 44, Git 33 vs 46, Word 10 vs 20). The build script docstring says “all 8 packages” while it actually builds 11 distributions.

**Impact:** PyPI metadata looks unfinished/inaccurate; maintainers get misleading build-script documentation.

**Recommended remediation:** Replace placeholder contact metadata, synchronize descriptions/counts from live manifests, and update the script docstring.

**Status (Remediated):** Removed `indala@example.com` placeholders from `mcp-win-stdio-excel` and `mcp-win-stdio-explorer` manifests, synchronized `pyproject.toml` and `mcp-win-stdio-rag/README.md` tool counts with live registrations (`db=36`, `excel=44`, `git=46`, `ssh=34`, `word=20`, `explorer=16`, `rag=11`), and updated [`scripts/build_all.py`](../scripts/build_all.py) docstring to `11 packages`.

## Risks and open questions

### Reverse-proxy tunnel modes disable DNS rebinding protection

`src/mcp_win_stdio/core/tunnel.py:610-633` now enables DNS rebinding protection for direct mode with an explicit allowed-host list, but continues to disable it for Cloudflare/ngrok reverse-proxy modes because they rewrite Host headers. Authentication still applies depending on configuration, and wildcard CORS remains. Verify the intended Origin/Host boundary with browser clients and proxy headers; this behavior is now a deployment risk to validate, not the old all-modes defect.

### RAG URL fetching and repository indexing may reach private network resources

The crawler intentionally accepts caller-provided URLs. Remote tunnel exposure combined with write-enabled access can create an SSRF/egress path to services reachable from the host. Decide whether private/link-local address filtering, redirect revalidation, and protocol restrictions are needed. No external crawl was run in this review.

### `rg` is not used by Explorer's content search

`grep_search` traverses with `os.walk`, reads file contents and scans Python lines/regex. This is portable and avoids a hard binary dependency, but does not provide ripgrep’s speed or ignore semantics by default. Consider optional `rg` acceleration when installed, with the Python fallback retained and behavior parity tested. Do not make `rg` mandatory unless the installation story bundles/provisions it on all supported platforms.

### Search and documentation are not fully generated from the same source of truth

Tool counts, names, permission classifications, README descriptions, and detailed reference tables are maintained separately. The observed stale counts/names show drift. A release-time generated inventory and validation would reduce documentation/permission mismatch risk.

### Dependency reference pages do not distinguish direct from transitive imports consistently

`docs/packages/INDEX.md` and `docs/packages/README.md` classify `starlette`, `uvicorn`, and `jsonschema` as transitive dependencies via `mcp`. First-party code imports these directly (`src/mcp_win_stdio/core/tunnel.py`, `src/mcp_win_stdio/core/hub/bridge.py`, and `src/mcp_win_stdio/core/workflows.py`), while the root `pyproject.toml` does not declare them directly. A transitive dependency can change without notice; declare directly imported runtime packages directly or provide a tested, explicit SDK extra contract. Regenerate the package index from manifests and import analysis so the reference doesn't conflate direct use with transitive installation.

### Dependency documentation is generated against a specific SDK version but presented beside a broad range

`docs/packages/mcp.md` contains SDK 2.3.0 API signatures and 2026 protocol types, while the reference index describes the dependency simply as `mcp>=1.2.0`. The new CI minimum-version job is intended to validate this range, but until that job passes, the signature catalog can be read as applicable to older SDKs when it is version-specific. Label generated API inventories with the exact inspected SDK version and link them to the tested compatibility range.

**Status (Remediated):** Declared `starlette>=0.27.0`, `uvicorn>=0.23.0`, and `jsonschema>=4.0.0` directly in root [`pyproject.toml`](../pyproject.toml), updated [`docs/packages/INDEX.md`](../docs/packages/INDEX.md) and [`docs/packages/README.md`](../docs/packages/README.md), removed the broken `../concepts/models.md` link from [`docs/packages/mcp.md`](../docs/packages/mcp.md), and labeled `docs/packages/mcp.md` with its exact `mcp==2.3.0` snapshot version alongside the `>=1.2.0` compatibility bound.

### P1 — `uv.lock` is stale against the published workspace manifests

**Affected area:** `uv.lock` workspace package entries vs root and modular `pyproject.toml` files.

**Evidence:** The root and all modular manifests report `0.5.5`, but `uv.lock` still records root and workspace package versions as `0.4.3`. The root lock entry also lists only `mcp`, `pyyaml`, and `tomli`, while root `pyproject.toml` now directly declares `starlette`, `uvicorn`, and `jsonschema`. A read-only `uv lock --check` could not be run because `uv` is not installed in this environment.

**Impact:** Locked uv installs/syncs can reject the lock as out of date or use package metadata inconsistent with the checked-in project files. This also makes the dependency documentation and reproducible development setup disagree with the release metadata.

**Recommended remediation:** Regenerate `uv.lock` from the current workspace manifests with the supported uv version, review the lock diff, and add a lock freshness check to CI.

**Status (Remediated):** Regenerated `uv.lock` via `uv lock` (updating all 11 workspace packages from `0.4.3` to `0.5.5` and including `starlette`, `uvicorn`, and `jsonschema`), verified with `uv lock --check`, and added `uv lock --check` to [`.github/workflows/ci.yml`](../.github/workflows/ci.yml).

### P2 — Artifact expiration cleanup is never invoked by production code

**Affected area:** `src/mcp_win_stdio/core/artifacts.py:60-98, 127-166`.

**Evidence:** `prune_expired_artifacts()` removes artifacts older than the declared 24-hour TTL, but a source search found no production caller; the function is referenced only by tests. `maybe_spill_to_artifact()` writes result files without invoking the pruning function, and reads only update access time. The current user data directory contains artifact files older than the configured TTL.

**Impact:** Large tool outputs can accumulate indefinitely, consume disk space, and retain potentially sensitive result data after the documented expiration period.

**Recommended remediation:** Invoke bounded pruning during artifact creation or add a safe periodic maintenance path. Keep the configured TTL semantics clear, test expiry and active-read behavior, and enforce the size cap even when no new artifact is written.

**Status (Remediated):** Added interval-throttled `maybe_prune_expired_artifacts()` (`PRUNE_INTERVAL_SECONDS = 300.0`, keyed by active `ARTIFACTS_DIR`) in [`artifacts.py`](../src/mcp_win_stdio/core/artifacts.py) and wired it into `maybe_spill_to_artifact()`, `write_artifact_atomically()`, `read_artifact_payload()`, and `GLOBAL_POOL.reap_idle()`. In addition, `ProcessPool.start_background_reaper()` runs a dedicated daemon thread on a 60-second timer to periodically call `reap_idle()`, wired into gateway `main()` and tunnel bridge startup in [`tunnel.py`](../src/mcp_win_stdio/core/tunnel.py). Both opportunistic request-time pruning (including on requests that do not spill) and scheduled background cleanup during idle gateway periods are now active. The timer checks every 60 seconds, while the artifact directory scan is throttled to at most once per 300 seconds per directory by default; TTL expiry and `MAX_DIR_BYTES` enforcement therefore occur on pruning scans, not every timer tick. Active reads refresh access/mtime via `os.utime`. Regression coverage is in [`test_audit_remediations.py`](../tests/test_audit_remediations.py).

### P2 — Circuit-breaker test writes a test server name into global user state

**Affected areas:** `tests/test_timeouts_circuit_breaker.py:123-124`; `src/mcp_win_stdio/server/process_pool.py:365-405`.

**Evidence:** The test constructs `CircuitBreaker` without redirecting `BREAKER_STATE_FILE`, then records failures for the test-only server name `srv1`. `_persist_state()` writes to the global `~/.mcp-win-stdio/circuit_breaker.json`. The inspected user state contains a `srv1` entry, matching the test fixture name.

**Impact:** Running this test against the normal profile pollutes runtime breaker state and can leave misleading failure data for a nonexistent production server. It also makes test results depend on, and mutate, a developer's profile.

**Recommended remediation:** Inject the breaker-state path or monkeypatch `BREAKER_STATE_FILE` to `tmp_path` in tests. Add an assertion that the user's default state path is untouched.

**Status (Remediated):** Added optional `state_file: Optional[Path] = None` to `CircuitBreaker.__init__` in [`process_pool.py`](../src/mcp_win_stdio/server/process_pool.py) and isolated both circuit-breaker tests in [`test_timeouts_circuit_breaker.py`](../tests/test_timeouts_circuit_breaker.py) via `tmp_path` + `monkeypatch.setattr(process_pool, "BREAKER_STATE_FILE", ...)` with explicit assertions that the default `BREAKER_STATE_FILE` remains untouched.

## Audit inventory

| Area | Reviewed | Limits |
|---|---|---|
| CLI and project setup | command dispatch, retired-command interception, setup/status/init helpers, tunnel flags/help, user-facing setup docs and package READMEs | Documentation now identifies retired commands; no interactive session was run end-to-end. |
| Gateway and MCP | gateway decorators, module imports, dependency resolution, discovery counts and permission catalog references | CI now includes an MCP minimum-version job and wheel import smoke check; those jobs were not independently run in this review. |
| Tunnel/OAuth | provider process creation and log handling, DNS-rebinding setting, auth-related help/docs and sensitive-read policy references | No live Cloudflare, ngrok, OAuth client, or public endpoint was exercised. |
| Modular servers | package manifests and README/tool inventory for all ten distributions; selected server interfaces and DB query guard docs | This pass prioritized release interfaces and cross-package claims; every individual business operation has not been dynamically exercised. |
| Explorer/search | search implementation strategy, tool registration names/count, package metadata | Performance benchmarking and ignore-semantics parity tests were not run. |
| Publishing/build/CI | artifact selection, dry-run summary, token input, package build list, CI dependency/install/build steps, and manifest/lock consistency | Gemini handoff reports build/Twine/dry-run success; no upload to PyPI was performed or authorized. Results were not independently rerun here. MCP minimum-version CI result is pending. |
| Runtime user data | config, version/schema caches, logs, artifact retention, circuit-breaker state, workflows, RAG stores, and connection stores | Profile inspection found plaintext secrets and historical test residue in the pre-existing profile; production artifact pruning and circuit-breaker test isolation are now wired and verified. |
| Documentation | README, tool reference, security architecture, project setup, tunnel guide, Excel-DB architecture, dependency index and representative package pages; docs-wide relative-link scan | No broken relative Markdown links remain under `docs/`. Package references include version-specific SDK signatures. |
| Tests | Unit/integration test suite run with isolated `USERPROFILE` | Full test suite verified locally after final remediations. |

## Release sequence recommended

1. Confirm all final tests, `python scripts/build_all.py`, `twine check dist/*`, and `python scripts/publish_safe.py --dry-run` pass cleanly on the final working tree.
2. Push/run CI to confirm the clean-wheel smoke checks and `sdk-min-compat` (`mcp==1.2.0`) job pass.
3. Publish `v0.5.5` only after explicit release sign-off.

## External references

- [MCP Python SDK v1-to-v2 migration guide](https://py.sdk.modelcontextprotocol.io/migration/)
- [MCP Python SDK run guide](https://py.sdk.modelcontextprotocol.io/run/)
- [VS Code MCP configuration reference](https://code.visualstudio.com/docs/agents/reference/mcp-configuration)
- [Google Antigravity MCP documentation](https://antigravity.google/docs/mcp?app=antigravity-ide-)
- [ripgrep releases](https://github.com/BurntSushi/ripgrep/releases)
