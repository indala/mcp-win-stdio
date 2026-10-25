# Security Policy & Safeguards

This document outlines the security architecture, threat models, safeguards, and reporting procedures for the **`mcp-win-stdio` (`mws`)** tool suite.

---

## 1. Security Architecture Principles

`mcp-win-stdio` is designed specifically for local execution on Windows environments where AI agents interface with system tools, databases, files, and remote servers. Its security architecture follows five core principles:

1. **Zero Secret Leakage in LLM Context**:
   - Connection strings, passwords, and SSH keys are stored persistently in user-owned local configuration (`~/.mcp-win-stdio/`) with Windows file ACLs.
   - Credentials are never injected into LLM system prompts or client configuration files (`claude_desktop_config.json`, `.mcp.json`).
   - Diagnostic listings mask sensitive credentials by default (e.g. hostnames and databases are visible, passwords are stripped).

2. **Defense-in-Depth for Destructive Operations**:
   - Operations that can result in irreversible data loss require explicit parameter confirmations (e.g., `drop_database` requires `confirmName` matching the exact database name).
   - DML/DDL operations in `execute_query` support transactional `dry_run` simulations.

3. **Context Overflow & Denial-of-Context Protection**:
   - High-volume data retrieval tools (`read_range`, `read_query`, `call_tool`) enforce maximum cell and character thresholds (`MAX_RESPONSE_CHARS = 120_000`).
   - Oversized outputs are truncated gracefully with structural notifications rather than exhausting the model's context window.

4. **Safe Process Isolation & No Shell Injections**:
   - Child processes spawned by the on-demand gateway (`mws server`) and subprocess runners (`git`, `ssh`, `tsc`) use explicit vector-argument execution (`subprocess.Popen([cmd, *args])`).
   - `shell=True` is strictly avoided to prevent shell metacharacter injection.

5. **Path Traversal & System Folder Quarantine**:
   - System root directories (`C:\`, `C:\Windows`, `System32`, `%APPDATA%`, `%TEMP%`) are strictly quarantined and prevented from automatic watcher scans or destructive operations.

---

## 2. Server-Specific Safeguards

### Database MCP (`db` & `excel-db`)
* **PII Redaction**: `get_table_sample` automatically detects and redacts columns matching known sensitive patterns (`password`, `token`, `secret`, `ssn`, `api_key`, `credit_card`, `hash`, `auth`) with `[REDACTED_SENSITIVE]`.
* **Administrative Confirmation**: `drop_database` rejects execution unless `confirmName` exactly matches the target database name.
* **Transaction Rollback**: `execute_query` supports `dry_run=True`, executing within a transaction and issuing a rollback before completion.
* **Polyglot Safety**: Parameterized queries via `psycopg2` and `pymysql` cursor parameter passing (`%s`) protect against SQL injection.

### TypeScript Watcher MCP (`tsc`)
* **System Directory Blocking**: `is_home_or_root_dir()` validates every project directory, actively rejecting system folders (`C:\`, user home root, Windows system directories, AppData) from auto-watching.
* **Process Isolation**: Every project watcher runs as an isolated background subprocess with strict process cleanup on exit (`atexit.register`).

### Workspace Explorer MCP (`explorer`)
* **Ignore Rule Enforcement**: Dynamically parses and honors `.gitignore`, preventing accidental indexing or retrieval of `.env`, secrets, `.git`, `node_modules`, and cached artifacts.
* **Token-Safe Collapsible Hierarchy**: Truncates massive subtrees into collapsed summaries to avoid token flooding.

### Multi-SSH MCP (`ssh`)
* **Key & Identity Resolution**: Auto-discovers standard `~/.ssh/config` configurations and private keys without exposing private key material to the LLM.
* **Channel Sandboxing**: PTY and command execution operate through standard Paramiko encrypted channels.

### On-Demand Gateway (`mws server`)
* **Process Pooling & Idle Reaping**: Child processes are managed by `ProcessPool` with an automatic 10-minute idle reaper, preventing orphaned processes, memory leaks, and lingering file locks.
* **Response Sanitization**: All proxy tool call results pass through `_format_result` to enforce response limits and structure safety.

---

## 3. Reporting a Vulnerability

If you discover a security vulnerability in `mcp-win-stdio`, please report it responsibly:

1. **Do not open a public issue.**
2. Send an email with details, reproduction steps, and potential impact to:
   **mohanindala@gmail.com**
3. You will receive an acknowledgment within 48 hours, followed by updates as the issue is triaged and patched.
