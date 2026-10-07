# mcp-win-stdio-excel

Windows-native **Model Context Protocol (MCP)** server for Microsoft Excel: 44 tools combining high-speed Pandas querying, OpenPyXL bulk write & editing, native Excel Tables (`ListObject`), column/row structural mutations, cell merging, professional styling & conditional formatting, charts, data cleaning, transformations, RapidFuzz reconciliation, diff auditor, and native Windows Excel COM automation.

Part of the **`mcp-win-stdio`** Windows-optimized suite.

---

## 🚀 Features (44 Tools)

- **Native Excel Tables (`ListObject`)**: Create named, styled tables (`create_table`) with auto-filters and list all tables across sheets (`list_tables`).
- **Structural Row & Column Mutations**: Insert/delete columns with dynamic formula templates (`insert_column`, `delete_column`), insert/delete rows (`insert_rows`, `delete_rows`), and merge cell ranges (`merge_cells`).
- **Deterministic Workbook Diffing**: Compare two workbooks cell-by-cell or key-aligned with numeric tolerance (`diff_workbooks`).
- **Vectorized Data Queries**: High-speed Pandas slicing, filtering, and aggregation on large spreadsheets (`query_rows`, `query_excel_sql`).
- **Bulk 2D Matrix Writing**: High-efficiency table writes (`write_range`) with automatic leftover row cleanup (`clear_subsequent_rows=True`).
- **Professional Cell Styling & Layout**: Apply fonts, hex colors, fills, borders, text wrapping, and currency/percent/date formats (`format_cells`).
- **Dynamic Conditional Formatting**: Highlight threshold cells, duplicate/unique values, 2/3-color heatmap gradients, and formula rules (`apply_conditional_formatting`).
- **Sheet Layout & Panes**: Auto-fit column widths, freeze header panes, adjust row heights, and toggle gridlines (`set_sheet_layout_and_freeze`).
- **Chart Generation**: Native embedded Excel charts (Bar, Column, Line, Pie, Area) with custom titles, dimensions, and legends (`create_chart`).
- **Data Hygiene & Deduplication**: Automated string trimming, date normalization, blank stripping, and key deduplication (`clean_and_deduplicate_sheet`).
- **In-Memory Transforms & Grouping**: Pandas grouping, multi-column aggregations (`sum`, `mean`, `count`), filtering, and sorting (`transform_sheet_data`).
- **Typo-Tolerant Reconciliation**: Pre-flight key diagnostics (`analyze_reconciliation_keys`) and fuzzy joins (`reconcile_and_merge`) producing clean 3-tab audit workbooks (`Matched`, `Unmatched_Source`, `Unmatched_Target`).
- **OpenPyXL Direct Editing**: Safe cell updates with inline styling, row appending, multi-sheet management, broken formula audits (`audit_formulas`), search & replace (`search_and_replace_cells`), and CSV/JSON exports.
- **Native Windows Excel COM Automation**: Background/visible Excel process control, formula recalculation, pivot table refreshes, PDF export, and VBA macro execution.

---

## 🛠️ Included Tools (44 Tools)

* **Inspection**: `get_workbook_info`, `preview_sheet`, `get_column_values`, `compare_column_values`, `summarize_column`, `search_text`, `profile_sheet`, `list_tables`.
* **Structural & Tables**: `create_table`, `insert_column`, `delete_column`, `insert_rows`, `delete_rows`, `merge_cells`, `diff_workbooks`.
* **Querying & Slices**: `query_rows` (Pandas vectorized expressions), `read_range`, `query_excel_sql` (in-memory SQLite queries).
* **Editing & Export**: `create_workbook`, `append_rows`, `write_range` (bulk 2D write), `update_cells` (values + inline styles), `add_sheet`, `rename_sheet`, `delete_sheet`, `export_to_csv`, `export_to_json`, `audit_formulas`, `search_and_replace_cells`.
* **Styling & Layout**: `format_cells`, `apply_conditional_formatting`, `set_sheet_layout_and_freeze`.
* **Analysis & Copilot Tools**: `create_chart`, `clean_and_deduplicate_sheet`, `transform_sheet_data`.
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
