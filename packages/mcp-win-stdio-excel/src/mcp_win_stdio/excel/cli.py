"""
CLI entry point for mcp-win-stdio-excel.
"""

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

from mcp_win_stdio.excel import __version__
from mcp_win_stdio.excel.guide import print_guide
from mcp_win_stdio.excel.server import mcp


def get_claude_desktop_config_path() -> Path | None:
    appdata = os.environ.get("APPDATA")
    if appdata:
        p = Path(appdata) / "Claude" / "claude_desktop_config.json"
        if p.exists():
            return p
    default_p = Path.home() / "AppData" / "Roaming" / "Claude" / "claude_desktop_config.json"
    return default_p if default_p.exists() else None


def get_claude_cli_config_path() -> Path | None:
    p = Path.home() / ".claude.json"
    return p if p.exists() else None


def cmd_setup(args: argparse.Namespace) -> None:
    """Setup excel MCP server in Claude Desktop and Claude Code CLI."""
    client = args.client.lower()
    python_exe = sys.executable.replace("\\", "/")
    cmd_args = ["-m", "mcp_win_stdio.excel.server"]

    print(f"\nSetting up 'excel' MCP server (target: {client})...\n")

    # 1. Desktop
    if client in ("all", "desktop"):
        desktop_cfg = get_claude_desktop_config_path()
        if desktop_cfg:
            try:
                shutil.copy2(desktop_cfg, desktop_cfg.with_suffix(".json.bak"))
                with open(desktop_cfg, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if "mcpServers" not in data:
                    data["mcpServers"] = {}
                data["mcpServers"]["excel"] = {
                    "command": python_exe,
                    "args": cmd_args,
                }
                with open(desktop_cfg, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2)
                print(f"[OK] Claude Desktop: Configured 'excel' in {desktop_cfg}")
            except Exception as e:
                print(f"[ERROR] Claude Desktop: Failed to configure: {e}")
        else:
            print("[WARN] Claude Desktop configuration not found.")

    # 2. CLI
    if client in ("all", "cli"):
        added_cli = False
        try:
            res = subprocess.run(
                ["claude", "mcp", "add", "-s", "user", "excel", "--", python_exe] + cmd_args,
                capture_output=True,
                text=True,
                timeout=10,
            )
            if res.returncode == 0:
                added_cli = True
                print("[OK] Claude Code CLI: Configured via `claude mcp add`")
        except Exception:
            pass

        if not added_cli:
            cli_cfg = get_claude_cli_config_path()
            if cli_cfg:
                try:
                    with open(cli_cfg, "r", encoding="utf-8") as f:
                        cli_data = json.load(f)
                    if "mcpServers" not in cli_data:
                        cli_data["mcpServers"] = {}
                    cli_data["mcpServers"]["excel"] = {
                        "command": python_exe,
                        "args": cmd_args,
                    }
                    with open(cli_cfg, "w", encoding="utf-8") as f:
                        json.dump(cli_data, f, indent=2)
                    print(f"[OK] Claude Code CLI: Configured directly in {cli_cfg}")
                except Exception as e:
                    print(f"[ERROR] Claude CLI: Failed to configure: {e}")

    print("\nExcel MCP setup complete! Please restart Claude Desktop if active.\n")


def cmd_remove(args: argparse.Namespace) -> None:
    """Remove excel MCP server from Claude Desktop and CLI."""
    desktop_cfg = get_claude_desktop_config_path()
    if desktop_cfg and desktop_cfg.exists():
        try:
            with open(desktop_cfg, "r", encoding="utf-8") as f:
                data = json.load(f)
            if "mcpServers" in data and "excel" in data["mcpServers"]:
                del data["mcpServers"]["excel"]
                with open(desktop_cfg, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2)
                print(f"[OK] Removed 'excel' from Claude Desktop.")
        except Exception as e:
            print(f"[ERROR] Claude Desktop: {e}")

    try:
        res = subprocess.run(["claude", "mcp", "remove", "-s", "user", "excel"], capture_output=True, text=True)
        if res.returncode == 0:
            print("[OK] Removed 'excel' from Claude Code CLI.")
    except Exception:
        pass


def cmd_run(args: argparse.Namespace) -> None:
    """Run excel MCP server over stdio."""
    mcp.run()


def cmd_doctor(args: argparse.Namespace) -> None:
    """Check Excel MCP health and dependencies."""
    print(f"\n=== mcp-win-stdio-excel Doctor Diagnostic (v{__version__}) ===\n")
    print(f"[OK] Python: {sys.version.split()[0]} ({sys.executable})")

    for dep in ("mcp", "pandas", "openpyxl", "rapidfuzz", "win32com"):
        try:
            __import__(dep)
            print(f"[OK] Dependency: {dep:<12}")
        except ImportError:
            print(f"[FAIL] Dependency: {dep:<12} (MISSING)")

    print("\n--- Excel COM Automation Check ---")
    try:
        import win32com.client
        app = win32com.client.DispatchEx("Excel.Application")
        ver = app.Version
        app.Quit()
        print(f"[OK] Microsoft Excel COM: Available (Version {ver})")
    except Exception as e:
        print(f"[INFO] Microsoft Excel COM: Not detected ({e})")

    print("\nDiagnostic complete.\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="mcp-win-stdio-excel",
        description="Windows-optimized Excel MCP Server CLI",
    )
    parser.add_argument("--version", "-v", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    sub_setup = subparsers.add_parser("setup", help="Auto-configure into Claude Desktop & CLI")
    sub_setup.add_argument("--client", "-c", choices=["all", "desktop", "cli"], default="all")
    sub_setup.set_defaults(func=cmd_setup)

    sub_remove = subparsers.add_parser("remove", help="Remove from Claude Desktop & CLI")
    sub_remove.set_defaults(func=cmd_remove)

    sub_guide = subparsers.add_parser("guide", help="View usage guide and prompt recipes")
    sub_guide.set_defaults(func=lambda args: print_guide())

    sub_run = subparsers.add_parser("run", help="Run Excel MCP server over stdio")
    sub_run.set_defaults(func=cmd_run)

    sub_doctor = subparsers.add_parser("doctor", help="Check dependencies and COM automation")
    sub_doctor.set_defaults(func=cmd_doctor)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(0)

    args.func(args)


if __name__ == "__main__":
    main()
