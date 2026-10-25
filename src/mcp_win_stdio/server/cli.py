"""
CLI entry point for mws server.
"""

import argparse
import sys

from mcp_win_stdio.server import __version__
from mcp_win_stdio.server.catalog import get_server_catalog
from mcp_win_stdio.server.guide import print_server_guide
from mcp_win_stdio.server.server import mcp


def cmd_run(args: argparse.Namespace) -> None:
    """Run mws as an MCP Server over stdio."""
    mcp.run()


def cmd_list(args: argparse.Namespace) -> None:
    """Dynamically list all discovered MCP servers, installed status, and active/inactive states."""
    catalog = get_server_catalog(include_tools=args.verbose, refresh=args.refresh)
    print(f"\n=== ⚡ mws Gateway Server Catalog (v{__version__}) ===")
    print(f"Total Discovered: {catalog['total_servers']} servers | Active Running Sessions: {catalog['active_processes']}\n")

    print(f"{'SERVER':<12} {'INSTALLED':<14} {'STATUS':<24} {'TOOLS':<8} DESCRIPTION")
    print("-" * 88)

    for name, srv in catalog["servers"].items():
        inst_str = "[Installed]" if srv.get("installed", True) else "[Not Installed]"
        status = srv.get("status", "inactive")
        if status == "active":
            status_str = f"[Active (PID {srv.get('pid', '?')})]"
        elif status == "not_installed":
            status_str = "[Not Installed]"
        else:
            status_str = "[Inactive / Idle]"

        desc = srv["description"].splitlines()[0]
        if len(desc) > 36:
            desc = desc[:33] + "..."

        print(f"{name:<12} {inst_str:<14} {status_str:<24} {srv['tool_count']:<8} {desc}")
        if args.verbose and srv.get("tools"):
            print(f"  └─ Tools: {', '.join(srv['tools'])}")
    print("-" * 88)
    print("Commands:")
    print("  mws server stop <server>     -> Terminate active warm child process to release RAM\n")


def cmd_stop(args: argparse.Namespace) -> None:
    """Stop an active warm server process."""
    from mcp_win_stdio.server.process_pool import GLOBAL_POOL

    target = args.server.lower().strip()
    stopped = GLOBAL_POOL.stop_server(target)
    if stopped:
        print(f"✅ Server '{target}' process terminated.")
    else:
        print(f"ℹ️  Server '{target}' was not running.")


def cmd_doctor(args: argparse.Namespace) -> None:
    """Check mws server health and Python environment."""
    print(f"\n=== mws Server Diagnostic (v{__version__}) ===\n")
    print(f"[OK] Python: {sys.version.split()[0]} ({sys.executable})")

    for dep in ("mcp", "pathlib", "json", "subprocess"):
        try:
            __import__(dep)
            print(f"[OK] Core Library: {dep:<14}")
        except ImportError:
            print(f"[FAIL] Core Library: {dep:<14} (MISSING)")

    print("\nDiagnostic complete.\n")


def cmd_guide(args: argparse.Namespace) -> None:
    """Print guide and prompt recipes."""
    print_server_guide()


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="mws server",
        description="Unified On-Demand MCP Gateway & Dynamic Process Orchestrator",
    )
    subparsers = parser.add_subparsers(dest="subcommand", help="Available subcommands")

    run_parser = subparsers.add_parser("run", help="Run MCP server over stdio")
    run_parser.set_defaults(func=cmd_run)

    list_parser = subparsers.add_parser("list", help="List all discovered servers and tool counts")
    list_parser.add_argument("-v", "--verbose", action="store_true", help="Include tool names")
    list_parser.add_argument("-r", "--refresh", action="store_true", help="Force probe refresh")
    list_parser.set_defaults(func=cmd_list)

    stop_parser = subparsers.add_parser("stop", help="Stop an active warm child MCP process")
    stop_parser.add_argument("server", help="Server name to stop (e.g. 'excel', 'db')")
    stop_parser.set_defaults(func=cmd_stop)

    doc_parser = subparsers.add_parser("doctor", help="Check dependencies and health")
    doc_parser.set_defaults(func=cmd_doctor)

    guide_parser = subparsers.add_parser("guide", help="Print tool guide")
    guide_parser.set_defaults(func=cmd_guide)

    args = parser.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        cmd_run(args)


if __name__ == "__main__":
    main()
