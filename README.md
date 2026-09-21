# mcp-win-stdio

Windows-optimized **Model Context Protocol (MCP)** suite and CLI orchestrator for local `stdio` execution with automated Claude Desktop & Claude Code CLI setup.

---

## 🌟 Highlights

* **Automated Claude Setup**: One command (`mcp-win-stdio setup`) auto-configures Claude Desktop (`claude_desktop_config.json`) and Claude Code CLI (`claude mcp add`) with zero manual JSON editing.
* **Modular Selection**: Install all servers or select individual modules (`excel`, `explorer`, or custom plugins).
* **Excel MCP (20 Tools)**: High-speed Pandas data queries, multi-column reconciliation with RapidFuzz, cell & formula editing, and native Windows Excel COM automation (PDF exports, recalculation, pivot refreshes, VBA macros).
* **Workspace Explorer MCP (11 Tools)**: Token-safe directory exploration, collapsible heavy folders (`node_modules`, `.next`, `.git`), dynamic `.gitignore` parsing, in-file grep, RapidFuzz fuzzy file search, and AST code outline extraction.
* **Extensible User Plugins**: Drop any standalone MCP Python script into `~/.mcp-win-stdio/plugins/` and it is immediately discovered, runnable, and configurable.

---

## 📦 Installation

Install base package (CLI + Explorer):
```powershell
pip install mcp-win-stdio
```

Or install with specific optional modules:
```powershell
# Excel MCP (Pandas + openpyxl + pywin32)
pip install "mcp-win-stdio[excel]"

# All modules & dependencies
pip install "mcp-win-stdio[all]"
```

For local development:
```powershell
git clone https://github.com/indala/mcp-win-stdio.git
cd mcp-win-stdio
pip install -e .
```

---

## 🚀 Quick Start

### 1. Run the Interactive Setup Wizard
```powershell
mcp-win-stdio setup
```
The wizard will prompt you:
```text
=== mcp-win-stdio Setup Wizard ===
Select which MCP servers you want to configure into Claude:
  [1] All servers (excel + explorer) [Recommended]
  [2] Excel MCP only (20 tools + COM automation)
  [3] Workspace Explorer MCP only (11 tools + smart ignore)
  [4] Exit
```

### 2. Or Install Individual Servers Directly
```powershell
# Configure only Excel MCP
mcp-win-stdio setup excel

# Configure only Workspace Explorer
mcp-win-stdio setup explorer

# Configure all servers
mcp-win-stdio setup all
```

---

## 📖 CLI Commands

| Command | Description |
| :--- | :--- |
| `mcp-win-stdio list` | Lists all available built-in servers and user plugins with tool counts. |
| `mcp-win-stdio setup [server]` | Auto-configures server(s) into Claude Desktop and Claude Code CLI. |
| `mcp-win-stdio remove <server>` | Safely removes server(s) from Claude Desktop and CLI configs. |
| `mcp-win-stdio guide <server>` | Prints complete tool reference, parameters, and prompt recipes for Claude. |
| `mcp-win-stdio run <server>` | Launches the MCP server over stdio (e.g. `mcp-win-stdio run excel`). |
| `mcp-win-stdio doctor` | Runs diagnostic health checks (Python, dependencies, Excel COM readiness). |

*(You can also use the shorthand alias `mws` instead of `mcp-win-stdio`)*.

---

## 🔌 Custom Plugins from Other PCs

Have custom MCP scripts (like TypeScript watchers, Word automators, or custom scrapers)?
Simply place your Python script into:
```text
%USERPROFILE%\.mcp-win-stdio\plugins\my_custom_mcp.py
```
`mcp-win-stdio` automatically detects it:
* View it in `mcp-win-stdio list`
* Run it via `mcp-win-stdio run my_custom_mcp`
* Add it to Claude via `mcp-win-stdio setup my_custom_mcp`

---

## 📜 License
MIT License. Copyright (c) 2026 indala.
