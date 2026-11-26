# `MySQL CLI (`mysqldump`, `mysql`)`

> Optional native MySQL/MariaDB dump/restore utilities invoked by `dump_database` and `restore_database`.

## Tool Metadata

| Property | Details |
| :--- | :--- |
| **Category** | External CLI & Binary |
| **Install / Prerequisite** | MySQL / MariaDB client utilities on `PATH` |
| **Used By (`mcp-win-stdio`)** | `packages/mcp-win-stdio-db/src/mcp_win_stdio/db/server.py`, `db/cli.py`, `src/mcp_win_stdio/cli.py` |

## Subcommands, Flags & Environment Variables

| Function Name / Variable | Attributes & Description |
| :--- | :--- |
| `mysqldump -h <host> -P <port> -u <user> <db>` | `binary` · Exports MySQL/MariaDB database SQL snapshots (`dump_database`). |
| `mysqldump --no-data` / `--no-create-info` / `--single-transaction` / `--routines` | `flags` · Controls schema-only, data-only, consistent snapshots, and stored routines. |
| `mysql -h <host> -P <port> -u <user> <db> < dump.sql` | `binary` · Restores SQL dump files via stdin redirection (`restore_database`). |
| `MYSQL_PWD` / `--password=...` | `auth` · Credential passing for non-interactive MySQL CLI execution. |
