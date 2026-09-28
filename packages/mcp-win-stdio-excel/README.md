# mcp-win-stdio-excel

Windows-native **Model Context Protocol (MCP)** server for Microsoft Excel: 20 tools combining high-speed Pandas querying, RapidFuzz reconciliation, OpenPyXL editing, and native Windows Excel COM automation.

Part of the **`mcp-win-stdio`** Windows-optimized suite.

---

## 🚀 Features (20 Tools)

- **Vectorized Data Queries**: High-speed Pandas slicing, filtering, and aggregation on large spreadsheets.
- **Typo-Tolerant Reconciliation**: Pre-flight key diagnostics (`analyze_reconciliation_keys`) and fuzzy joins (`reconcile_and_merge`) producing clean 3-tab audit workbooks (`Matched`, `Unmatched_Source`, `Unmatched_Target`).
- **OpenPyXL Direct Editing**: Safe cell updates, row appending, multi-sheet management, formula insertion, CSV/JSON export.
- **Native Windows Excel COM Automation**: Background/visible Excel process control, formula recalculation, pivot table refreshes, PDF export, and VBA macro execution.

---

## 🛠️ Included Tools (20 Tools)

* **Inspection**: `get_workbook_info`, `preview_sheet`, `get_column_values`, `compare_column_values`, `summarize_column`, `search_text`.
* **Querying & Slices**: `query_rows` (Pandas vectorized expressions), `read_range`, `query_excel_sql`.
* **Editing & Export**: `create_workbook`, `append_rows`, `update_cells`, `add_sheet`, `rename_sheet`, `delete_sheet`, `export_to_csv`, `export_to_json`.
* **Reconciliation**: `analyze_reconciliation_keys`, `reconcile_and_merge`.
* **Windows COM Automation**: `recalculate_and_save`, `export_to_pdf`, `refresh_data_and_pivots`, `run_vba_macro`, `get_active_excel_window`.

---

## 📦 Installation

```powershell
pip install mcp-win-stdio-excel
```
*(Installing this package automatically installs `mws` CLI orchestrator)*.

---

## 🚀 One-Command Claude Setup

```powershell
mws setup excel
# or:
mws add excel
```

### Manual Configuration Example
In `%APPDATA%\Claude\claude_desktop_config.json`:
```json
{
  "mcpServers": {
    "excel": {
      "command": "python",
      "args": ["-m", "mcp_win_stdio.excel"]
    }
  }
}
```

---

## 📖 CLI Commands & Interactive Guide

```powershell
mws excel guide     # Complete tool reference & prompt recipes
mws excel doctor    # Verify Excel COM automation, Pandas, and OpenPyXL
mws excel setup     # Configure Claude Desktop / Claude Code
mws excel run       # Launch server over stdio
```

---

## 📜 License
MIT License. Copyright (c) 2026 Mohan Kumar Indala.
