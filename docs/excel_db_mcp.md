# Architecture & Implementation Plan: `mcp-win-stdio-excel-db`

> **Status:** Saved Future Goal / Roadmap  
> **Target Package:** `packages/mcp-win-stdio-excel-db`  
> **Module Name:** `mcp_win_stdio.excel_db`

---

## 🎯 Overview

`mcp-win-stdio-excel-db` is an advanced **Power Engine** designed to sit alongside core `excel-mcp` and `db-mcp` servers. While basic MCP servers handle standard reading, writing, and schema viewing, `excel-db-mcp` focuses on **high-performance, zero-context-cost data pipelines, cross-source analytical joins, direct streaming, and automated reconciliation**.

---

## 🏗️ Core Architecture & Dependencies

### Python Dependencies
* `mcp>=1.2.0`
* `pandas>=2.0.0`
* `duckdb>=0.9.0` (High-performance in-memory SQL engine over `.xlsx`, `.csv`, `.parquet`, and SQL DB connections)
* `polars>=0.20.0`
* `sqlalchemy>=2.0.0`
* `openpyxl>=3.1.0`
* `xlsxwriter>=3.1.0`

---

## ⚡ Planned Tool Matrix

### 1. `db_to_excel_stream`
* **Purpose:** Directly stream database query results into Excel `.xlsx` files on disk.
* **Key Arguments:**
  * `connection_name` (str): Database connection ID.
  * `sql_query` (str): SQL SELECT statement.
  * `target_excel_path` (str): Target `.xlsx` file path.
  * `sheet_name` (str): Worksheet name.
  * `table_style` (str): Excel native table style (`TableStyleMedium9`).
* **Benefit:** 100% token savings — data stays on disk, only a 1-line summary is returned to the LLM.

### 2. `excel_to_db_upsert`
* **Purpose:** Parse an Excel sheet and bulk stream rows directly into a database table using chunked transactions.
* **Key Arguments:**
  * `excel_path` (str): Path to `.xlsx` file.
  * `sheet_name` (str | int): Sheet name or index.
  * `connection_name` (str): Target DB connection ID.
  * `target_table` (str): Database table name.
  * `if_exists` (str): `'append' | 'replace' | 'upsert'`.
  * `chunk_size` (int): Batch insert size (default: 1000).

### 3. `query_unified_sources` (Cross-Source Join Engine)
* **Purpose:** Run unified SQL queries spanning live SQL databases and Excel files using DuckDB.
* **Key Arguments:**
  * `sources` (list of dicts): References to database queries & Excel file paths.
  * `sql_query` (str): DuckDB cross-join query (e.g. `SELECT * FROM db_orders JOIN excel_vip ON ...`).
  * `export_target` (dict): Target file path or DB table.

### 4. `reconcile_db_vs_excel`
* **Purpose:** Compare a database query against an Excel spreadsheet and highlight row/cell differences.
* **Key Arguments:**
  * `db_query` (str) & `excel_path` (str).
  * `key_columns` (list of str): Primary keys to join on.
  * `output_report_path` (str): Path to write the diff report.

### 5. `db_to_excel_template`
* **Purpose:** Inject database query outputs into pre-designed Excel template files, preserving charts, pivot tables, and corporate styling.

---

## 📁 Package Layout in Monorepo

```
z:\projects\mcp-win-stdio\
├── packages\
│   └── mcp-win-stdio-excel-db\
│       ├── pyproject.toml
│       └── src\
│           └── mcp_win_stdio\
│               └── excel_db\
│                   ├── __init__.py
│                   ├── __main__.py
│                   ├── cli.py
│                   └── server.py
```

---

## 🚀 Execution & CLI Integration

```powershell
# Run Standalone
mws excel-db

# Run with All MCP Servers
mws all
```
