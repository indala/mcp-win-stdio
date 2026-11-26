# `PostgreSQL CLI (`pg_dump`, `psql`)`

> Optional native PostgreSQL dump/restore tools invoked by `dump_database` and `restore_database` (with SQL fallback when absent).

## Tool Metadata

| Property | Details |
| :--- | :--- |
| **Category** | External CLI & Binary |
| **Install / Prerequisite** | PostgreSQL bin utilities on `PATH` |
| **Used By (`mcp-win-stdio`)** | `packages/mcp-win-stdio-db/src/mcp_win_stdio/db/server.py`, `db/cli.py`, `src/mcp_win_stdio/cli.py` |

## Subcommands, Flags & Environment Variables

| Function Name / Variable | Attributes & Description |
| :--- | :--- |
| `pg_dump -h <host> -p <port> -U <user> -f <file> [-F c\|d\|t\|p] <db>` | `binary` · Exports PostgreSQL schema/data snapshots (`dump_database`). |
| `pg_dump --schema-only` (`-s`) / `--data-only` (`-a`) / `--clean` (`-c`) / `--if-exists` | `flags` · Controls schema-only, data-only, or clean DDL output. |
| `psql -h <host> -p <port> -U <user> -d <db> -f <file>` | `binary` · Executes SQL restore scripts against a PostgreSQL database (`restore_database`). |
| `psql -v ON_ERROR_STOP=1` / `-1` (`--single-transaction`) | `flags` · Abort on first SQL error or wrap script execution in a single transaction. |
| `PGPASSWORD` | `env variable` · Passed in subprocess `env` by `db/server.py` for non-interactive authentication. |
