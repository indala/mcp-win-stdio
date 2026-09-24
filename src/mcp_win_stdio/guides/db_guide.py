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
  DBA administrative tools (safe DROP, CREATE, CLONE), and native DUMP / RESTORE.

Available Tools (20 Tools):
--------------------------------------------------------------------------------
1.  list_connections
    - Lists all active and configured database connections from SERVERS env.

2.  use_database
    - Switches active connection or switches database on current server.
    - Args: name (str), database (optional str)

3.  list_databases
    - Lists all databases on the active server.

4.  list_schemas
    - Lists all schemas in the active PostgreSQL database.

5.  describe_table
    - Full schema inspection: columns, data types, nullability, defaults, PKs,
      foreign keys, and indexes. Auto-resolves cross-schema tables in PostgreSQL.
    - Args: tableName (str), schemaName (optional str)

6.  schema_overview
    - Compact overview of all user tables and views.
    - Args: schemaName (optional str)

7.  get_table_sample
    - Returns sample rows (default: 5) and estimated row count for quick inspection.
    - Args: tableName (str), schemaName (optional str), limit (optional int)

8.  search_schema
    - Case-insensitive regex search for table, view, or column names.
    - Args: query (str)

9.  read_query
    - Safe SELECT queries returning structured JSON with row counts.
    - Args: sql (str), limit (optional int)

10. execute_query
    - Executes DML / DDL statements (INSERT, UPDATE, DELETE, CREATE, ALTER) with
      transaction commit/rollback and affected row counts.
    - Args: sql (str)

11. explain_query
    - Generates EXPLAIN query execution plan.
    - Args: sql (str), analyze (optional bool)

12. get_database_stats
    - Table size, row estimates, index sizes, and total database size.

13. add_connection
    - Dynamically adds a new PostgreSQL or MySQL connection string at runtime.
    - Args: name (str), url (str)

14. create_database
    - Creates a new database on the active server.
    - Args: name (str), template (optional str, Postgres only), encoding (optional str)

15. drop_database
    - Safety-guarded DROP DATABASE (requires confirmName matching target name).
    - Args: name (str), confirmName (str), force (optional bool)

16. clone_database
    - Fast database cloning using PostgreSQL TEMPLATE mechanism.
    - Args: sourceDb (str), targetDb (str)

17. terminate_connections
    - Terminates active connections to a specific database (PostgreSQL only).
    - Args: dbName (str)

18. list_active_queries
    - Lists running queries, connection duration, and process IDs.

19. dump_database
    - Dumps database to SQL file using native pg_dump or mysqldump.
    - Args: outputPath (str), tables (optional list)

20. restore_database
    - Restores database from SQL dump file using native psql or mysql.
    - Args: inputPath (str), targetDb (optional str)

--------------------------------------------------------------------------------
Environment Variables:
--------------------------------------------------------------------------------
* SERVERS: JSON dictionary mapping server names to connection strings.
  Example:
  {
    "showreel": "postgresql://postgres:mohan@localhost:5432/showreel",
    "dsr": "postgresql://postgres:mohan@localhost:5432/dsr",
    "ijitest": "mysql://u116573049_ijitest:password@srv604.hstgr.io:3306/db_name"
  }

--------------------------------------------------------------------------------
Example Prompts for Claude:
--------------------------------------------------------------------------------
* "What databases are configured and what tables are in the active database?"
* "Switch to the ijitest database and describe the users table."
* "Create a clone of the showreel database named showreel_backup."
* "Show the active queries running on PostgreSQL right now."
================================================================================
"""
    print(guide_text)
