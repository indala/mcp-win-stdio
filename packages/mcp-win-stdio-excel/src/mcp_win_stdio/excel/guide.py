"""
Interactive and printable guide for the Excel MCP server.
"""

EXCEL_GUIDE = """
# ================================================================
# EXCEL MCP (WINDOWS NATIVE + PANDAS) - USER & LLM GUIDE
# ================================================================

The Excel MCP server provides 44 specialized tools for programmatic
reading, updating, bulk writing, styling, formatting, native Excel Tables, row/col mutations,
chart generation, data hygiene, grouping/aggregation, fuzzy reconciling, and automating Excel workbooks on Windows.

----------------------------------------------------------------
1. TOOL SUMMARY (44 TOOLS)
----------------------------------------------------------------
* Read & Inspect:
  - get_workbook_info(file_path): Sheet names, dimensions, cell counts.
  - preview_sheet(file_path, sheet_name, max_rows): Fast preview.
  - query_rows(file_path, sheet_name, query_expr, columns): Pandas query.
  - read_range(file_path, sheet_name, range_address): Slices (e.g. A1:D50).
  - get_column_values(file_path, sheet_name, column_name): Distinct column values.
  - compare_column_values(file_path, sheet1, col1, sheet2, col2): Compare sets.
  - summarize_column(file_path, sheet_name, column_name): Statistics.
  - search_text(file_path, sheet_name, search_term): Keyword search.
  - profile_sheet(file_path, sheet_name): Data profiling and null audit.
  - query_excel_sql(file_path, query, sheet_name): In-memory SQLite queries.
  - list_tables(file_path, sheet_name): List all native Excel ListObjects with boundaries.

* Native Tables & Structural Mutations:
  - create_table(file_path, sheet_name, range_address, table_name, style): Convert range to native styled Table.
  - insert_column(file_path, sheet_name, col_idx, header, values, formula_template): Insert column with dynamic formulas.
  - delete_column(file_path, sheet_name, col_identifier): Delete column by index, letter, or header name.
  - insert_rows(file_path, sheet_name, row_idx, rows_data, num_rows): Insert blank or populated rows.
  - delete_rows(file_path, sheet_name, row_idx, count): Delete rows shifting data up.
  - merge_cells(file_path, sheet_name, range_address, value, alignment): Merge cell range with formatting.
  - diff_workbooks(wb1_path, wb2_path, ...): Cell-by-cell or key-aligned diff between two workbooks.

* Edit & Manage:
  - create_workbook(file_path, sheet_name, data): Create xlsx.
  - append_rows(file_path, sheet_name, rows): In-place fast row append.
  - write_range(file_path, data, start_cell, clear_subsequent_rows): Bulk 2D write.
  - update_cells(file_path, sheet_name, updates): Set values, formulas & styles.
  - add_sheet(file_path, sheet_name, title): Add new worksheet.
  - rename_sheet(file_path, old_name, new_name): Rename worksheet.
  - delete_sheet(file_path, sheet_name): Delete worksheet.
  - export_to_csv(file_path, sheet_name, output_csv_path): CSV export.
  - export_to_json(file_path, sheet_name, output_json_path): JSON export.
  - audit_formulas(file_path, sheet_name): Detect broken formulas (#REF!, #VALUE!).
  - search_and_replace_cells(file_path, search_val, replace_val): Batch replace.

* Styling & Layout:
  - format_cells(file_path, range_address, font, fill, border, alignment, number_format, batch_formats):
    Apply fonts, colors, solid fills, custom borders, text wrap/alignment, and currency/percent/date formats.
  - apply_conditional_formatting(file_path, range_address, rule_type, operator, formula, fill_color, font_color, color_scale_preset):
    Highlight thresholds, duplicate/unique values, 2/3-color heatmap gradients, or formula rules.
  - set_sheet_layout_and_freeze(file_path, column_widths, auto_fit_columns, row_heights, freeze_panes, show_grid_lines):
    Auto-fit column widths, freeze header panes (e.g. A2), adjust row heights, and toggle gridlines.

* Charts, Hygiene & Advanced Transforms:
  - create_chart(file_path, sheet_name, chart_type, data_range, title, categories_range, target_cell):
    Embed Bar/Column, Line, Pie, or Area charts directly into the sheet.
  - clean_and_deduplicate_sheet(file_path, sheet_name, deduplicate_by, trim_strings, normalize_dates, drop_blank_rows):
    Normalize dates, trim excess whitespace, remove duplicate records, and drop blanks.
  - transform_sheet_data(file_path, sheet_name, group_by, aggregations, query_filter, sort_by, output_sheet_name):
    Perform Pandas-powered group-by aggregations (sum, mean, count) and write results to a new summary sheet.

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
* Styling & Formatting:
  "Format the header row in financial_report.xlsx (A1:G1) with navy blue fill,
  bold white text, centered alignment, and freeze the top row."

* Conditional Formatting:
  "Apply a 3-color heatmap scale (red-yellow-green) to column E (Profit Margin)
  and highlight any cells with negative values in soft red."

* Auto-Fit & Layout:
  "Auto-fit all column widths in data.xlsx and freeze pane at B2."

* Charts & Data Cleaning:
  "Deduplicate the Customer_ID records in Sales.xlsx, normalize dates to ISO format,
  and create a Bar chart showing Total Revenue by Region in sheet Summary."

* In-Memory Transformations:
  "Group Transactions by Department, aggregate sum of Amount and count of ID,
  and output the summary to Department_Totals."

* Pre-flight Reconciliation:
  "Analyze the reconciliation keys between orders.xlsx (sheet: Sheet1,
  keys: PO_Number, Vendor) and sap_report.xlsx (sheet: PR_Data,
  keys: SAP_PO, Vendor_ID) and tell me match rate and fuzzy candidates."

* COM Automation:
  "Recalculate formulas in audit_result.xlsx and export it to PDF."
# ================================================================
"""

def print_excel_guide() -> None:
    print(EXCEL_GUIDE.strip())
