# mcp-win-stdio

Windows-optimized **Model Context Protocol (MCP)** suite and interactive CLI hub for local `stdio` execution with transparent Claude Desktop & Claude Code CLI configuration.

---

## 🌟 Highlights

* **Interactive Terminal Hub (`mws`)**: Run `mws` alone to view all servers, live installation status (`[Installed]` vs `[Not Installed]`), and quick commands.
* **Safe, Transparent Setup (`mws setup <server>`)**: Installs missing dependencies on-demand, generates exact copy-pasteable JSON configuration for Claude Desktop and Claude Code CLI, and asks confirmation before making any automated edits (always creating `.bak` backups).
* **Excel MCP (20 Tools)**: High-speed Pandas data queries, multi-column reconciliation with RapidFuzz, cell & formula editing, and native Windows Excel COM automation (PDF exports, recalculation, pivot refreshes, VBA macros).
* **Word MCP (10 Tools)**: Multi-unit page layout geometry (margins in inches, cm, mm, pt), multi-column layout analysis, paragraph spacing/indentation, typography (fonts, sizes, hex colors), and floating/inline header image extraction.
* **Workspace Explorer MCP (11 Tools)**: Token-safe directory exploration, collapsible heavy folders (`node_modules`, `.next`, `.git`), dynamic `.gitignore` parsing, in-file regex grep, RapidFuzz fuzzy search, and Python/TypeScript AST outline extraction.
* **TypeScript Diagnostic Watcher MCP (6 Tools)**: Persistent background `tsc` compiler watchers maintaining an in-memory cache for instantaneous (0ms latency) error inspection across multi-tsconfig projects.
* **Extensible User Plugins**: Drop any standalone Python MCP script into `~/.mcp-win-stdio/plugins/` and it is immediately discovered, runnable, and configurable.

---

## 📦 Installation

Install base package (CLI Hub & Discovery Engine):
```powershell
pip install mcp-win-stdio
```

Or install with specific optional modules:
```powershell
# Excel MCP (Pandas + OpenPyXL + RapidFuzz + PyWin32)
pip install "mcp-win-stdio[excel]"

# Word MCP (Python-Docx + PyWin32)
pip install "mcp-win-stdio[word]"

# Explorer MCP (PathSpec + RapidFuzz)
pip install "mcp-win-stdio[explorer]"

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

### 1. Launch the Interactive Dashboard
```powershell
mws
```
Output:
```text
============================================================================
   🚀  mcp-win-stdio — Windows Model Context Protocol Suite (v0.1.0)
============================================================================
 Single-Source Hub:      C:\Users\User\.mcp-win-stdio
 Claude Desktop Config:  C:\Users\User\AppData\Roaming\Claude\claude_desktop_config.json
 Claude Code CLI Config: C:\Users\User\.claude.json
----------------------------------------------------------------------------
SERVER       STATUS           TOOLS    DESCRIPTION
----------------------------------------------------------------------------
excel        [Installed]      20       20 tools: Pandas queries, RapidFuzz...
word         [Installed]      10       10 tools: multi-unit margins (in, cm...
explorer     [Installed]      11       11 tools: token-safe collapsible tree...
tsc          [Installed]      6        6 tools: background tsc compiler...
----------------------------------------------------------------------------
 💡 Quick Commands:
   mws setup <server>    -> Install dependencies & show Claude config
   mws guide <server>    -> View complete tool reference & Claude prompts
   mws doctor            -> Run health checks (Office COM, Python, Node)
   mws run <server>      -> Launch MCP server over stdio
   mws list              -> List all servers and custom plugins
============================================================================
```

### 2. Configure a Server for Claude
```powershell
mws setup word
```
`mws` will verify dependencies, display the exact JSON block to add to Claude Desktop, show the CLI command for Claude Code, and offer safe automated application.

---

## 📖 CLI Commands

| Command | Description |
| :--- | :--- |
| `mws` | Displays interactive terminal home dashboard with server status and tips. |
| `mws list` | Lists all available built-in servers and user plugins with tool counts. |
| `mws setup [server]` | Guides setup, installs dependencies, and provides copy-pasteable Claude configurations. |
| `mws remove <server>` | Safely removes server(s) from Claude Desktop and CLI configs. |
| `mws guide <server>` | Prints complete tool reference, parameters, and prompt recipes for Claude (`excel`, `word`, `explorer`, `tsc`). |
| `mws doctor` | Runs diagnostic health checks (Python runtime, PyWin32 Excel/Word COM readiness, Node/tsc tools, Claude configs). |
| `mws run <server>` | Launches the MCP server over stdio (e.g. `mws run word` or `mws run tsc`). |

---

## 🛠️ Built-In MCP Servers (47 Tools)

### 📊 1. Excel MCP (`mcp_win_stdio.excel`) — 20 Tools
* **Fast Data Queries**: `query_sheet`, `filter_and_aggregate`, `export_filtered_data`
* **Fuzzy Reconciliation**: `reconcile_sheets`, `fuzzy_match_columns`
* **OpenPyXL Editing**: `read_cell_range`, `write_cells`, `append_rows`, `add_sheet`, `create_workbook`, `apply_formatting`, `insert_formula`
* **Native Windows Excel COM**: `open_excel_visible`, `close_excel_visible`, `recalculate_workbook`, `export_to_pdf`, `refresh_pivot_tables`, `run_vba_macro`

### 📝 2. Word MCP (`mcp_win_stdio.word`) — 10 Tools
* **Layout & Geometry**: `get_document_layout` (exact margins in inches, cm, mm, pt, paper format, multi-column analysis, section breaks)
* **Spacing & Indents**: `get_paragraph_spacing_and_indentation` (line spacing, space before/after in pt, first-line and hanging indents, pagination controls)
* **Typography**: `get_document_typography` (font family, font size in pt, hex colors `#002060`, highlights, paragraph alignments)
* **Visuals & Tables**: `get_document_images` (inline vs floating anchor images, placement offsets, dimensions), `get_document_tables`, `get_headers_and_footers`
* **Content & Search**: `read_word_document`, `search_word_document`, `get_document_outline`, `get_document_metadata`

### 📁 3. Workspace Explorer MCP (`mcp_win_stdio.explorer`) — 11 Tools
* **Token-Safe Exploration**: `get_workspace_tree`, `list_directory_safe` (collapses `node_modules`, `.next`, `dist`, `.git`)
* **Search & Filter**: `fuzzy_find_files` (RapidFuzz), `find_by_extension`, `grep_workspace`
* **Code Intelligence**: `get_code_outline` (Python & TypeScript AST symbol extractor), `search_definitions`
* **Safe File Operations**: `read_file_safe`, `get_file_stats`

### ⚡ 4. TypeScript Diagnostic Watcher MCP (`mcp_win_stdio.tsc`) — 6 Tools
* **Instant Diagnostic Query**: `get_tsc_errors` (0ms in-memory cache), `get_file_errors`, `get_error_summary`
* **Dynamic Project Control**: `list_watched_projects`, `watch_project(path)`, `restart_tsc_watcher`

---

## 🔌 Custom Plugins from Other PCs

Have custom MCP Python scripts?
Simply place your script into:
```text
%USERPROFILE%\.mcp-win-stdio\plugins\my_custom_mcp.py
```
`mcp-win-stdio` automatically discovers it:
* View it in `mws list`
* Run it via `mws run my_custom_mcp`
* Add it to Claude via `mws setup my_custom_mcp`

---

## 📜 License
MIT License. Copyright (c) 2026 Mohan Kumar Indala.
