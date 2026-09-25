"""
mcp-win-stdio CLI: Windows-optimized Model Context Protocol suite orchestrator.
"""

import argparse
import importlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Dict, List, Optional

# Ensure Windows console uses UTF-8 without crashing on cp1252
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from mcp_win_stdio import __version__
from mcp_win_stdio.core.config import INDALA_DIR, PLUGINS_DIR, ensure_workspace_dirs, load_config, save_config
from mcp_win_stdio.core.discovery import BUILTIN_SERVERS, get_server_info, list_available_servers
from mcp_win_stdio.core.installer import (
    generate_claude_cli_command,
    generate_claude_desktop_snippet,
    get_claude_cli_config_path,
    get_claude_desktop_config_path,
    install_pip_dependencies,
    remove_server_from_cli,
    remove_server_from_desktop,
    safe_apply_to_cli,
    safe_apply_to_desktop,
)
from mcp_win_stdio.guides.excel_guide import print_excel_guide
from mcp_win_stdio.guides.explorer_guide import print_explorer_guide
from mcp_win_stdio.guides.tsc_guide import print_tsc_guide
from mcp_win_stdio.guides.word_guide import print_word_guide
from mcp_win_stdio.guides.db_guide import print_db_guide



def print_dashboard() -> None:
    """Print interactive home dashboard when run with no arguments."""
    ensure_workspace_dirs()
    servers = list_available_servers()
    desktop_cfg = get_claude_desktop_config_path()
    cli_cfg = get_claude_cli_config_path()

    print(f"\n" + "=" * 76)
    print(f"   🚀  mcp-win-stdio — Windows Model Context Protocol Suite (v{__version__})")
    print("=" * 76)
    print(f" Single-Source Hub:      {INDALA_DIR}")
    print(f" Claude Desktop Config:  {desktop_cfg or 'Not detected (%APPDATA%\\Claude)'}")
    print(f" Claude Code CLI Config: {cli_cfg or 'Not detected (~/.claude.json)'}")
    print("-" * 76)

    print(f"{'SERVER':<12} {'STATUS':<16} {'TOOLS':<8} {'DESCRIPTION'}")
    print("-" * 76)

    for name, srv in servers.items():
        is_inst = srv.get("is_installed", False)
        status_str = "[Installed]" if is_inst else "[Not Installed]"
        tools = str(srv.get("tools_count", "?"))
        desc = srv.get("description", "")
        if len(desc) > 36:
            desc = desc[:33] + "..."
        print(f"{name:<12} {status_str:<16} {tools:<8} {desc}")

    print("-" * 76)
    print(" 💡 Quick Commands:")
    print("   mws setup <server>    -> Install dependencies & show Claude config")
    print("   mws guide <server>    -> View complete tool reference & Claude prompts")
    print("   mws doctor            -> Run health checks (Office COM, Python, Node)")
    print("   mws run <server>      -> Launch MCP server over stdio")
    print("   mws list              -> List all servers and custom plugins")
    print("=" * 76 + "\n")


def cmd_list(args: argparse.Namespace) -> None:
    """List available MCP servers and installation status."""
    print_dashboard()


def cmd_guide(args: argparse.Namespace) -> None:
    """Print guide and prompt recipes for a specific server."""
    target = (args.server or "all").lower()

    if target in ("excel", "all"):
        print_excel_guide()
    if target in ("word", "all"):
        print_word_guide()
    if target in ("explorer", "workspace-explorer", "all"):
        print_explorer_guide()
    if target in ("tsc", "all"):
        print_tsc_guide()
    if target in ("db", "database", "all"):
        print_db_guide()

    if target not in ("excel", "word", "explorer", "workspace-explorer", "tsc", "db", "database", "all"):
        print(f"No built-in guide for '{target}'. Built-in guides: 'excel', 'word', 'explorer', 'tsc', 'db'.")


