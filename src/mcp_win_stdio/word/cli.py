"""
CLI entry point for mcp-win-stdio-word.
"""

import argparse
import os
import sys
from pathlib import Path

from mcp_win_stdio.word import __version__
from mcp_win_stdio.word.guide import print_guide
from mcp_win_stdio.word.server import mcp


def cmd_run(args: argparse.Namespace) -> None:
    """Run Word MCP server over stdio."""
    mcp.run()


def cmd_doctor(args: argparse.Namespace) -> None:
    """Check Word MCP health and dependencies."""
    print(f"\n=== mcp-win-stdio-word Doctor Diagnostic (v{__version__}) ===\n")
    print(f"[OK] Python: {sys.version.split()[0]} ({sys.executable})")

    for dep in ("mcp", "docx", "win32com"):
        try:
            __import__(dep)
            print(f"[OK] Dependency: {dep:<12}")
        except ImportError:
            if dep == "win32com":
                print(f"[INFO] Dependency: {dep:<12} (Optional for legacy .doc conversion)")
            else:
                print(f"[FAIL] Dependency: {dep:<12} (MISSING - run `pip install python-docx`)")

    print("\n--- Word COM Automation Check ---")
    try:
        import win32com.client
        app = win32com.client.Dispatch("Word.Application")
        app.Visible = False
        ver = app.Version
        app.Quit()
        print(f"[OK] Microsoft Word COM: Available (Version {ver})")
    except Exception as e:
        print(f"[INFO] Microsoft Word COM: Not detected ({e})")

    print("\nDiagnostic complete.\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="mcp-win-stdio-word",
        description="Windows-optimized Word Document MCP Server CLI",
    )
    parser.add_argument("--version", "-v", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    sub_guide = subparsers.add_parser("guide", help="View usage guide and prompt recipes")
    sub_guide.set_defaults(func=lambda args: print_guide())

    sub_run = subparsers.add_parser("run", help="Run Word MCP server over stdio")
    sub_run.set_defaults(func=cmd_run)

    sub_doctor = subparsers.add_parser("doctor", help="Check dependencies and Word COM status")
    sub_doctor.set_defaults(func=cmd_doctor)

    args = parser.parse_args()
    if not args.command:
        # Default to running server if piped or print help
        if not sys.stdin.isatty():
            mcp.run()
            return
        parser.print_help()
        sys.exit(0)

    args.func(args)


if __name__ == "__main__":
    main()
