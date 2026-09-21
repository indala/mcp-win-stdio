# mcp-win-stdio-explorer

Lightweight, token-safe **Model Context Protocol (MCP)** server for directory exploration, `.gitignore` resolution, in-file grep, RapidFuzz fuzzy search, and code symbol extraction.

---

## 📦 Installation

```powershell
pip install mcp-win-stdio-explorer
```
*(Pip also resolves `pip install mcp-win-stdio.explorer` to this package)*.

---

## 🚀 One-Command Claude Setup

```powershell
mcp-win-stdio-explorer setup
```
Automatically configures Claude Desktop (`claude_desktop_config.json`) and Claude Code CLI (`claude mcp add`).

---

## 🛠️ Included Tools (11 Tools)

* **Directory Navigation**: `list_dir` (PowerShell Get-ChildItem style), `get_directory_tree` (depth-controlled, collapses `node_modules`, `.git`, `.next`, `dist` to avoid token bloat)
* **Search**: `find_files` (advanced glob search), `fuzzy_find` (RapidFuzz typo-tolerant file search)
* **In-File Content Search**: `grep_search` (regex & text content search inside code with context lines)
* **Token-Safe Reading**: `read_file` (windowed line slicing, binary safeguard), `read_head_tail` (quick log peek)
* **Diagnostics & Outlines**: `get_code_outline` (Python AST & JS/TS symbol extractor), `get_file_info`, `workspace_summary`, `export_tree_to_file` (export map directly to disk)

---

## 📖 CLI Commands

```powershell
mcp-win-stdio-explorer setup    # Auto-add to Claude
mcp-win-stdio-explorer guide    # View prompts & tool guide
mcp-win-stdio-explorer doctor   # Verify dependencies
mcp-win-stdio-explorer run      # Run over stdio
mcp-win-stdio-explorer remove   # Remove from Claude
```
*(You can also use the shorthand alias `mws-explorer`)*.