def cmd_setup(args: argparse.Namespace) -> None:
    """Setup and configure a server with transparent guidance and optional safe auto-apply."""
    ensure_workspace_dirs()
    servers = list_available_servers()

    target = args.server
    client = args.client.lower()

    if not target:
        if sys.stdin.isatty():
            print("\n=== 🛠️  mcp-win-stdio Setup Wizard ===")
            print("Select an MCP server to configure:")
            print("  [1] excel     (20 tools: Pandas queries, RapidFuzz reconciliation, Office COM)")
            print("  [2] word      (10 tools: Multi-unit margins, multi-columns, typography, images)")
            print("  [3] explorer  (11 tools: Token-safe tree, .gitignore, regex grep, AST outline)")
            print("  [4] tsc       (6 tools: TypeScript diagnostic watcher, 0ms cache)")
            print("  [5] db        (20 tools: Polyglot PostgreSQL & MySQL DBA manager)")
            print("  [6] all       (Configure all servers)")
            print("  [7] Exit")
            choice = input("\nEnter choice (1-7) [default: 1]: ").strip() or "1"
            mapping = {"1": "excel", "2": "word", "3": "explorer", "4": "tsc", "5": "db", "6": "all"}
            if choice not in mapping:
                print("Setup cancelled.")
                return
            target = mapping[choice]
        else:
            target = "all"

    selected_servers = ["excel", "word", "explorer", "tsc", "db"] if target.lower() == "all" else [target.lower()]

    for srv_name in selected_servers:
        srv = get_server_info(srv_name)
        if not srv:
            print(f"\n[ERROR] Unknown server: '{srv_name}'. Run 'mws list' to see available servers.")
            continue

        print(f"\n" + "=" * 70)
        print(f"  Configuration Setup for: {srv['title']}")
        print("=" * 70)

        # 1. Dependency check & optional installation
        env_vars = {}
        if not srv.get("is_installed"):
            req_pip = srv.get("required_pip", [])
            print(f"\n[INFO] '{srv_name}' requires the following Python packages: {', '.join(req_pip)}")
            if sys.stdin.isatty():
                do_install = input(f"Would you like to install them now via pip? [Y/n]: ").strip().lower()
                if do_install not in ("n", "no"):
                    ok, msg = install_pip_dependencies(req_pip)
                    if ok:
                        print(f"[OK] {msg}")
                    else:
                        print(f"[WARN] {msg}")
            else:
                install_pip_dependencies(req_pip)

        # Special prompt for TSC watch directory
        if srv_name == "tsc":
            default_dir = os.getcwd()
            if sys.stdin.isatty():
                chosen_dir = input(f"\nEnter TypeScript project directory to watch [default: {default_dir}]: ").strip() or default_dir
            else:
                chosen_dir = default_dir
            env_vars["TSC_WATCH_DIR"] = os.path.abspath(chosen_dir)

        # Special prompt for DB SERVERS env var
        if srv_name == "db":
            servers_env = os.environ.get("SERVERS")
            if servers_env:
                env_vars["SERVERS"] = servers_env
            elif sys.stdin.isatty():
                print("\n[Optional] Enter SERVERS JSON string (or press Enter to configure later):")
                chosen_servers = input("SERVERS JSON: ").strip()
                if chosen_servers:
                    env_vars["SERVERS"] = chosen_servers

        # 2. Transparent Configuration Guidance
        snippet_dict = generate_claude_desktop_snippet(srv_name, env_vars if env_vars else None)
        snippet_json = json.dumps({srv_name: snippet_dict}, indent=2)
        cli_command = generate_claude_cli_command(srv_name, env_vars if env_vars else None)

        print("\n" + "-" * 70)
        print("📋 Claude Desktop Configuration:")
        print("File: %APPDATA%\\Claude\\claude_desktop_config.json")
        print("Add this snippet inside your \"mcpServers\" object:\n")
        print(snippet_json)

        print("\n" + "-" * 70)
        print("💻 Claude Code CLI Command:")
        print("Run this command in your terminal:\n")
        print(f"  {cli_command}")
        print("-" * 70)

        # 3. Optional Safe Auto-Write
        if sys.stdin.isatty():
            auto_apply = input("\n👉 Would you like mws to safely write this configuration for you? [y/N]: ").strip().lower()
            if auto_apply in ("y", "yes"):
                if client in ("all", "desktop"):
                    ok, msg = safe_apply_to_desktop(srv_name, env_vars if env_vars else None)
                    symbol = "OK" if ok else "ERROR"
                    print(f"  [{symbol}] Claude Desktop: {msg}")
                if client in ("all", "cli"):
                    ok, msg = safe_apply_to_cli(srv_name, env_vars if env_vars else None)
                    symbol = "OK" if ok else "ERROR"
                    print(f"  [{symbol}] Claude Code CLI: {msg}")
                print("\n[NOTE] Please restart Claude Desktop if it is currently running.")
        else:
            print("\nTo auto-apply via script, pass interactive input or use the JSON snippet above.")

    print("\n" + "=" * 70)
    print("Setup guide complete!")
    print("=" * 70 + "\n")


