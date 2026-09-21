"""
Interactive and printable guide for the Excel MCP server.
"""

EXCEL_GUIDE = """
# ================================================================
# EXCEL MCP (WINDOWS NATIVE + PANDAS) - USER & LLM GUIDE
# ================================================================

The Excel MCP server provides 20 specialized tools for programmatic
reading, updating, querying, fuzzy reconciling, and automating Excel
workbooks on Windows.

----------------------------------------------------------------
1. TOOL SUMMARY
----------------------------------------------------------------
* Read & Inspect:
  - get_workbook_info(file_path): Sheet names, dimensions, cell counts.
  - preview_sheet(file_path, sheet_name, max_rows): Fast preview.
  - query_rows(file_path, sheet_name, query_expr, columns): Pandas query.
  - read_range(file_path, sheet_name, range_address): Slices (e.g. A1:D50).
  - summarize_column(file_path, sheet_name, column_name): Statistics.
  - search_text(file_path, sheet_name, search_term): Keyword search.

* Edit & Manage:
  - create_workbook(file_path, sheet_name, headers, initial_rows): Create xlsx.
  - append_rows(file_path, sheet_name, rows): In-place fast row append.
  - update_cells(file_path, sheet_name, updates): Set values & formulas.
  - add_sheet(file_path, sheet_name, title): Add new worksheet.
  - rename_sheet(file_path, old_name, new_name): Rename worksheet.
  - delete_sheet(file_path, sheet_name): Delete worksheet.
  - export_to_csv(file_path, sheet_name, output_csv_path): CSV export.

* Reconciliation & Audit:
  - analyze_reconciliation_keys(wb1, s1, keys1, wb2, s2, keys2):
    PRE-FLIGHT analysis. Checks nulls, duplicate keys, overlap %, and
    candidate fuzzy matches before any merging is performed!
  - reconcile_and_merge(wb1, s1, keys1, wb2, s2, keys2, output_wb, fuzzy_matching=True):
    Generates an automated 3-tab audit workbook:
    [1] Matched (exact + fuzzy with confidence scores & variance)
    [2] Unmatched_Source_1
    [3] Unmatched_Source_2

* Native Windows Excel COM Automation (Requires installed Excel):
  - recalculate_and_save(file_path): Forces formula engine calculation.
  - export_to_pdf(file_path, output_pdf_path): Native high-res PDF export.
  - refresh_data_and_pivots(file_path): Refreshes PowerQuery / Pivot tables.
  - run_vba_macro(file_path, macro_name): Executes workbook VBA macros.
  - get_active_excel_window(): Inspects open Excel instances.

----------------------------------------------------------------
2. EXAMPLE PROMPTS FOR CLAUDE
----------------------------------------------------------------
* Pre-flight Check:
  "Analyze the reconciliation keys between orders.xlsx (sheet: Sheet1,
  keys: PO_Number, Vendor) and sap_report.xlsx (sheet: PR_Data,
  keys: SAP_PO, Vendor_ID) and tell me match rate and fuzzy candidates."

* Reconcile:
  "Reconcile those workbooks into audit_result.xlsx with fuzzy matching
  enabled and show me the unmatched items."

* COM Automation:
  "Recalculate formulas in audit_result.xlsx and export it to PDF."
# ================================================================
"""

def print_excel_guide() -> None:
    print(EXCEL_GUIDE.strip())
