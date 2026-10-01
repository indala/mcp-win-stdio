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

Available Tools (25 Tools):
--------------------------------------------------------------------------------
CONNECTION MANAGEMENT
1.  list_connections
    - Lists all active and configured database connections from SERVERS env.

2.  use_database
    - Switches active connection or switches database on current/specified server.
    - Args: database (str), server/connection (optional str), name (optional str)

3.  add_connection
    - Dynamically adds a new PostgreSQL or MySQL connection string at runtime.
    - Args: name (str), url (str), type (optional str), setActive (bool)

SCHEMA INSPECTION
4.  list_databases
    - Lists all databases on the active (or specified) server.
    - Args: connection/server (optional str)

5.  list_schemas
    - Lists all schemas in the active PostgreSQL database or table summary in MySQL.
    - Args: connection/server (optional str)

6.  describe_table
    - Full schema inspection: columns, data types, nullability, defaults, PKs,
      foreign keys, and indexes. Auto-resolves cross-schema tables in PostgreSQL.
    - Args: tableName (str), schema (optional str), connection/server (optional str)

7.  schema_overview
    - Compact overview of all user tables and views with sizes and row counts.
    - Args: schema (optional str), connection/server (optional str), max_tables (int)

8.  compact_schema_overview
    - Ultra-compact one-liner per table: schema.table (col: type PK, col2: FK->ref)
    - Ideal for large databases — fits entire schema in minimal tokens.
    - Args: schema (optional str), connection/server (optional str), max_tables (int)

9.  get_table_ddl
    - Reconstructs the full CREATE TABLE DDL with column types, NOT NULL,
      defaults, all constraints (PK, FK, UNIQUE, CHECK), and extra indexes.
    - Args: tableName (str), schema (optional str), connection/server (optional str)

10. search_schema
    - Case-insensitive regex search for table, view, or column names.
    - Args: searchTerm (str), schema (optional str), max_results (int), connection/server (optional str)

DATA ACCESS
11. get_table_sample
    - Returns sample rows (default: 5) and estimated row count for quick inspection.
    - mask_sensitive=True (default) auto-redacts PII columns (password, token,
      secret, ssn, api_key, credit_card, etc.) as [REDACTED_SENSITIVE].
    - Args: tableName (str), limit (optional int), schema (optional str),
            mask_sensitive (optional bool, default: True), connection/server (optional str)

12. read_query
    - Safe SELECT queries returning structured JSON with row counts.
    - Args: sql (str), params (optional list), limit (optional int), max_cell_chars (int), connection/server (optional str)

13. execute_query
    - Executes DML / DDL statements (INSERT, UPDATE, DELETE, CREATE, ALTER) with
      transaction commit/rollback, batch statement progress, and affected row counts.
    - Args: sql (str), params (optional list), dry_run (optional bool), connection/server (optional str)

14. explain_query
    - Generates EXPLAIN query execution plan.
    - Args: sql (str), analyze (optional bool), connection/server (optional str)

DIAGNOSTICS & HEALTH
15. get_database_stats
    - Table size, row estimates, index sizes, active connections, cache hit ratio.
    - Args: connection/server (optional str)

16. list_active_queries
    - Lists running queries, connection duration, and process IDs.
    - Args: database (optional str), server/connection (optional str)

17. audit_database_health
    - Database-wide health audit (PostgreSQL only). Returns three categories:
        • unindexed_foreign_keys: FK columns lacking a supporting index (slow JOINs).
        • unused_indexes: Indexes with zero scans — candidates for DROP.
        • bloated_tables: Tables with >20% dead tuples needing VACUUM.
    - Each finding includes a 'fix' field with the recommended SQL statement.
    - Args: schema (optional str, default: 'public', use '*' for all schemas),
            connection/server (optional str)

18. analyze_table_indexes
    - Deep index analysis: primary keys, missing foreign key indexes, and unused indexes.
    - Args: tableName (str), schema (optional str), connection/server (optional str)

19. compare_schemas
    - Compares two connections: missing tables, missing columns, type mismatches.
    - Includes migration_sql: auto-generated ALTER/CREATE statements to bring target schema up to source.
    - Args: source_connection/source_server (str), target_connection/target_server (str), schema (optional str)

DBA MANAGEMENT
20. create_database
    - Creates a new database on the active (or specified) server.
    - Args: database (str), server/connection (optional str), encoding (optional str), template (optional str)

21. drop_database
    - Safety-guarded DROP DATABASE (requires confirmName matching target name).
    - Args: database (str), confirmName (str), force (optional bool), server/connection (optional str)

22. clone_database
    - Fast database cloning using PostgreSQL TEMPLATE mechanism.
    - Args: sourceDatabase (str), targetDatabase (str), server/connection (optional str)

23. terminate_connections
    - Terminates active connections to a specific database (PostgreSQL & MySQL).
    - Args: database (str), server/connection (optional str)

24. dump_database
    - Dumps database to SQL file using native pg_dump or mysqldump.
    - Args: database (optional str), outputPath (optional str), schemaOnly (bool), server/connection (optional str)

25. restore_database
    - Restores database from SQL dump file using native psql or mysql.
    - Args: database (str), dumpFilePath (str), server/connection (optional str)

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
Environment Variables:
--------------------------------------------------------------------------------
* SERVERS: JSON dictionary mapping server names to connection strings.
  Example:
  {
    "showreel": "postgresql://postgres:pass@localhost:5432/showreel",
    "dsr": "postgresql://postgres:pass@localhost:5432/dsr",
    "ijitest": "mysql://user:pass@srv604.hstgr.io:3306/db_name"
  }

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
