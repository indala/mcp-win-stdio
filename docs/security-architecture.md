# Security Architecture & Defense-in-Depth

The `mcp-win-stdio` (`mws`) suite is built for Windows environments where local AI agents and remote LLMs interact directly with host tools, relational databases, filesystems, and development toolchains. Because agent-directed tools have access to real system resources, `mcp-win-stdio` implements a **multi-layered, fail-closed defense-in-depth architecture**.

---

## 🛡️ Core Security Tenets

1. **Fail-Closed by Default**: If an authentication check, permission lookup, SQL dialect analysis, or input parser hits an unexpected state or ambiguity, the operation is immediately denied with an informative error rather than proceeding.
2. **Context-Driven Permission Ceilings**: Permissions are enforced globally at the server entry point, refined per-session, and clamped dynamically at the request level via Python `ContextVar` (`CURRENT_PERMISSION_MODE`).
3. **Defense-in-Depth**: No single layer of defense is trusted on its own. For example, database query protection pairs an AST/lexical parser with database-level read-only transactions, engine-level session variables, and dialect isolation.

---

## 🧱 Defensive Layers Overview

```mermaid
flowchart TD
    Client["Client / AI Agent (Local stdio / Remote Tunnel)"] --> RateLimit["1. Token-Bucket Rate Limiter & IP Throttler"]
    RateLimit --> AuthLayer["2. Authentication Layer (OAuth PKCE / Bearer / Host PIN)"]
    AuthLayer --> ModeClamp["3. Permission Mode Clamping (min(server_mode, client_scope))"]
    ModeClamp --> Dispatcher["4. Tool Dispatcher & Route Guard"]
    
    subgraph Tool Guards
        Dispatcher --> MutCheck{"Mutating Tool?"}
        MutCheck -- Yes in Read-Only --> Blocked["403 Forbidden / Tool Blocked"]
        MutCheck -- No or Read-Write --> ExecTool["Tool Handler Execution"]
    end
    
    subgraph Database Sandbox (read_query)
        ExecTool --> SQLSanitize["5. Lexical & AST SQL Sanitizer"]
        SQLSanitize --> CommentCheck["Quote & Comment Balancing Guard"]
        CommentCheck --> TokenFSM["State Machine: Reject DDL, DML, CTE writes, side-effect funcs"]
        TokenFSM --> EngineTx["6. Database Engine Read-Only Transaction"]
        EngineTx --> DBExec["Execute Query in Read-Only Boundary"]
    end
```

---

## 1. OAuth 2.0 PKCE & Host-Owner Proof (Remote Tunnels)

When operating remote tunnels (`mws tunnel`), authentication enforces zero-trust boundaries:

### Host-Owner Proof (Approval PIN)
Because tunnel proxies (such as `cloudflared` or `ngrok`) forward incoming public traffic through a local loopback socket (`127.0.0.1`), naive checks for `client.host == "127.0.0.1"` would allow remote attackers to bypass authorization.
* **The Solution**: When `/oauth/authorize` is accessed, `mws` generates a cryptographically random, 6-digit approval PIN and prints it **strictly to the host operator's local terminal stdout**.
* The approval form (`POST /oauth/approve`) requires both this PIN and an origin-bound CSRF token to authorize the client.

### Dynamic Client Registration (RFC 7591) & Loopback Security (RFC 8252)
* Public clients (e.g. desktop AI agents, native CLIs) register via `POST /oauth/register`.
* Redirect URIs are validated against RFC 8252: loopback URIs (`http://127.0.0.1:<port>/...` and `http://localhost:<port>/...`) allow dynamic ephemeral ports while strictly rejecting non-loopback insecure HTTP schemes.
* Single-use authorization codes are atomically popped and burned upon exchange (`POST /oauth/token`). Replay attempts are instantly rejected.

### Token Verification & Revocation Poisoning Defense
* All issued tokens are signed using HMAC-SHA256 with an ephemeral 32-byte secret generated at server startup.
* When a revocation request (`POST /oauth/revoke`, RFC 7009) is received, the token's cryptographic signature is verified **before** adding its `jti` to the revoked token index. This prevents malicious actors from flooding the server with bogus identifiers to exhaust memory or evict legitimately revoked tokens.

---

## 2. Dynamic Permission Mode Clamping

Permission modes dictate what actions a client is allowed to perform:

| Mode | Allowed Capabilities | Blocked Capabilities |
| :--- | :--- | :--- |
| `read_only` | Safe inspection, reading files (`read_file`), querying database tables (`read_query`), viewing git logs/status/diffs, running non-destructive analysis. | File modifications (`write_file`, `edit_file`), SQL mutations (`execute_query`, DDL/DML), Git writes (`git_commit`, `git_push`), SSH command execution. |
| `read_write` | Full access to both read and mutating tools, subject to database connection permissions and OS file ACLs. | Operating outside configured directories or dropping database safety constraints. |

