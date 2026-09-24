"""
CLI entry point for mcp-win-stdio-db.
"""

import argparse
import sys
from mcp_win_stdio.db import __version__
from mcp_win_stdio.db.server import mcp


def cmd_run(args: argparse.Namespace) -> None:
    """Run Database MCP server over stdio."""
    mcp.run()


def cmd_doctor(args: argparse.Namespace) -> None:
    """Check Database MCP health and dependencies."""
    print(f"\n=== mcp-win-stdio-db Doctor Diagnostic (v{__version__}) ===\n")
    print(f"[OK] Python: {sys.version.split()[0]} ({sys.executable})")

    for dep in ("mcp", "psycopg2", "pymysql"):
        try:
            __import__(dep)
            print(f"[OK] Driver: {dep:<12}")
        except ImportError:
            print(f"[FAIL] Driver: {dep:<12} (MISSING - run `pip install {dep}`)")

    print("\n--- Native DB Dump Utilities ---")
    import shutil
    for util in ("pg_dump", "psql", "mysqldump", "mysql"):
        loc = shutil.which(util)
        if loc:
            print(f"[OK] Tool: {util:<12} -> {loc}")
        else:
            print(f"[INFO] Tool: {util:<12} -> (Not on PATH, fallback SQL execution used)")

    print("\nDiagnostic complete.\n")


def cmd_guide(args: argparse.Namespace) -> None:
    """Print guide and prompt recipes."""
    print("""
=== mcp-win-stdio-db Guide & Recipes ===

Tools Provided:
  - list_connections, use_database, list_databases, list_schemas
  - describe_table, schema_overview, get_table_sample, search_schema
  - read_query, execute_query, explain_query, get_database_stats
  - create_database, drop_database, clone_database, terminate_connections
  - list_active_queries, dump_database, restore_database

Configuration:
  Pass SERVERS env var as JSON:
  SERVERS='{"showreel":"postgresql://...","dsr":"postgresql://...","ijitest":"mysql://..."}'

Run in Claude / Copilot:
  python -m mcp_win_stdio.db.server
""")


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="mcp-win-stdio-db",
        description="Unified Database MCP Server CLI (PostgreSQL & MySQL)",
    )
    parser.add_argument("--version", "-v", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    sub_guide = subparsers.add_parser("guide", help="View usage guide and recipes")
    sub_guide.set_defaults(func=cmd_guide)

    sub_doctor = subparsers.add_parser("doctor", help="Check database drivers and native tools")
    sub_doctor.set_defaults(func=cmd_doctor)

    sub_run = subparsers.add_parser("run", help="Run Database MCP server over stdio")
    sub_run.set_defaults(func=cmd_run)

    args = parser.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        # Default action is run
        cmd_run(args)


if __name__ == "__main__":
    main()
