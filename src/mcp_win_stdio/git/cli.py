"""
CLI entry point for mcp-win-stdio-git.
"""

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys

from mcp_win_stdio.git import __version__
from mcp_win_stdio.git.server import mcp, is_git_installed, is_gh_installed


def cmd_run(args: argparse.Namespace) -> None:
    """Run Git & GitHub MCP server over stdio."""
    mcp.run()


def cmd_doctor(args: argparse.Namespace) -> None:
    """Run diagnostic checks on Git, GitHub CLI, author identity, and authentication."""
    print(f"\n=== mcp-win-stdio-git Doctor Diagnostic (v{__version__}) ===\n")
    print(f"[OK] Python Runtime: {sys.version.split()[0]} ({sys.executable})")

    # 1. Git CLI Check
    git_bin = shutil.which("git")
    if git_bin:
        try:
            ver = subprocess.run(["git", "--version"], capture_output=True, text=True, check=True).stdout.strip()
            print(f"[OK] Git CLI: {ver} ({git_bin})")
        except Exception:
            print(f"[OK] Git CLI: Found at {git_bin}")

        # Git Config
        name = subprocess.run(["git", "config", "user.name"], capture_output=True, text=True).stdout.strip()
        email = subprocess.run(["git", "config", "user.email"], capture_output=True, text=True).stdout.strip()
        if name and email:
            print(f"[OK] Git Identity: {name} <{email}>")
        else:
            print(f"[WARN] Git Identity: Not configured (missing user.name or user.email)")
            print(f"       👉 Run: git config --global user.name \"Your Name\"")
            print(f"       👉 Run: git config --global user.email \"you@example.com\"")
    else:
        print(f"[FAIL] Git CLI: Not found on PATH")
        print(f"       👉 Install Git: winget install --id Git.Git -e")
        if sys.stdin.isatty():
            install = input("       Would you like to install Git now via winget? [Y/n]: ").strip().lower()
            if install not in ("n", "no"):
                subprocess.run(["winget", "install", "--id", "Git.Git", "-e"])

    # 2. GitHub CLI Check
    gh_bin = shutil.which("gh")
    if gh_bin:
        try:
            ver_line = subprocess.run(["gh", "--version"], capture_output=True, text=True, check=True).stdout.splitlines()[0]
            print(f"[OK] GitHub CLI: {ver_line} ({gh_bin})")
        except Exception:
            print(f"[OK] GitHub CLI: Found at {gh_bin}")

        # GitHub Auth status
        auth_res = subprocess.run(["gh", "auth", "status"], capture_output=True, text=True, encoding="utf-8", errors="replace")
        auth_out = auth_res.stderr or auth_res.stdout
        if "Logged in to" in auth_out:
            first_account = [ln.strip() for ln in auth_out.splitlines() if "Logged in to" in ln]
            account_str = first_account[0] if first_account else "Active"
            account_str = account_str.replace("✓", "").replace("âœ“", "").strip()
            print(f"[OK] GitHub Auth: Logged in ({account_str})")
        else:
            print(f"[INFO] GitHub Auth: Not logged in")
            print(f"       👉 Run: gh auth login")
    else:
        print(f"[INFO] GitHub CLI: Not found on PATH (Optional: enables PR, Issue, and Actions tools)")
        print(f"       👉 Install GitHub CLI: winget install --id GitHub.cli -e")
        if sys.stdin.isatty():
            install = input("       Would you like to install GitHub CLI now via winget? [y/N]: ").strip().lower()
            if install in ("y", "yes"):
                subprocess.run(["winget", "install", "--id", "GitHub.cli", "-e"])

    print("\nDiagnostic complete.\n")


def cmd_guide(args: argparse.Namespace) -> None:
    """Print Git MCP guide and prompt recipes."""
    from mcp_win_stdio.guides.git_guide import print_git_guide
    print_git_guide()


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="mcp-win-stdio-git",
        description="Unified Git & GitHub MCP Server CLI (Local Git + Remote GitHub CLI)",
    )
    parser.add_argument("--version", "-v", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    sub_guide = subparsers.add_parser("guide", help="View usage guide, tool references, and prompts")
    sub_guide.set_defaults(func=cmd_guide)

    sub_doctor = subparsers.add_parser("doctor", help="Check Git & GitHub CLI health, identity, and auth")
    sub_doctor.set_defaults(func=cmd_doctor)

    sub_run = subparsers.add_parser("run", help="Run Git & GitHub MCP server over stdio")
    sub_run.set_defaults(func=cmd_run)

    args = parser.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        cmd_run(args)


if __name__ == "__main__":
    main()
