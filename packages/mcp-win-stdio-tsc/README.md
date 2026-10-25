# mcp-win-stdio-tsc

Windows-optimized **Model Context Protocol (MCP)** server for TypeScript diagnostics: persistent background compiler watchers (`tsc --watch`) maintaining an in-memory cache for **0ms latency** error inspection across multi-project and monorepo repositories.

Part of the **`mcp-win-stdio`** Windows-optimized suite.

---

## 🚀 Features (12 Tools)

- **Dynamic Zero-Env Project Hub**: Track and switch between multiple TypeScript projects dynamically using `list_projects`, `add_project`, and `use_project`. All settings are persisted to `~/.mcp-win-stdio/tsc_projects.json` with zero environment variables required.
- **0ms Diagnostic Cache**: Checks compilation errors instantaneously from memory without spawning slow CLI processes on each turn.
- **Actionable Fix Suggestions (`suggest_error_fixes`)**: Built-in intelligent fix engine for common TypeScript errors (nullish checks, type assertions, missing imports).
- **Categorized Error Breakdown (`get_error_category_breakdown`)**: Groups diagnostics by type, syntax, import/module, and declaration categories.
- **Multi-Project Auto-Discovery**: Automatically scans and watches all `tsconfig.json` configurations across project subdirectories.
- **Token-Safe Error Summaries**: Provides high-level error counts, affected files, and top error codes (e.g. `TS2322`) to avoid flooding Claude's context window.
- **Zero Admin / AppData Crawling**: Quarantines user profile roots (`C:\Users\admin`), `AppData`, and Windows system directories from unintended scans.

---

## 🛠️ Included Tools (12 Tools)

### Project & Watcher Management
1. `list_projects`: Lists all configured TypeScript workspace projects with live watcher status and active project indicator.
2. `use_project`: Sets the active workspace project for subsequent diagnostic queries.
3. `add_project`: Dynamically registers a TypeScript workspace directory and starts background watchers.
4. `remove_project`: Unregisters a project and stops its compiler watchers.
5. `list_watched_projects`: Lists all active `tsconfig.json` files and watcher worker statuses.
6. `watch_project`: Starts background compiler watchers for a specific directory or tsconfig file.
7. `restart_tsc_watcher`: Restarts compiler watchers and flushes the in-memory diagnostic cache.

### Diagnostic Inspection & Fixes
8. `get_tsc_errors`: Returns all active compilation errors from cache (supports project/tsconfig filters and limit).
9. `suggest_error_fixes`: Analyzes current errors and returns actionable code fix suggestions.
10. `get_error_category_breakdown`: Groups errors by category (Type Mismatch, Missing Property, Import/Export, Syntax).
11. `get_file_errors`: Checks diagnostics for a specific `.ts`, `.tsx`, `.js`, or `.jsx` file.
12. `get_error_summary`: Compact error counts per project and top 5 most common error codes.

---

## 📦 Installation

```powershell
pip install mcp-win-stdio-tsc
```
*(Installing this package automatically installs the `mws` CLI orchestrator)*.

---

## 🚀 One-Command Claude Setup

```powershell
mws setup tsc
# or:
mws add tsc
```

### Manual Configuration Example (Zero-Env)
In `%APPDATA%\Claude\claude_desktop_config.json`:
```json
{
  "mcpServers": {
    "tsc": {
      "command": "python",
      "args": ["-m", "mcp_win_stdio.tsc"]
    }
  }
}
```
*Note: Projects are managed dynamically with `add_project` and `use_project`. No environment variables required!*
