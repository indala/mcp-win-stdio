# mcp-win-stdio-tsc

Windows-optimized **Model Context Protocol (MCP)** server for TypeScript diagnostics.

Runs persistent background compiler watchers (`tsc --watch`) with an in-memory cache for **0ms latency** error inspection across multi-project and monorepo repositories.

---

## 🌟 Features (6 Tools)

* **0ms In-Memory Cache**: `get_tsc_errors` (all active compiler errors across watched projects, with project/tsconfig filters)
* **File-Specific Diagnostics**: `get_file_errors` (strictly check errors for a specific `.ts`/`.tsx`/`.js`/`.jsx` file)
* **Token-Safe Summary**: `get_error_summary` (total error counts, project status, and top 5 most common error codes without flooding context)
* **Dynamic Multi-Project Control**: `list_watched_projects`, `watch_project(path)`, and `restart_tsc_watcher`

---

## 📦 Installation

```powershell
pip install mcp-win-stdio-tsc
```

---

## 🚀 Usage with Claude Desktop

Add to `%APPDATA%\Claude\claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "tsc": {
      "command": "python",
      "args": [
        "-m",
        "mcp_win_stdio.tsc"
      ]
    }
  }
}
```

---

## 📜 License
MIT License. Copyright (c) 2026 Mohan Kumar Indala.
