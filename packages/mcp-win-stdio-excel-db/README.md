# mcp-win-stdio-excel-db

High-Performance Power Pipeline Model Context Protocol (MCP) Server combining SQL Databases and Excel Spreadsheets: **9 tools** for high-volume streaming, in-memory cross-joins, and automated reconciliation.

Part of the **`mcp-win-stdio`** Windows-optimized suite.

---

## 🌟 Key Features (9 Tools)

* **Direct DB to Excel Streaming (`db_to_excel_stream`)**: Streams tens of thousands of database rows directly into styled `.xlsx` files without passing raw data through the LLM context window.
* **Bulk Excel to DB Upsert (`excel_to_db_upsert`)**: Ingests Excel spreadsheets into relational database tables with automatic type inference, chunking, and upsert conflict resolution.
* **Cross-Source Join Engine (`query_unified_sources`)**: Executes unified DuckDB SQL queries joining relational database tables and local `.xlsx`/`.csv` files in memory.
* **Reconciliation Auditor (`reconcile_db_vs_excel`)**: Detects discrepancies, missing rows, and value drift between database tables and business spreadsheets.
* **Master Dataset Comparer (`compare_master_datasets`)**: Deep schema and record-level structural diff between two master sources.
* **Master Migration Planner (`generate_master_migration_plan`)**: Generates verifiable SQL migration and rollback scripts to sync spreadsheet changes to production.
* **Sync Master to DB (`sync_master_to_db`)**: Executes staged migration plans in atomic database transactions.
* **Python Template Pipeline (`py_template_pipeline`)**: Runs deterministic Python/Pandas data pipeline transformations.
* **Template Populator (`db_to_excel_template`)**: Injects live database query results into pre-styled corporate Excel templates while preserving existing formulas, fonts, and borders.

---

## 🔐 Zero-Configuration & Dynamic Connection Sharing

`mcp-win-stdio-excel-db` requires **zero mandatory environment variables**. It automatically shares the dynamic database connections configured via `mws-db` or the `db` MCP server (`~/.mcp-win-stdio/db_connections.json`), supporting PostgreSQL, MySQL, SQLite, and SQL Server out of the box.

---

## 📦 Installation

```bash
# Standalone package installation:
pip install mcp-win-stdio-excel-db

# Or with full mcp-win-stdio suite:
pip install "mcp-win-stdio[all]"
```

---

## 🚀 Claude Setup

### Claude Desktop (`%APPDATA%\Claude\claude_desktop_config.json`)

```json
{
  "mcpServers": {
    "excel-db": {
      "command": "python",
      "args": ["-m", "mcp_win_stdio.excel_db"]
    }
  }
}
```

### Claude Code CLI

```bash
claude mcp add excel-db python -m mcp_win_stdio.excel_db
```

---

## 📜 License
MIT License. Copyright (c) 2026 Mohan Kumar Indala.
