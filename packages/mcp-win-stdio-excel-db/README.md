# mcp-win-stdio-excel-db

High-Performance Power Pipeline MCP Server combining SQL Databases and Excel Spreadsheets.

## Features
* **Direct DB to Excel Streaming (`db_to_excel_stream`)**: Zero-context LLM token cost for massive queries.
* **Bulk Excel to DB Upsert (`excel_to_db_upsert`)**: Stream spreadsheets directly into database tables with type inference and chunking.
* **Cross-Source Join Engine (`query_unified_sources`)**: Run unified SQL joining SQL DB tables and `.xlsx` sheets in memory.
* **Reconciliation Auditor (`reconcile_db_vs_excel`)**: Identify data drift and discrepancies between database records and spreadsheets.
* **Template Populator (`db_to_excel_template`)**: Inject database query results into styled corporate Excel workbooks.
