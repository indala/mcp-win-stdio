"""
mcp-win-stdio CLI: Windows-optimized Model Context Protocol suite orchestrator.
"""

import argparse
import importlib
import os
from pathlib import Path
import subprocess
import sys
from typing import List, Optional

from mcp_win_stdio import __version__
from mcp_win_stdio.core.config import INDALA_DIR, PLUGINS_DIR, ensure_workspace_dirs, load_config
from mcp_win_stdio.core.discovery import BUILTIN_SERVERS, get_server_info, list_available_servers
from mcp_win_stdio.core.installer import (
    get_claude_cli_config_path,
    get_claude_desktop_config_path,
    install_server_to_cli,
    install_server_to_desktop,
    remove_server_from_cli,
    remove_server_from_desktop,
)
from mcp_win_stdio.guides.excel_guide import print_excel_guide
from mcp_win_stdio.guides.explorer_guide import print_explorer_guide


def cmd_list(args: argparse.Namespace) -> None:
    """List available MCP servers and installation status."""
    ensure_workspace_dirs()
    servers = list_available_servers()
    desktop_cfg = get_claude_desktop_config_path()
    cli_cfg = get_claude_cli_config_path()

    print(f"\n================ mcp-win-stdio v{__version__} ================")
    print(f"Single-Source Directory: {INDALA_DIR}")
    print(f"Claude Desktop Config:   {desktop_cfg or 'Not found'}")
    print(f"Claude Code CLI Config:  {cli_cfg or 'Not found'}\n")

    print(f"{'SERVER NAME':<16} {'TOOLS':<8} {'TYPE':<12} {'DESCRIPTION'}")
    print("-" * 75)

    for name, srv in servers.items():
        srv_type = "Built-in" if srv.get("is_builtin") else "User Plugin"
        tools = str(srv.get("tools_count", "?"))
        desc = srv.get("description", "")
        if len(desc) > 42:
            desc = desc[:39] + "..."
        print(f"{name:<16} {tools:<8} {srv_type:<12} {desc}")

    print("\nTo setup a server in Claude:  mcp-win-stdio setup [server_name]")
    print("To view usage guide & prompts: mcp-win-stdio guide [server_name]")
    print("To run a server over stdio:    mcp-win-stdio run <server_name>\n")


def cmd_guide(args: argparse.Namespace) -> None:
    """Print guide and prompts for a specific server."""
    target = (args.server or "all").lower()

    if target in ("excel", "all"):
        print_excel_guide()
    if target in ("explorer", "workspace-explorer", "all"):
        print_explorer_guide()

    if target not in ("excel", "explorer", "workspace-explorer", "all"):
        print(f"No specific guide available for '{target}'. Built-in guides: 'excel', 'explorer'.")


def cmd_setup(args: argparse.Namespace) -> None:
    """Configure one or all servers into Claude Desktop and Claude Code CLI."""
    ensure_workspace_dirs()
    servers = list_available_servers()

    target = args.server
    client = args.client.lower()

    # If no target passed, prompt interactively if running in terminal
    if not target:
        if sys.stdin.isatty():
            print("\n=== mcp-win-stdio Setup Wizard ===")
            print("Select which MCP servers you want to configure into Claude:")
            print("  [1] All servers (excel + explorer) [Recommended]")
            print("  [2] Excel MCP only (20 tools + COM automation)")
            print("  [3] Workspace Explorer MCP only (11 tools + smart ignore)")
            print("  [4] Exit")
            choice = input("\nEnter choice (1-4) [default: 1]: ").strip() or "1"
            if choice == "1":
                selected_servers = ["excel", "explorer"]
            elif choice == "2":
                selected_servers = ["excel"]
            elif choice == "3":
                selected_servers = ["explorer"]
            else:
                print("Setup cancelled.")
                return
        else:
            selected_servers = ["excel", "explorer"]
    elif target.lower() == "all":
        selected_servers = ["excel", "explorer"]
    else:
        if target.lower() not in servers:
            print(f"Error: Unknown server '{target}'. Run 'mcp-win-stdio list' to see available servers.")
            return
        selected_servers = [target.lower()]

    print(f"\nSetting up servers: {', '.join(selected_servers)} (target client: {client})...\n")

    for srv_name in selected_servers:
        print(f"--- Configuring '{srv_name}' ---")
        if client in ("all", "desktop"):
            ok, msg = install_server_to_desktop(srv_name)
            symbol = "OK" if ok else "WARN"
            print(f"  [{symbol}] Claude Desktop: {msg}")

        if client in ("all", "cli"):
            ok, msg = install_server_to_cli(srv_name)
            symbol = "OK" if ok else "WARN"
            print(f"  [{symbol}] Claude CLI:     {msg}")

    print("\nSetup complete! Please restart Claude Desktop if it is currently running.\n")


def cmd_remove(args: argparse.Namespace) -> None:
    """Remove server(s) from Claude Desktop and CLI."""
    target = args.server.lower()
    client = args.client.lower()

    servers_to_remove = ["excel", "explorer"] if target == "all" else [target]

    for srv_name in servers_to_remove:
        print(f"\nRemoving '{srv_name}'...")
        if client in ("all", "desktop"):
            ok, msg = remove_server_from_desktop(srv_name)
            print(f"  Claude Desktop: {msg}")
        if client in ("all", "cli"):
            ok, msg = remove_server_from_cli(srv_name)
            print(f"  Claude CLI:     {msg}")


