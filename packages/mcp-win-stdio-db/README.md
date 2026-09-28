# mcp-win-stdio-db

Unified Database Model Context Protocol (MCP) server for **PostgreSQL** and **MySQL** with multi-server in-memory pooling, sibling database auto-derivation, cross-schema resolution, and complete DBA operations.

Part of the **`mcp-win-stdio`** Windows-optimized suite.

---

## 🚀 Features (20 Tools)

- **Polyglot Database Engine**: Handles PostgreSQL (`psycopg2`) and MySQL (`pymysql`) transparently side-by-side.
- **In-Memory Connection Pooling**: Fast continuous queries with zero reconnection latency and persistent `use_database` sticky state.
- **Detailed Diagnostic Error Reporting**: Forwards native PostgreSQL error codes (e.g. 23503 FK violation), offending constraint names, column names, and error details directly to Claude so issues can be diagnosed immediately.
- **Sibling Database Auto-Derivation**: On PostgreSQL (`localhost:5432`), auto-discovers sibling databases (`showreel`, `dsr`, `location_booking`, `sap`, etc.) on the fly.
- **DBA & Management Tools**: `create_database`, `drop_database` (with safety guard), `clone_database` (instant template clone), `terminate_connections`, `list_active_queries`, `dump_database`, and `restore_database`.
- **Self-Contained `SERVERS` JSON**: Configure multiple database instances in one environment variable without external files.

---

## 🛠️ Included Tools (20 Tools)

1. `list_connections`: Lists all active and configured database connections.
2. `use_database`: Switches active connection or switches database on current server.
3. `list_databases`: Lists all databases on the active server.
4. `list_schemas`: Lists all schemas in the active PostgreSQL database.
5. `describe_table`: Detailed schema inspection (columns, nullability, PKs, FKs, indexes). Auto-resolves cross-schema tables in PostgreSQL.
6. `schema_overview`: Compact overview of all user tables and views.
7. `get_table_sample`: Returns sample rows and estimated row count.
8. `search_schema`: Case-insensitive regex search for table, view, or column names.
9. `read_query`: Safe SELECT queries returning structured JSON with row counts.
10. `execute_query`: Executes DML / DDL statements with transaction commit/rollback and detailed error forwarding.
11. `explain_query`: Generates EXPLAIN query execution plan.
12. `get_database_stats`: Table sizes, row estimates, index sizes, and total database size.
13. `add_connection`: Dynamically adds a new PostgreSQL or MySQL connection string at runtime.
14. `create_database`: Creates a new database on the active server.
15. `drop_database`: Safety-guarded DROP DATABASE (requires `confirmName` matching target name).
16. `clone_database`: Fast database cloning using PostgreSQL TEMPLATE mechanism.
17. `terminate_connections`: Terminates active connections to a specific database (PostgreSQL only).
18. `list_active_queries`: Lists running queries, connection duration, and process IDs.
19. `dump_database`: Dumps database to SQL file using native `pg_dump` or `mysqldump`.
20. `restore_database`: Restores database from SQL dump file using native `psql` or `mysql`.

---

## 📦 Installation

```powershell
pip install mcp-win-stdio-db
```
*(Installing this package automatically installs `mws` CLI orchestrator)*.

---

## 🚀 One-Command Claude Setup

```powershell
mws setup db
# or:
mws add db
```

### Manual Configuration Example
In `%APPDATA%\Claude\claude_desktop_config.json`:
```json
{
  "mcpServers": {
    "db": {
      "command": "python",
      "args": ["-m", "mcp_win_stdio.db"],
      "env": {
        "SERVERS": "{\"postgres\":\"postgresql://postgres:password@localhost:5432/mydb\",\"mysql\":\"mysql://user:pass@localhost:3306/mydb\"}"
      }
    }
  }
}
```

---

## 📖 CLI Commands & Interactive Guide

```powershell
mws db guide       # Complete tool reference & prompt recipes
mws db doctor      # Verify PostgreSQL/MySQL adapters and native dump tools
mws db setup       # Configure Claude Desktop / Claude Code
mws db run         # Launch server over stdio
```

---

## 📜 License
MIT License. Copyright (c) 2026 Mohan Kumar Indala.
