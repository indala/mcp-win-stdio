# mcp-win-stdio-excel

Windows-native **Model Context Protocol (MCP)** server for Microsoft Excel automation, Pandas querying, fuzzy reconciliation, and COM automation.

---

## 📦 Installation

```powershell
pip install mcp-win-stdio-excel
```
*(Pip also resolves `pip install mcp-win-stdio.excel` to this package)*.

---

## 🚀 One-Command Claude Setup

```powershell
mcp-win-stdio-excel setup
```
Automatically configures Claude Desktop (`claude_desktop_config.json`) and Claude Code CLI (`claude mcp add`) with zero manual JSON editing.

---

## 🛠️ Included Tools (20 Tools)

* **Inspection**: `get_workbook_info`, `preview_sheet`, `summarize_column`, `search_text`
* **Querying & Slices**: `query_rows` (Pandas vectorized expressions), `read_range`
* **Editing**: `create_workbook`, `append_rows`, `update_cells`, `add_sheet`, `rename_sheet`, `delete_sheet`, `export_to_csv`
* **Pre-flight & Reconciliation**: `analyze_reconciliation_keys` (pre-flight diagnostics), `reconcile_and_merge` (RapidFuzz fuzzy joins + 3-tab audit workbook)
* **Native Windows COM**: `recalculate_and_save`, `export_to_pdf`, `refresh_data_and_pivots`, `run_vba_macro`, `get_active_excel_window`

---

## 📖 CLI Commands

```powershell
mcp-win-stdio-excel setup    # Auto-add to Claude
mcp-win-stdio-excel guide    # View prompts & tool guide
mcp-win-stdio-excel doctor   # Verify dependencies & Excel COM readiness
mcp-win-stdio-excel run      # Run over stdio
mcp-win-stdio-excel remove   # Remove from Claude
```
*(You can also use the shorthand alias `mws-excel`)*.
