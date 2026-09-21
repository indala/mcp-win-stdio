"""
CLI entry point for mcp-win-stdio-tsc.
"""

import argparse
import os
import shutil
import sys
from pathlib import Path

from mcp_win_stdio.tsc import __version__
from mcp_win_stdio.tsc.guide import print_guide
from mcp_win_stdio.tsc.server import mcp


def cmd_run(args: argparse.Namespace) -> None:
    """Run TypeScript Watcher MCP server over stdio."""
    if args.dir:
        os.environ["TSC_WATCH_DIR"] = os.path.abspath(args.dir)
    mcp.run()


def cmd_doctor(args: argparse.Namespace) -> None:
    """Check TypeScript watcher health and dependencies."""
    print(f"\n=== mcp-win-stdio-tsc Doctor Diagnostic (v{__version__}) ===\n")
    print(f"[OK] Python: {sys.version.split()[0]} ({sys.executable})")

    for dep in ("mcp",):
        try:
            __import__(dep)
            print(f"[OK] Python Dependency: {dep:<12}")
        except ImportError:
            print(f"[FAIL] Python Dependency: {dep:<12} (MISSING - run `pip install mcp`)")

    print("\n--- TypeScript & Node.js System Tools ---")
    node_bin = shutil.which("node")
    if node_bin:
        print(f"[OK] Node.js Runtime: Found ({node_bin})")
    else:
        print("[WARN] Node.js Runtime: Not found on PATH")

    tsc_bin = shutil.which("tsc")
    if tsc_bin:
        print(f"[OK] Global TypeScript Compiler (tsc): Found ({tsc_bin})")
    else:
        print("[INFO] Global TypeScript Compiler (tsc): Not found on PATH (will check local node_modules/npx)")

    npx_bin = shutil.which("npx")
    if npx_bin:
        print(f"[OK] NPX Runner: Found ({npx_bin})")
    else:
        print("[INFO] NPX Runner: Not found")

    target_dir = os.environ.get("TSC_WATCH_DIR") or os.getcwd()
    print(f"\n[INFO] Target Watch Directory: {target_dir}")
    print("\nDiagnostic complete.\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="mcp-win-stdio-tsc",
        description="Windows-optimized TypeScript Diagnostic Watcher MCP CLI",
    )
    parser.add_argument("--version", "-v", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    sub_guide = subparsers.add_parser("guide", help="View usage guide and prompt recipes")
    sub_guide.set_defaults(func=lambda args: print_guide())

    sub_run = subparsers.add_parser("run", help="Run TypeScript Watcher MCP server over stdio")
    sub_run.add_argument("--dir", "-d", help="Target project directory to watch")
    sub_run.set_defaults(func=cmd_run)

    sub_doctor = subparsers.add_parser("doctor", help="Check dependencies and TypeScript compiler status")
    sub_doctor.set_defaults(func=cmd_doctor)

    args = parser.parse_args()
    if not args.command:
        if not sys.stdin.isatty():
            mcp.run()
            return
        parser.print_help()
        sys.exit(0)

    args.func(args)


if __name__ == "__main__":
    main()