### Effective Mode Computation
When a request arrives at the tunnel or gateway, the server calculates:
$$\text{effective\_mode} = \min(\text{server\_mode}, \text{token\_scope})$$
This ensures that even if a token was granted `read_write` in a prior session, launching the server with `--mode read_only` unconditionally forces all operations into `read_only`.

---

## 3. SQL Injection & Read-Only Query Defense (`read_query`)

The `read_query` tool in `mcp-win-stdio-db` allows AI agents to run SQL queries while guaranteeing that no data modification, table dropping, administrative lock acquisition, or sleep-based denial-of-service can take place.

It employs a two-tier defense:

### Layer A: Lexical Tokenizer & State-Machine Parser
Before SQL is sent to the database driver, it is parsed by `_validate_readonly_sql`:

1. **Quote & Comment Differential Protection**:
   * Lexical scanners check that all single quotes (`'`), double quotes (`"`), MySQL backticks (``` ` ```), block comments (`/* ... */`), and PostgreSQL dollar quotes (`$tag$ ... $tag$`) are properly closed.
   * Unclosed delimiters trigger an immediate syntax rejection, neutralizing dialect-specific parser differential bypasses.
2. **Disallowed First Non-Comment Token**:
   * Only queries beginning with `SELECT`, `WITH`, or `EXPLAIN` are permitted.
   * Write statements (`INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER`, `TRUNCATE`, `REPLACE`, `MERGE`, `GRANT`, `REVOKE`, `CREATE`) are blocked outright.
3. **Data-Modifying CTE Detection**:
   * Common Table Expressions (`WITH ... AS (...)`) in PostgreSQL can wrap mutating statements (`WITH x AS (DELETE FROM ...) SELECT ...`). The parser inspects recursive token trees inside CTE blocks and blocks write operations.
4. **Dangerous Side-Effect Function Blocklist**:
   * Prohibits functions that could lock server processes or leak timing information, including:
     * MySQL: `GET_LOCK`, `RELEASE_LOCK`, `SLEEP`
     * PostgreSQL: `PG_SLEEP`, `PG_ADVISORY_LOCK`, `PG_TERMINATE_BACKEND`, `PG_CANCEL_BACKEND`

### Layer B: Database-Level Transaction Boundaries
Even if a novel SQL syntax bypass slips past the parser, the query is executed inside strict, driver-enforced read-only transaction envelopes:

* **PostgreSQL / CockroachDB**:
  ```sql
  BEGIN READ ONLY;
  -- Query execution here
  ROLLBACK;
  ```
  Postgres strictly aborts any attempt to execute DML or DDL inside a transaction marked `READ ONLY`.

* **MySQL / MariaDB**:
  ```sql
  START TRANSACTION READ ONLY;
  -- Fallback for legacy variants:
  -- SET TRANSACTION READ ONLY; START TRANSACTION;
  -- Query execution here
  ROLLBACK;
  ```
  If transaction-level read-only initialization fails, the execution **fails closed** and aborts immediately rather than running in an unconstrained read-write transaction.

---

## 4. Unauthenticated Tunnel Boundaries (`--auth none`)

In testing scenarios where authentication is explicitly disabled (`mws tunnel --auth none`), `mcp-win-stdio` applies severe perimeter restrictions to prevent data exfiltration:

* **Blocked Content Tools**:
  * `explorer.read_file`, `explorer.grep_search` (prevents sweeping regex scans for secrets/passwords).
  * `excel.preview_sheet`, `excel.query_rows` (prevents dumping spreadsheets containing PII or financial exports).
  * `rag.query_knowledge_base`, `rag.find_related_chunks`, `rag.get_chunk_context` (prevents leaking indexed document contents).
  * `git.git_log`, `git.gh_pr_diff`.
* **Permitted Metadata Tools**:
  * Unauthenticated callers may only invoke structural discovery metadata (e.g., `explorer.list_dir`, `db.describe_table`, `git.repo_overview`, `rag.get_knowledge_tree`).

---

## 5. Rate Limiting & Resource Exhaustion Protection

* **Token-Bucket Rate Limiter**: All tunnel endpoints are throttled to 60 requests per minute per IP. Bursts beyond bucket capacity return HTTP 429 (`Too Many Requests`).
* **Bounded In-Memory State**: Authorization codes, pending PKCE authorizations, and revoked tokens are held in bounded, time-pruned LRU data structures to prevent memory exhaustion under continuous traffic.
* **Stream & Output Pagination**: File reads, Git diffs, and query results enforce hard limits on returned row counts and byte sizes, preventing LLM context window crashes and buffer overflow.
