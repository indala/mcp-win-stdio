"""
Usage guide and prompt recipes for Database MCP server (mcp-win-stdio.db).
"""


def print_db_guide() -> None:
    guide_text = """
================================================================================
           Polyglot Database MCP Server (mcp-win-stdio.db)
================================================================================

Description:
  Unified Model Context Protocol server for PostgreSQL and MySQL databases.
  Supports cross-database switching, cross-schema auto-resolution, fast JSON queries,
  DBA administrative tools (safe DROP, CREATE, CLONE), native DUMP / RESTORE,
  DDL reconstruction, PII-safe sampling, database-wide health auditing, and
  schema diff with auto-generated migration SQL.

Server vs Connection vs Database Resolution:
  • Connection Aliases & Database Names are accepted interchangeably across all tools.
  • In SERVERS (e.g. {"showreel": "postgresql://...:5432/showreel"}), 'showreel' is
    both the registered connection alias and the database name.
  • All tools accept both 'connection' and 'server' parameters interchangeably.
  • 'use_database' switches to a connection alias (e.g. 'showreel'), a database name,
    or a sibling database on the active/specified server.

Available Tools (34 Tools):
--------------------------------------------------------------------------------
CONNECTION MANAGEMENT
1.  list_connections
    - Lists all active and configured database connections from ~/.mcp-win-stdio/db_connections.json.

2.  use_database
    - Switches active connection or switches database on current/specified server.
    - Args: database (str), server/connection (optional str), name (optional str)

3.  add_connection
    - Dynamically adds a new PostgreSQL or MySQL connection string at runtime and persists to ~/.mcp-win-stdio/db_connections.json.
    - Args: name (str), url (str), type (optional str), setActive (bool), test_connect (bool)

4.  edit_connection
    - Dynamically updates an existing connection URL, credentials, or alias name at runtime.
    - Args: name (str), new_url (optional str), new_name (optional str), type (optional str), setActive (optional bool), test_connect (bool)

5.  remove_connection
    - Removes a database connection from saved configuration.
    - Args: name (str)

6.  test_connection
    - Tests connectivity to an existing or ad-hoc database connection.
    - Args: name (optional str), url (optional str)

SCHEMA INSPECTION
7.  list_databases
    - Lists all databases on the active (or specified) server.
    - Args: connection/server (optional str)

8.  list_schemas
    - Lists all schemas in the active PostgreSQL database or table summary in MySQL.
    - Args: connection/server (optional str)

9.  describe_table
    - Full schema inspection: columns, data types, nullability, defaults, PKs,
      foreign keys, and indexes. Auto-resolves cross-schema tables in PostgreSQL.
    - Args: tableName (str), schema (optional str), connection/server (optional str)

10. schema_overview
    - Compact overview of all user tables and views with sizes and row counts.
    - Args: schema (optional str), connection/server (optional str), max_tables (int)

11. compact_schema_overview
    - Ultra-compact one-liner per table: schema.table (col: type PK, col2: FK->ref)
    - Ideal for large databases — fits entire schema in minimal tokens.
    - Args: schema (optional str), connection/server (optional str), max_tables (int)

12. get_table_ddl
    - Reconstructs the full CREATE TABLE DDL with column types, NOT NULL,
      defaults, all constraints (PK, FK, UNIQUE, CHECK), and extra indexes.
    - Args: tableName (str), schema (optional str), connection/server (optional str)

13. search_schema
    - Case-insensitive regex search for table, view, or column names.
    - Args: searchTerm (str), schema (optional str), max_results (int), connection/server (optional str)

DATA ACCESS
14. get_table_sample
    - Returns sample rows (default: 5) and estimated row count for quick inspection.
    - mask_sensitive=True (default) auto-redacts PII columns (password, token,
      secret, ssn, api_key, credit_card, etc.) as [REDACTED_SENSITIVE].
    - Args: tableName (str), limit (optional int), schema (optional str),
            mask_sensitive (optional bool, default: True), connection/server (optional str)

15. read_query
    - Safe SELECT queries returning structured JSON with row counts.
    - Args: sql (str), params (optional list), limit (optional int), max_cell_chars (int), connection/server (optional str)

16. execute_query
    - Executes DML / DDL statements (INSERT, UPDATE, DELETE, CREATE, ALTER) with
      transaction commit/rollback, batch statement progress, and affected row counts.
    - Args: sql (str), params (optional list), dry_run (optional bool), connection/server (optional str)

17. explain_query
    - Generates EXPLAIN query execution plan.
    - Args: sql (str), analyze (optional bool), connection/server (optional str)

DIAGNOSTICS & HEALTH
18. get_database_stats
    - Table size, row estimates, index sizes, active connections, cache hit ratio.
    - Args: connection/server (optional str)

19. list_active_queries
    - Lists running queries, connection duration, and process IDs.
    - Args: database (optional str), server/connection (optional str)

20. audit_database_health
    - Database-wide health audit (PostgreSQL only). Returns three categories:
        • unindexed_foreign_keys: FK columns lacking a supporting index (slow JOINs).
        • unused_indexes: Indexes with zero scans — candidates for DROP.
        • bloated_tables: Tables with >20% dead tuples needing VACUUM.
    - Each finding includes a 'fix' field with the recommended SQL statement.
    - Args: schema (optional str, default: 'public', use '*' for all schemas),
            connection/server (optional str)

21. analyze_table_indexes
    - Deep index analysis: primary keys, missing foreign key indexes, and unused indexes.
    - Args: tableName (str), schema (optional str), connection/server (optional str)

22. compare_schemas
    - Compares two connections: missing tables, missing columns, type mismatches.
    - Includes migration_sql: auto-generated ALTER/CREATE statements to bring target schema up to source.
    - Args: source_connection/source_server (str), target_connection/target_server (str), schema (optional str)

DBA MANAGEMENT
23. create_database
    - Creates a new database on the active (or specified) server.
    - Args: database (str), server/connection (optional str), encoding (optional str), template (optional str)

24. drop_database
    - Safety-guarded DROP DATABASE (requires confirmName matching target name).
    - Args: database (str), confirmName (str), force (optional bool), server/connection (optional str)

25. clone_database
    - Fast database cloning using PostgreSQL TEMPLATE mechanism.
    - Args: sourceDatabase (str), targetDatabase (str), server/connection (optional str)

26. terminate_connections
    - Terminates active connections to a specific database (PostgreSQL & MySQL).
    - Args: database (str), server/connection (optional str)

27. dump_database
    - Dumps database to SQL file using native pg_dump or mysqldump.
    - Args: database (optional str), outputPath (optional str), schemaOnly (bool), server/connection (optional str)

28. restore_database
    - Restores database from SQL dump file using native psql or mysql.
    - Args: database (str), dumpFilePath (str), server/connection (optional str)

HEALTH, AUDITING & VISUALIZATION
29. generate_erd
    - Generates Entity-Relationship Diagram in GitHub/Mermaid markdown syntax directly from foreign keys.
    - Args: schema (optional str), tables (optional list), include_columns (bool), connection/server (optional str)

30. diff_data
    - Row-level data comparison between two tables/schemas/databases with key matching and field diffs.
    - Args: table1 (str), table2 (optional str), key_columns (optional list), max_differences (int)

31. list_slow_queries
    - Inspects slow queries via pg_stat_statements or performance_schema / processlist.
    - Args: limit (int), min_duration_ms (float), connection/server (optional str)

32. get_locks
    - Real-time blocking dependency trees, lock wait durations, and active lock distributions.
    - Args: connection/server (optional str)

STREAMING & ETL
33. export_table
    - Streams table contents or SQL query results directly to CSV, JSON, or TSV on disk.
    - Args: table_or_query (str), output_path (str), format (str), is_query (bool)

34. import_csv
    - Batch imports CSV file into table with transaction safety, on_conflict handling, and dry-run rollback.
    - Args: table_name (str), csv_path (str), delimiter (str), on_conflict (str), dry_run (bool)

--------------------------------------------------------------------------------
Error Handling:
--------------------------------------------------------------------------------
All tools return rich PostgreSQL error details when a query fails:
  • pgcode       — PostgreSQL error code (e.g. 23503 for FK violation)
  • severity     — ERROR / FATAL / WARNING
  • detail       — Full PostgreSQL DETAIL message
  • hint         — PostgreSQL HINT for resolution
  • constraint   — Constraint name (for constraint violations)
  • table        — Table name from error context
  • suggestion   — Human-readable fix suggestion from the built-in suggestion map

--------------------------------------------------------------------------------
Configuration:
--------------------------------------------------------------------------------
* Dynamic Connections (~/.mcp-win-stdio/db_connections.json):
  Connections are stored and managed dynamically without needing environment variables.
  Both 'db' and 'excel-db' share this unified configuration hub.
  Use 'add_connection', 'edit_connection', 'remove_connection', and 'use_database' to manage them.
* Fallback / Backward Compatibility:
  Existing SERVERS or DATABASE_URL env vars are automatically ingested as fallbacks.

--------------------------------------------------------------------------------
Example Prompts for Claude:
--------------------------------------------------------------------------------
* "What databases are configured and what tables are in the active database?"
* "Switch to the showreel database (or server) and describe the users table."
* "Show me the full DDL for the orders table."
* "Show a sample of the users table — mask any sensitive columns."
* "Run a health audit on the showreel database and tell me what to fix."
* "Compare the dev and prod schemas and generate migration SQL for differences."
* "Create a clone of the showreel database named showreel_backup."
* "Show the active queries running on PostgreSQL right now."
================================================================================
"""
    print(guide_text)
