# mcp-win-stdio-tsc

Windows-optimized **Model Context Protocol (MCP)** server for TypeScript diagnostics: persistent background compiler watchers (`tsc --watch`) maintaining an in-memory cache for **0ms latency** error inspection across multi-project and monorepo repositories.

Part of the **`mcp-win-stdio`** Windows-optimized suite.

---

## 🚀 Features (6 Tools)

- **Zero Admin / AppData Crawling (Safe Standby Mode)**: If `TSC_WATCH_DIR` is not explicitly set, the server boots safely into standby mode. It never scans user profile roots (`C:\Users\admin`), `AppData`, or system directories.
- **Compiler Pre-Flight Check**: Checks for `tsc` availability (project `node_modules`, global `tsc`, or `npx tsc`) *before* scanning the filesystem, reporting clear installation guidance if missing.
- **0ms Diagnostic Cache**: Checks compilation errors instantly from memory without spawning slow CLI processes on each turn.
- **Multi-Project Auto-Discovery**: Automatically scans and watches all `tsconfig.json` configurations across project subdirectories.
- **Token-Safe Error Summaries**: Provides high-level error counts, affected files, and top error codes (e.g. `TS2322`) to avoid flooding Claude's context window.
- **Dynamic Watcher Management**: Add new projects on the fly (`watch_project`) or restart compiler workers without restarting the MCP server.

---

## 🛠️ Included Tools (6 Tools)

1. `get_tsc_errors`: Returns all active compilation errors from cache (supports project/tsconfig filters).
2. `get_file_errors`: Checks diagnostics for a specific `.ts`, `.tsx`, `.js`, or `.jsx` file.
3. `get_error_summary`: Compact error counts per project and top 5 most common error codes.
4. `list_watched_projects`: Lists all active `tsconfig.json` files and watcher statuses (or standby status).
5. `watch_project`: Dynamically verifies `tsc`, scans for `tsconfig.json`, and starts background watchers for a target project directory at runtime.
6. `restart_tsc_watcher`: Restarts compiler watchers and flushes the in-memory cache.

---

## 📦 Installation

```powershell
pip install mcp-win-stdio-tsc
```
*(Installing this package automatically installs `mws` CLI orchestrator)*.

---

## 🚀 One-Command Claude Setup

```powershell
mws setup tsc
# or:
mws add tsc
```

### Manual Configuration Example
In `%APPDATA%\Claude\claude_desktop_config.json`:
```json
{
  "mcpServers": {
    "tsc": {
      "command": "python",
      "args": ["-m", "mcp_win_stdio.tsc"],
      "env": {
        "TSC_WATCH_DIR": "C:/path/to/your/monorepo"
      }
    }
  }
}
```
> [!NOTE]
> If `TSC_WATCH_DIR` is omitted, the server starts in standby mode. You can tell Claude at any time:
> *"Watch the project located at 'D:/projects/my-web-app'"* and Claude will use `watch_project` to begin monitoring.

---

## 📖 CLI Commands & Interactive Guide

```powershell
mws tsc guide       # Complete tool reference & prompt recipes
mws tsc doctor      # Verify TypeScript compiler availability
mws tsc setup       # Configure Claude Desktop / Claude Code
mws tsc run         # Launch server over stdio
```

---

## 📜 License
MIT License. Copyright (c) 2026 Mohan Kumar Indala.
