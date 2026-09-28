# mcp-win-stdio-explorer

Lightweight, token-safe **Model Context Protocol (MCP)** server for directory exploration, `.gitignore` resolution, in-file grep, RapidFuzz fuzzy search, and code symbol extraction.

Part of the **`mcp-win-stdio`** Windows-optimized suite.

---

## 🚀 Features (11 Tools)

- **Token-Safe Directory Navigation**: Depth-controlled tree (`get_directory_tree`) that automatically collapses heavy build directories (`node_modules`, `.next`, `dist`, `.git`) to protect LLM context windows.
- **Git-Wildmatch Pattern Engine**: Respects workspace `.gitignore` rules with high-performance `pathspec` matching.
- **Fast Content Search (Grep)**: Regex and plain-text search across file contents with surrounding context lines.
- **Typo-Tolerant Search**: RapidFuzz fuzzy search to locate files even with incomplete names or abbreviations.
- **Code Symbol Outlines**: Symbol extractor (`get_code_outline`) extracting classes, functions, arguments, docstrings, and line numbers from Python (AST) and JS/TS without loading entire files into memory.

---

## 🛠️ Included Tools (11 Tools)

1. `list_dir`: Detailed listing (PowerShell Get-ChildItem style) with file sizes, counts, and heavy folder indicators.
2. `get_directory_tree`: Depth-controlled tree with automatic heavy folder collapsing.
3. `find_files`: Advanced glob search honoring `.gitignore` and build caches.
4. `fuzzy_find`: RapidFuzz typo-tolerant file search.
5. `grep_search`: Fast text and regex search inside file contents with context lines.
6. `read_file`: Windowed file reader with line numbers and binary file safeguard.
7. `read_head_tail`: Quick top N (head) or bottom N (tail) line peek for logs and large files.
8. `get_code_outline`: Symbol extractor for Python AST and JavaScript/TypeScript symbols.
9. `get_file_info`: File metadata, line counts, line endings (CRLF vs LF), and hashes.
10. `workspace_summary`: Folder disk usage, extension breakdown, and Git repo status.
11. `export_tree_to_file`: Dumps an un-truncated workspace map directly to disk.

---

## 📦 Installation

```powershell
pip install mcp-win-stdio-explorer
```
*(Installing this package automatically installs `mws` CLI orchestrator)*.

---

## 🚀 One-Command Claude Setup

```powershell
mws setup explorer
# or:
mws add explorer
```

### Manual Configuration Example
In `%APPDATA%\Claude\claude_desktop_config.json`:
```json
{
  "mcpServers": {
    "explorer": {
      "command": "python",
      "args": ["-m", "mcp_win_stdio.explorer"]
    }
  }
}
```

---

## 📖 CLI Commands & Interactive Guide

```powershell
mws explorer guide     # Complete tool reference & prompt recipes
mws explorer doctor    # Verify pathspec and rapidfuzz dependencies
mws explorer setup     # Configure Claude Desktop / Claude Code
mws explorer run       # Launch server over stdio
```

---

## 📜 License
MIT License. Copyright (c) 2026 Mohan Kumar Indala.
