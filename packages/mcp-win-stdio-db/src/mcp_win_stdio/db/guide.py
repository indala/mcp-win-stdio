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

Available Tools (23 Tools):
--------------------------------------------------------------------------------
CONNECTION MANAGEMENT
1.  list_connections
    - Lists all active and configured database connections from SERVERS env.

2.  use_database
    - Switches active connection or switches database on current server.
    - Args: name (str), database (optional str)

3.  add_connection
    - Dynamically adds a new PostgreSQL or MySQL connection string at runtime.
    - Args: name (str), url (str)

SCHEMA INSPECTION
4.  list_databases
    - Lists all databases on the active server.

5.  list_schemas
    - Lists all schemas in the active PostgreSQL database.

6.  describe_table
    - Full schema inspection: columns, data types, nullability, defaults, PKs,
      foreign keys, and indexes. Auto-resolves cross-schema tables in PostgreSQL.
    - Args: tableName (str), schemaName (optional str)

7.  schema_overview
    - Compact overview of all user tables and views.
    - Args: schemaName (optional str)

8.  compact_schema_overview                                          [NEW v0.2.4]
    - Ultra-compact one-liner per table: schema.table (col: type PK, col2: FK->ref)
    - Ideal for large databases — fits entire schema in minimal tokens.
    - Args: schemaName (optional str), connection (optional str)

9.  get_table_ddl                                                    [NEW v0.2.4]
    - Reconstructs the full CREATE TABLE DDL with column types, NOT NULL,
      defaults, all constraints (PK, FK, UNIQUE, CHECK), and extra indexes.
    - PostgreSQL only (MySQL falls back to SHOW CREATE TABLE).
    - Args: tableName (str), schema (optional str), connection (optional str)

10. search_schema
    - Case-insensitive regex search for table, view, or column names.
    - Args: query (str)

DATA ACCESS
11. get_table_sample                                                 [NEW v0.2.4]
    - Returns sample rows (default: 5) and estimated row count for quick inspection.
    - mask_sensitive=True (default) auto-redacts PII columns (password, token,
      secret, ssn, api_key, credit_card, etc.) as [REDACTED_SENSITIVE].
    - Args: tableName (str), schemaName (optional str), limit (optional int),
            mask_sensitive (optional bool, default: True)

12. read_query
    - Safe SELECT queries returning structured JSON with row counts.
    - Args: sql (str), limit (optional int)

13. execute_query
    - Executes DML / DDL statements (INSERT, UPDATE, DELETE, CREATE, ALTER) with
      transaction commit/rollback and affected row counts.
    - Args: sql (str), dry_run (optional bool)

14. explain_query
    - Generates EXPLAIN query execution plan.
    - Args: sql (str), analyze (optional bool)

DIAGNOSTICS & HEALTH
15. get_database_stats
    - Table size, row estimates, index sizes, and total database size.

16. list_active_queries
    - Lists running queries, connection duration, and process IDs.

17. audit_database_health                                            [NEW v0.2.4]
    - Database-wide health audit (PostgreSQL only). Returns three categories:
        • unindexed_foreign_keys: FK columns lacking a supporting index (slow JOINs).
        • unused_indexes: Indexes with zero scans — candidates for DROP.
        • bloated_tables: Tables with >20% dead tuples needing VACUUM.
    - Each finding includes a 'fix' field with the recommended SQL statement.
    - Args: schema (optional str, default: 'public', use '*' for all schemas),
            connection (optional str)

18. compare_schemas                                                  [ENHANCED]
    - Compares two connections: missing tables, missing columns, type mismatches.
    - Now includes migration_sql: auto-generated ALTER/CREATE statements to bring
      target schema up to source.
    - Args: source_connection (str), target_connection (str), schema (optional str)

DBA MANAGEMENT
19. create_database
    - Creates a new database on the active server.
    - Args: name (str), template (optional str, Postgres only), encoding (optional str)

20. drop_database
    - Safety-guarded DROP DATABASE (requires confirmName matching target name).
    - Args: name (str), confirmName (str), force (optional bool)

21. clone_database
    - Fast database cloning using PostgreSQL TEMPLATE mechanism.
    - Args: sourceDb (str), targetDb (str)

22. terminate_connections
    - Terminates active connections to a specific database (PostgreSQL only).
    - Args: dbName (str)

23. dump_database / restore_database
    - dump_database: Dumps database to SQL file using native pg_dump or mysqldump.
      Args: outputPath (str), tables (optional list)
    - restore_database: Restores database from SQL dump file using native psql or mysql.
      Args: inputPath (str), targetDb (optional str)

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
* "Switch to the ijitest database and describe the users table."
* "Show me the full DDL for the orders table."
* "Show a sample of the users table — mask any sensitive columns."
* "Run a health audit on the showreel database and tell me what to fix."
* "Compare the dev and prod schemas and generate migration SQL for differences."
* "Create a clone of the showreel database named showreel_backup."
* "Show the active queries running on PostgreSQL right now."
================================================================================
"""
    print(guide_text)
