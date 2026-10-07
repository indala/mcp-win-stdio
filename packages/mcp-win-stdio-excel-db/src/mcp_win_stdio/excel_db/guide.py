"""
Interactive and printable guide for the Excel-DB High-Speed Pipeline MCP Server.
"""

EXCEL_DB_GUIDE = """
# ================================================================
# EXCEL-DB MCP (HIGH-SPEED PIPELINES & RECONCILIATION) - USER GUIDE
# ================================================================

The Excel-DB MCP server provides 9 specialized tools for zero-context streaming,
cross-source SQL queries, automated master dataset reconciliation, and transactional
database migrations between Microsoft Excel and relational databases (PostgreSQL, MySQL, SQLite).

----------------------------------------------------------------
1. TOOL SUMMARY (9 TOOLS)
----------------------------------------------------------------
* Streaming & Direct ETL:
  - db_to_excel_stream(sql_query, target_excel_path, ...):
    Directly streams database query results to an Excel file with chunking,
    optional table styling, and auto-fit column widths without loading rows into LLM context.
  - excel_to_db_upsert(excel_path, target_table, chunk_size, ...):
    Bulk streams Excel worksheet rows directly into a database table in chunks with append/replace modes.
  - db_to_excel_template(sql_query, template_excel_path, output_excel_path, ...):
    Injects query results into pre-styled Excel template workbooks, preserving charts, logos, and macros.

* Master Data Comparison & Audit:
  - compare_master_datasets(source_a, source_b, key_columns, column_mapping, tolerance, output_report_path):
    Deterministically compares two master datasets (Excel vs Excel, DB vs Excel, DB vs DB).
    Detects additions, removals, and field discrepancies with floating-point tolerance.
    Generates styled 4-tab Excel audit workbooks with KPI summary cards and cell diff highlights.
  - reconcile_db_vs_excel(sql_query, excel_path, key_columns, ...):
    Audits a live SQL database query against an Excel spreadsheet to spot missing records or discrepancies.

* Database Migration & Synchronization:
  - generate_master_migration_plan(excel_path, target_table, key_columns, column_mapping_json, fk_lookups_json, ...):
    Generates atomic, transactional PostgreSQL/MySQL migration SQL scripts from an Excel master.
    Includes pre-flight foreign key validation (resolving codes like 'ROL' to UUIDs against live DB) and UPSERT handling.
  - sync_master_to_db(excel_path, target_table, key_columns, column_mapping_json, fk_lookups_json, dry_run=True, ...):
    Executes master data synchronization against a live database with full transactional safety.
    Dry-run mode (default) simulates the entire migration and verifies all constraints without committing.

* Unified Analytics & Custom Python Pipelines:
  - query_unified_sources(pipeline_spec_json):
    Executes in-memory DuckDB/SQLite SQL queries across multiple heterogeneous sources (joining DB tables and Excel files).
  - py_template_pipeline(template_excel_path, output_excel_path, pipeline_spec_json):
    Executes custom Python/Pandas logic on multiple sources and writes resulting DataFrames into template sheets as styled tables.

----------------------------------------------------------------
2. BEST PRACTICES & LLM PROMPT RECIPES
----------------------------------------------------------------
* Reconciling Master Data:
  "Compare masters/NewCatalog.xlsx against showreel_dev database table props_management.materials,
   key on 'material_number', map 'SKU' -> 'material_number', and generate an audit report at reports/diff.xlsx."

* Safe Transactional Migration:
  "Run sync_master_to_db with dry_run=True first to verify foreign keys and check constraint violations.
   Only rerun with dry_run=False after inspecting the dry-run summary."

* Zero-Context Streaming for Large Datasets:
  "Never load 50,000 rows into prompt context. Always use db_to_excel_stream to pipe query results directly into Excel."
# ================================================================
"""


def print_excel_db_guide() -> None:
    """Print the formatted Excel-DB MCP guide to stdout."""
    print(EXCEL_DB_GUIDE.strip())