def cmd_remove(args: argparse.Namespace) -> None:
    """Remove server(s) from Claude Desktop and CLI."""
    target = args.server.lower()
    client = args.client.lower()

    servers_to_remove = ["excel", "word", "explorer", "tsc", "db"] if target == "all" else [target]

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
        print(f"Error: Server '{server_name}' not found. Run 'mws list' to view available servers.", file=sys.stderr)
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
    """Run diagnostic health checks on Windows environment, COM automation, and dependencies."""
    print(f"\n=== mcp-win-stdio Doctor Diagnostic (v{__version__}) ===\n")

    # 1. Python Check
    py_ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    py_status = "OK" if sys.version_info >= (3, 10) else "FAIL (Requires Python 3.10+)"
    print(f"[{py_status}] Python Runtime: {py_ver} ({sys.executable})")

    # 1b. Scripts & PATH Check
    import sysconfig
    scripts_dir = sysconfig.get_path("scripts")
    path_env = os.environ.get("PATH", "")
    in_path = False
    if scripts_dir:
        in_path = any(
            os.path.normcase(os.path.normpath(scripts_dir)) == os.path.normcase(os.path.normpath(p.strip()))
            for p in path_env.split(os.pathsep)
            if p.strip()
        )
    scripts_exist = os.path.isdir(scripts_dir) if scripts_dir else False

    if scripts_exist and in_path:
        print(f"[OK] Scripts Directory: {scripts_dir} (in PATH)")
    elif scripts_exist and not in_path:
        print(f"[WARN] Scripts Directory: {scripts_dir} (NOT in PATH)")
        print(f"       Tip: Add to PATH to run 'mws' directly, or run: python -m mcp_win_stdio <command>")
    else:
        print(f"[INFO] Scripts Directory: Not created yet ({scripts_dir})")
        print(f"       Tip: You can always run: python -m mcp_win_stdio <command>")

    # 2. Python Dependencies
    deps = [
        ("mcp", "MCP Protocol Framework (Core)"),
        ("docx", "Python-Docx (Word MCP)"),
        ("pandas", "Pandas DataFrames (Excel MCP)"),
        ("openpyxl", "OpenPyXL Engine (Excel MCP)"),
        ("rapidfuzz", "RapidFuzz Vector Matcher (Excel & Explorer)"),
        ("pathspec", "Git-Wildmatch Pattern Engine (Explorer MCP)"),
        ("win32com", "PyWin32 Windows COM Automation (Excel & Word)"),
        ("psycopg2", "PostgreSQL Adapter (Database MCP)"),
        ("pymysql", "MySQL Pure-Python Driver (Database MCP)"),
    ]
    print("\n--- Python Dependencies ---")
    for mod, desc in deps:
        try:
            importlib.import_module(mod)
            print(f"[OK] {mod:<14} : {desc}")
        except ImportError:
            print(f"[MISSING] {mod:<10} : {desc}")

    # 3. Microsoft Office COM Automation
    print("\n--- Microsoft Office COM Automation ---")
    try:
        import win32com.client
        excel_app = win32com.client.DispatchEx("Excel.Application")
        excel_ver = excel_app.Version
        excel_app.Quit()
        print(f"[OK] Microsoft Excel COM Automation: Ready (Version {excel_ver})")
    except Exception as e:
        print(f"[INFO] Microsoft Excel COM Automation: Not available ({str(e)})")

    try:
        import win32com.client
        word_app = win32com.client.Dispatch("Word.Application")
        word_app.Visible = False
        word_ver = word_app.Version
        word_app.Quit()
        print(f"[OK] Microsoft Word COM Automation: Ready (Version {word_ver})")
    except Exception as e:
        print(f"[INFO] Microsoft Word COM Automation: Not available ({str(e)})")

    # 4. Native Database Dump & Client Utilities
    print("\n--- Native Database Dump & Client Utilities ---")
    for util in ("pg_dump", "psql", "mysqldump", "mysql"):
        loc = shutil.which(util)
        status = "OK" if loc else "INFO"
        note = loc if loc else "Not on PATH (fallback SQL used)"
        print(f"[{status}] Tool: {util:<12} -> {note}")

    # 5. Node.js & TypeScript
    print("\n--- Node.js & TypeScript Environment ---")
    node_bin = shutil.which("node")
    print(f"[{'OK' if node_bin else 'INFO'}] Node.js: {node_bin or 'Not found on PATH'}")

    tsc_bin = shutil.which("tsc")
    print(f"[{'OK' if tsc_bin else 'INFO'}] Global tsc: {tsc_bin or 'Not found on PATH (will check local projects)'}")

    # 6. Claude Config Files

    print("\n--- Claude Configuration Targets ---")
    desktop_cfg = get_claude_desktop_config_path()
    if desktop_cfg and desktop_cfg.exists():
        print(f"[OK] Claude Desktop: {desktop_cfg}")
    else:
        print(f"[INFO] Claude Desktop config: {desktop_cfg or 'Not found in %APPDATA%\\Claude'}")

    cli_cfg = get_claude_cli_config_path()
    if cli_cfg and cli_cfg.exists():
        print(f"[OK] Claude Code CLI: {cli_cfg}")
    else:
        print(f"[INFO] Claude Code CLI config: {cli_cfg or 'Not found in ~/.claude.json'}")

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
    sub_guide.add_argument("server", nargs="?", default="all", help="Server name ('excel', 'word', 'explorer', 'tsc', 'all')")
    sub_guide.set_defaults(func=cmd_guide)

    # setup
    sub_setup = subparsers.add_parser("setup", help="Configure server(s) into Claude Desktop and CLI")
    sub_setup.add_argument("server", nargs="?", default=None, help="Server to install ('excel', 'word', 'explorer', 'tsc', 'all')")
    sub_setup.add_argument("--client", "-c", choices=["all", "desktop", "cli"], default="all", help="Target client")
    sub_setup.set_defaults(func=cmd_setup)

    # remove
    sub_remove = subparsers.add_parser("remove", help="Remove server(s) from Claude Desktop and CLI")
    sub_remove.add_argument("server", help="Server to remove ('excel', 'word', 'explorer', 'tsc', 'all')")
    sub_remove.add_argument("--client", "-c", choices=["all", "desktop", "cli"], default="all", help="Target client")
    sub_remove.set_defaults(func=cmd_remove)

    # run
    sub_run = subparsers.add_parser("run", help="Launch an MCP server over stdio for Claude")
    sub_run.add_argument("server", help="Server name to launch ('excel', 'word', 'explorer', 'tsc', or custom plugin)")
    sub_run.set_defaults(func=cmd_run)

    # doctor
    sub_doctor = subparsers.add_parser("doctor", help="Check system health, dependencies, and COM readiness")
    sub_doctor.set_defaults(func=cmd_doctor)

    args = parser.parse_args()
    if not args.command:
        # Default action when run with no arguments: show interactive dashboard
        print_dashboard()
        sys.exit(0)

    args.func(args)


if __name__ == "__main__":
    main()
