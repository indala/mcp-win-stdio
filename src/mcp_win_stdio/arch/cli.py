"""
CLI entry point for mcp-win-stdio-arch.
"""

import argparse
import sys

from mcp_win_stdio.arch import __version__
from mcp_win_stdio.arch.server import mcp


def cmd_run(args: argparse.Namespace) -> None:
    """Run Architecture Blueprint MCP server over stdio."""
    mcp.run()


def cmd_doctor(args: argparse.Namespace) -> None:
    """Check Architecture Blueprint MCP health."""
    print(f"\n=== mcp-win-stdio-arch Doctor Diagnostic (v{__version__}) ===\n")
    print(f"[OK] Python: {sys.version.split()[0]} ({sys.executable})")

    for dep in ("mcp", "networkx"):
        try:
            __import__(dep)
            print(f"[OK] Library: {dep:<14}")
        except ImportError:
            print(f"[FAIL] Library: {dep:<14} (MISSING - run `pip install {dep}`)")

    print("\nDiagnostic complete.\n")


def cmd_guide(args: argparse.Namespace) -> None:
    """Print guide and prompt recipes."""
    print("""
=== mcp-win-stdio-arch Guide & Recipes ===

Tools Provided:
  - blueprint_feature(domain, workspace_root)
  - blueprint_erd(domain, workspace_root)
  - blueprint_trace(target, workspace_root)
  - blueprint_impact(node_id, direction, workspace_root)
  - blueprint_audit(workspace_root)
""")


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="mcp-win-stdio-arch",
        description="Universal Architecture Blueprint MCP Server",
    )
    subparsers = parser.add_subparsers(dest="subcommand", help="Available subcommands")

    run_parser = subparsers.add_parser("run", help="Run MCP server over stdio")
    run_parser.set_defaults(func=cmd_run)

    doc_parser = subparsers.add_parser("doctor", help="Check dependencies and health")
    doc_parser.set_defaults(func=cmd_doctor)

    guide_parser = subparsers.add_parser("guide", help="Print tool guide")
    guide_parser.set_defaults(func=cmd_guide)

    args = parser.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        # Default action: run stdio server
        cmd_run(args)


if __name__ == "__main__":
    main()