def cmd_run(args: argparse.Namespace) -> None:
    """Run an MCP server over stdio."""
    server_name = args.server.lower()
    srv = get_server_info(server_name)

    if not srv:
        print(f"Error: Server '{server_name}' not found. Run 'mcp-win-stdio list' to view available servers.", file=sys.stderr)
        sys.exit(1)

    if srv["is_builtin"]:
        module_name = srv["module"]
        try:
            mod = importlib.import_module(module_name)
            if hasattr(mod, "mcp"):
                mod.mcp.run()
            else:
                print(f"Error: Module '{module_name}' does not expose 'mcp'.", file=sys.stderr)
                sys.exit(1)
        except Exception as e:
            print(f"Error launching server '{server_name}': {str(e)}", file=sys.stderr)
            sys.exit(1)
    else:
        # Run custom user plugin
        plugin_path = srv["path"]
        try:
            subprocess.run([sys.executable, plugin_path])
        except Exception as e:
            print(f"Error running plugin: {str(e)}", file=sys.stderr)
            sys.exit(1)


def cmd_doctor(args: argparse.Namespace) -> None:
    """Run diagnostic health checks on Windows environment and dependencies."""
    print(f"\n=== mcp-win-stdio Doctor Diagnostic (v{__version__}) ===\n")

    # 1. Python Check
    py_ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    py_status = "OK" if sys.version_info >= (3, 10) else "FAIL (Requires Python 3.10+)"
    print(f"[{py_status}] Python Runtime: {py_ver} ({sys.executable})")

    # 2. Dependencies
    deps = [
        ("mcp", "MCP Protocol Framework"),
        ("pathspec", "Git-Wildmatch Pattern Engine"),
        ("rapidfuzz", "RapidFuzz Vector Matcher"),
        ("pandas", "Pandas DataFrames"),
        ("openpyxl", "OpenPyXL Engine"),
        ("win32com", "PyWin32 COM Automation"),
    ]
    for mod, desc in deps:
        try:
            importlib.import_module(mod)
            print(f"[OK] Dependency: {mod:<12} ({desc})")
        except ImportError:
            print(f"[WARN] Dependency: {mod:<12} ({desc}) - Not installed")

    # 3. Native Excel COM Check
    print("\n--- Windows Excel COM Check ---")
    try:
        import win32com.client
        excel_app = win32com.client.DispatchEx("Excel.Application")
        excel_ver = excel_app.Version
        excel_app.Quit()
        print(f"[OK] Microsoft Excel COM Automation: Active (Version {excel_ver})")
    except Exception as e:
        print(f"[INFO] Microsoft Excel COM Automation: Not available ({str(e)})")

    # 4. Claude Config Files
    print("\n--- Claude Configuration Targets ---")
    desktop_cfg = get_claude_desktop_config_path()
    if desktop_cfg and desktop_cfg.exists():
        print(f"[OK] Claude Desktop: {desktop_cfg}")
    else:
        print(f"[WARN] Claude Desktop config not found at standard path")

    cli_cfg = get_claude_cli_config_path()
    if cli_cfg and cli_cfg.exists():
        print(f"[OK] Claude Code CLI: {cli_cfg}")
    else:
        print(f"[INFO] Claude Code CLI config: {cli_cfg or 'Not found'}")

    print("\nDiagnostic complete.\n")


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="mcp-win-stdio",
        description="Windows-optimized Model Context Protocol suite & setup orchestrator.",
    )
    parser.add_argument("--version", "-v", action="version", version=f"%(prog)s {__version__}")

    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    # list
    sub_list = subparsers.add_parser("list", help="List available MCP servers and tool counts")
    sub_list.set_defaults(func=cmd_list)

    # guide
    sub_guide = subparsers.add_parser("guide", help="View usage guide, tool specs, and LLM prompts")
    sub_guide.add_argument("server", nargs="?", default="all", help="Server name ('excel', 'explorer', 'all')")
    sub_guide.set_defaults(func=cmd_guide)

    # setup
    sub_setup = subparsers.add_parser("setup", help="Configure server(s) into Claude Desktop and CLI")
    sub_setup.add_argument("server", nargs="?", default=None, help="Server to install ('excel', 'explorer', 'all')")
    sub_setup.add_argument("--client", "-c", choices=["all", "desktop", "cli"], default="all", help="Target client")
    sub_setup.set_defaults(func=cmd_setup)

    # remove
    sub_remove = subparsers.add_parser("remove", help="Remove server(s) from Claude Desktop and CLI")
    sub_remove.add_argument("server", help="Server to remove ('excel', 'explorer', 'all')")
    sub_remove.add_argument("--client", "-c", choices=["all", "desktop", "cli"], default="all", help="Target client")
    sub_remove.set_defaults(func=cmd_remove)

    # run
    sub_run = subparsers.add_parser("run", help="Launch an MCP server over stdio for Claude")
    sub_run.add_argument("server", help="Server name to launch ('excel', 'explorer', or custom plugin)")
    sub_run.set_defaults(func=cmd_run)

    # doctor
    sub_doctor = subparsers.add_parser("doctor", help="Check system health, dependencies, and COM readiness")
    sub_doctor.set_defaults(func=cmd_doctor)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(0)

    args.func(args)


if __name__ == "__main__":
    main()
