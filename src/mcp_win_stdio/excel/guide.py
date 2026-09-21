"""
User and LLM guide for mcp-win-stdio-excel.
"""

GUIDE_TEXT = """
# ================================================================
# MCP-WIN-STDIO-EXCEL: USER & LLM GUIDE (20 Tools)
# ================================================================

Provides 20 specialized tools for programmatic Excel automation on Windows:

1. WORKBOOK METADATA & STREAMING
   - get_workbook_info(file_path): Sheets, cell counts, dimensions.
   - preview_sheet(file_path, sheet_name, max_rows): Fast row-bounded preview.

2. VECTORIZED QUERY & SLICING
   - query_rows(file_path, sheet_name, query_expr, columns): Pandas query (e.g. `Amount > 5000 and Status == 'Pending'`).
   - read_range(file_path, sheet_name, range_address): Slice range (e.g. `A1:D25`).
   - summarize_column(file_path, sheet_name, column_name): Statistics (mean, sum, unique).
   - search_text(file_path, sheet_name, search_term): Keyword search across all cells.

3. WORKBOOK CREATION & EDITING
   - create_workbook(file_path, sheet_name, headers, initial_rows): Create formatted xlsx.
   - append_rows(file_path, sheet_name, rows): Fast in-place append.
   - update_cells(file_path, sheet_name, updates): Set values & formulas.
   - add_sheet(file_path, sheet_name, title): Create new worksheet.
   - rename_sheet(file_path, old_name, new_name): Rename worksheet.
   - delete_sheet(file_path, sheet_name): Delete worksheet.
   - export_to_csv(file_path, sheet_name, output_csv_path): Export sheet to CSV.

4. PRE-FLIGHT KEY ANALYSIS & RECONCILIATION
   - analyze_reconciliation_keys(wb1, s1, keys1, wb2, s2, keys2):
     Pre-flight audit: checks null counts, duplicate composite keys, overlap %,
     and candidate fuzzy matches BEFORE modifying any data.
   - reconcile_and_merge(wb1, s1, keys1, wb2, s2, keys2, output_wb, fuzzy_matching=True):
     Multi-column join with RapidFuzz similarity and automated 3-tab audit workbook:
     [1] Matched (exact + fuzzy with confidence % and variance)
     [2] Unmatched_Source_1
     [3] Unmatched_Source_2

5. NATIVE WINDOWS EXCEL AUTOMATION (COM / PyWin32)
   - recalculate_and_save(file_path): Forces native formula engine recalc.
   - export_to_pdf(file_path, output_pdf_path): Native high-res PDF export.
   - refresh_data_and_pivots(file_path): Refreshes PowerQuery connections & Pivot tables.
   - run_vba_macro(file_path, macro_name): Executes workbook VBA macros.
   - get_active_excel_window(): Inspects open Excel instances.

# ================================================================
"""

def print_guide() -> None:
    print(GUIDE_TEXT.strip())
