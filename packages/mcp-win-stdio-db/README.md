# mcp-win-stdio-db

Unified Database Model Context Protocol (MCP) server for **PostgreSQL** and **MySQL** with multi-server in-memory pooling, sibling database auto-derivation, cross-schema resolution, and complete DBA operations.

Part of the **`mcp-win-stdio`** Windows-optimized suite.

---

## 🚀 Features (31 Tools)

- **Polyglot Database Engine**: Handles PostgreSQL (`psycopg2`) and MySQL (`pymysql`) transparently side-by-side.
- **Entity-Relationship Diagrams (`generate_erd`)**: Generates clean GitHub/Mermaid markdown ER diagrams from foreign key metadata.
- **Row-Level Data Diffing (`diff_data`)**: Compares data across tables, schemas, or connections with column-by-column diffs.
- **Performance & Lock Auditing (`list_slow_queries`, `get_locks`)**: Real-time blocking dependency trees and slow query analysis (`pg_stat_statements` / `performance_schema`).
- **Streaming Export & Batch Import (`export_table`, `import_csv`)**: Streams tables/queries to CSV, JSON, or TSV on disk, and safely batch imports CSVs with transaction dry-run simulation.
- **Database Health & Schema Diff**: Unindexed foreign keys, unused indexes, bloated tables with recommended SQL fixes (`audit_database_health`, `compare_schemas`).
- **In-Memory Connection Pooling**: Fast continuous queries with zero reconnection latency and persistent `use_database` sticky state.
- **Detailed Diagnostic Error Reporting**: Native error codes (e.g. 23503 FK violation, 23505 unique violation), offending constraint names, and suggestions.
- **DBA & Management Tools**: `create_database`, `drop_database` (with safety guard), `clone_database` (instant template clone), `terminate_connections`, `dump_database`, and `restore_database`.

---

## 🛠️ Included Tools (31 Tools)

1. `list_connections`: Lists all active and configured database connections.
2. `use_database`: Switches active connection or switches database on current server.
3. `list_databases`: Lists all databases on the active server.
4. `list_schemas`: Lists all schemas in the active PostgreSQL database.
5. `describe_table`: Detailed schema inspection (columns, nullability, PKs, FKs, indexes). Auto-resolves cross-schema tables in PostgreSQL.
6. `schema_overview`: Compact overview of all user tables and views.
7. `compact_schema_overview`: Ultra-compact one-liner per table: schema.table (col: type PK, col2: FK->ref).
8. `get_table_sample`: Returns sample rows and estimated row count with PII masking.
9. `search_schema`: Case-insensitive regex search for table, view, or column names.
10. `get_table_ddl`: Complete CREATE TABLE DDL reconstruction.
11. `get_database_stats`: Table sizes, row estimates, index sizes, and total database size.
12. `read_query`: Safe SELECT queries returning structured JSON with row counts.
13. `execute_query`: Executes DML / DDL statements with transaction commit/rollback and `dry_run` support.
14. `explain_query`: Generates EXPLAIN / EXPLAIN ANALYZE execution plan.
15. `list_active_queries`: Lists running queries, connection duration, and process IDs.
16. `analyze_table_indexes`: Table index analysis: PKs, missing FK indexes, unused indexes.
17. `compare_schemas`: Schema diff between databases/schemas with generated migration SQL.
18. `audit_database_health`: Unindexed FKs, unused indexes, bloated tables with SQL fixes.
19. `generate_erd`: Entity-Relationship Diagram in GitHub/Mermaid markdown syntax from foreign keys.
20. `diff_data`: Row-level data comparison with field-level diffs and key matching.
21. `list_slow_queries`: Slow query analysis (`pg_stat_statements` / `performance_schema`).
22. `get_locks`: Real-time blocking dependency trees and lock distributions.
23. `export_table`: Streams table contents or SQL query results directly to CSV, JSON, or TSV on disk.
24. `import_csv`: Batch imports CSV file into table with transaction safety and dry-run rollback.
25. `add_connection`: Dynamically adds a new PostgreSQL or MySQL connection string at runtime.
26. `create_database`: Creates a new database on the active server.
27. `drop_database`: Safety-guarded DROP DATABASE (requires `confirmName` matching target name).
28. `clone_database`: Fast database cloning using PostgreSQL TEMPLATE mechanism.
29. `terminate_connections`: Terminates active connections to a specific database.
30. `dump_database`: Dumps database to SQL file using native `pg_dump` or `mysqldump`.
31. `restore_database`: Restores database from SQL dump file using native `psql` or `mysql`.

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
