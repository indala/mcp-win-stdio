"""
mcp-win-stdio CLI: Windows-optimized Model Context Protocol suite orchestrator.
"""

import argparse
import importlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# Ensure Windows console uses UTF-8 without crashing on cp1252
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# In monorepo development, dynamically discover packages/*/src if present
_repo_packages = Path(__file__).resolve().parent.parent.parent / "packages"
if _repo_packages.is_dir():
    import pkgutil

    for _sub in _repo_packages.glob("*/src"):
        _s = str(_sub.resolve())
        if _s not in sys.path:
            sys.path.insert(0, _s)
    if "mcp_win_stdio" in sys.modules:
        sys.modules["mcp_win_stdio"].__path__ = pkgutil.extend_path(
            sys.modules["mcp_win_stdio"].__path__, "mcp_win_stdio"
        )

from mcp_win_stdio import __version__
from mcp_win_stdio.core.config import INDALA_DIR, ensure_workspace_dirs
from mcp_win_stdio.core.discovery import BUILTIN_SERVERS, get_server_info, list_available_servers
from mcp_win_stdio.core.environment import (
    check_and_prompt_path_setup,
    get_candidate_script_dirs,
    is_in_path,
)
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
    uninstall_pip_packages,
)
from mcp_win_stdio.core.updater import (
    check_for_update,
    format_update_banner,
    get_cached_or_latest_version,
)


def print_dashboard() -> None:
    """Print interactive home dashboard when run with no arguments."""
    ensure_workspace_dirs()
    servers = list_available_servers()
    desktop_cfg = get_claude_desktop_config_path()
    cli_cfg = get_claude_cli_config_path()

    # Check for PyPI updates (fast/cached)
    update_info = check_for_update(__version__)
    if update_info:
        cur, latest = update_info
        print("\n" + format_update_banner(cur, latest))

    # Check if Python Scripts directory is missing from PATH and prompt user
    check_and_prompt_path_setup()

    print("\n" + "=" * 76)

    print(f"   🚀  mcp-win-stdio — Windows Model Context Protocol Suite (v{__version__})")
    print("=" * 76)
    desktop_status = str(desktop_cfg) if desktop_cfg else r"Not detected (%APPDATA%\Claude)"
    cli_status = str(cli_cfg) if cli_cfg else "Not detected (~/.claude.json)"
    print(f" Single-Source Hub:      {INDALA_DIR}")
    print(f" Claude Desktop Config:  {desktop_status}")
    print(f" Claude Code CLI Config: {cli_status}")
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
    print("   mws install <server|all>   -> Install server packages from PyPI")
    print("   mws update <server|all>    -> Check & upgrade to latest PyPI version")
    print("   mws setup <server>         -> Configure Claude Desktop & Claude Code CLI")
    print("   mws uninstall <server|all> -> Cleanly remove packages & Claude configs")
    print("   mws guide <server>         -> View complete tool reference & Claude prompts")
    print("   mws doctor                 -> Run health checks (COM, Python, DB, Git)")
    print("   mws run <server>           -> Launch MCP server over stdio")
    print("   mws list                   -> List all servers and custom plugins")
    print("=" * 76 + "\n")


def cmd_list(args: argparse.Namespace) -> None:
    """List available MCP servers and installation status."""
    print_dashboard()


def cmd_guide(args: argparse.Namespace) -> None:
    """Print guide and prompt recipes for a specific server or merged for all installed servers."""
    target = (args.server or "all").lower()
    target_aliases = {
        "github": "git",
        "database": "db",
        "workspace-explorer": "explorer",
        "excel-db": "excel_db",
        "exceldb": "excel_db",
    }
    target = target_aliases.get(target, target)

    known_servers = ["git", "db", "excel", "explorer", "word", "tsc", "ssh", "rag", "excel_db"]

    def _get_guide_func(srv_name: str):
        # Look for guide function in server package or legacy guides module
        for mod_path, func_name in [
            (f"mcp_win_stdio.{srv_name}.guide", f"print_{srv_name}_guide"),
            (f"mcp_win_stdio.guides.{srv_name}_guide", f"print_{srv_name}_guide"),
        ]:
            try:
                mod = importlib.import_module(mod_path)
                fn = getattr(mod, func_name, None)
                if callable(fn):
                    return fn
            except (ImportError, ModuleNotFoundError):
                continue
        return None

    if target == "all":
        installed_count = 0
        uninstalled = []
        for srv in known_servers:
            fn = _get_guide_func(srv)
            if fn:
                fn()
                installed_count += 1
            else:
                uninstalled.append(srv)

        if uninstalled:
            print("\n" + "-" * 80)
            print("💡 Additional Uninstalled MCP Modules:")
            for u in uninstalled:
                print(f"   • mcp-win-stdio-{u:<8} -> Install with: mws install {u}")
            print("-" * 80 + "\n")
    elif target in known_servers:
        fn = _get_guide_func(target)
        if fn:
            fn()
        else:
            print(f"\n[!] Server '{target}' (mcp-win-stdio-{target}) is not currently installed.")
            print(f"    -> Run: mws install {target}")
            print(f"       (or: pip install mcp-win-stdio-{target})\n")
    else:
        print(f"Unknown server '{target}'. Known servers: {', '.join(known_servers)}.")


def cmd_install(args: argparse.Namespace) -> None:
    """Install standalone server package(s) and dependencies from PyPI."""
    target = (args.server or "").lower()

    if not target:
        if sys.stdin.isatty():
            print("\n=== 📦 mcp-win-stdio Package Installer ===")
            print("Select an MCP server package to install from PyPI:")
            print("  [1] excel     -> pip install mcp-win-stdio-excel (Pandas, OpenPyXL, RapidFuzz, Office COM)")
            print("  [2] word      -> pip install mcp-win-stdio-word (python-docx, Typography, Office COM)")
            print("  [3] explorer  -> pip install mcp-win-stdio-explorer (PathSpec, RapidFuzz, AST outlines)")
            print("  [4] tsc       -> pip install mcp-win-stdio-tsc (TypeScript diagnostic watcher)")
            print("  [5] db        -> pip install mcp-win-stdio-db (PostgreSQL & MySQL DBA manager)")
            print("  [6] git       -> pip install mcp-win-stdio-git (Local Git + GitHub CLI)")
            print("  [7] ssh       -> pip install mcp-win-stdio-ssh (Multi-host SSH, PTY, SFTP, Tunnels)")
            print("  [8] rag       -> pip install mcp-win-stdio-rag (Playwright crawler, graph trees, hybrid search)")
            print(
                "  [9] excel-db  -> pip install mcp-win-stdio-excel-db (Zero-context streaming, cross-joins, diff auditor)"
            )
            print('  [10] all      -> pip install "mcp-win-stdio[all]" (All 9 servers)')
            print("  [11] Exit")
            choice = input("\nEnter choice (1-11) [default: 10]: ").strip() or "10"
            mapping = {
                "1": "excel",
                "2": "word",
                "3": "explorer",
                "4": "tsc",
                "5": "db",
                "6": "git",
                "7": "ssh",
                "8": "rag",
                "9": "excel-db",
                "10": "all",
            }
            if choice not in mapping:
                print("Installation cancelled.")
                return
            target = mapping[choice]
        else:
            target = "all"

    selected_servers = list(BUILTIN_SERVERS.keys()) if target == "all" else [target]

    if target == "all":
        print("\n==> 🚀 Installing full suite via 'pip install \"mcp-win-stdio[all]\"'...")
        subprocess.run([sys.executable, "-m", "pip", "install", "mcp-win-stdio[all]"])
    else:
        for srv_name in selected_servers:
            srv = get_server_info(srv_name)
            if not srv:
                print(f"[ERROR] Unknown server: '{srv_name}'. Run 'mws list' to see available servers.")
                continue
            pkg = srv.get("package", f"mcp-win-stdio-{srv_name}")
            print(f"\n==> 📦 Installing '{srv['title']}' via 'pip install {pkg}'...")
            subprocess.run([sys.executable, "-m", "pip", "install", pkg])

    # Special check for git / gh system tools
    if "git" in selected_servers:
        if not shutil.which("git"):
            print("\n[MISSING] Git CLI not found on PATH.")
            print("👉 Install Git: winget install --id Git.Git -e")
            if sys.stdin.isatty():
                do_git = input("Would you like to install Git now via winget? [Y/n]: ").strip().lower()
                if do_git not in ("n", "no"):
                    subprocess.run(["winget", "install", "--id", "Git.Git", "-e"])

        name_check = subprocess.run(["git", "config", "user.name"], capture_output=True, text=True).stdout.strip()
        email_check = subprocess.run(["git", "config", "user.email"], capture_output=True, text=True).stdout.strip()
        if not name_check or not email_check:
            print("\n[WARN] Git author identity is not configured.")
            if sys.stdin.isatty():
                u_name = input(f"Enter Git author name [{name_check or 'Developer'}]: ").strip() or (
                    name_check or "Developer"
                )
                u_email = input(f"Enter Git author email [{email_check or 'developer@example.com'}]: ").strip() or (
                    email_check or "developer@example.com"
                )
                subprocess.run(["git", "config", "--global", "user.name", u_name])
                subprocess.run(["git", "config", "--global", "user.email", u_email])
                print(f"[OK] Configured Git author: {u_name} <{u_email}>")

        if not shutil.which("gh"):
            print("\n[INFO] GitHub CLI ('gh') is not installed (optional: unlocks PR, Issue, and Actions tools).")
            print("👉 Install GitHub CLI: winget install --id GitHub.cli -e")
            if sys.stdin.isatty():
                do_gh = input("Would you like to install GitHub CLI now via winget? [y/N]: ").strip().lower()
                if do_gh in ("y", "yes"):
                    subprocess.run(["winget", "install", "--id", "GitHub.cli", "-e"])

    # Check and prompt to add Python Scripts directory to Windows User PATH
    check_and_prompt_path_setup()

    print("\n✅ Installation complete! Run 'mws list' to verify status or 'mws setup <server>' to configure Claude.\n")


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
            print("  [1] excel     (44 tools: Pandas queries, RapidFuzz reconciliation, native tables, Office COM)")
            print("  [2] word      (20 tools: Multi-unit margins, typography, authoring, template filling, COM PDF)")
            print("  [3] explorer  (14 tools: Token-safe collapsible tree, .gitignore, regex grep, AST outline)")
            print("  [4] tsc       (8 tools: TypeScript diagnostic watcher, 0ms cache, fix suggestions)")
            print("  [5] db        (31 tools: Polyglot PostgreSQL & MySQL DBA manager, ERDs, diffs, locks, imports)")
            print("  [6] git       (46 tools: Local Git branching, commits, diffs, conflicts, & GitHub PRs/issues)")
            print("  [7] ssh       (34 tools: Multi-host pooling, SFTP, interactive PTY shells, background jobs)")
            print(
                "  [8] rag       (8 tools: Headless Playwright crawler, codebase indexer, hybrid BM25 + vector search)"
            )
            print(
                "  [9] excel-db  (9 tools: Zero-context streaming, master dataset audit diffs, transactional migrations)"
            )
            print("  [10] all      (Configure all 9 servers)")
            print("  [11] Exit")
            choice = input("\nEnter choice (1-11) [default: 10]: ").strip() or "10"
            mapping = {
                "1": "excel",
                "2": "word",
                "3": "explorer",
                "4": "tsc",
                "5": "db",
                "6": "git",
                "7": "ssh",
                "8": "rag",
                "9": "excel-db",
                "10": "all",
            }
            if choice not in mapping:
                print("Setup cancelled.")
                return
            target = mapping[choice]
        else:
            target = "all"

    selected_servers = list(BUILTIN_SERVERS.keys()) if target.lower() == "all" else [target.lower()]

    for srv_name in selected_servers:
        srv = get_server_info(srv_name)
        if not srv:
            print(f"\n[ERROR] Unknown server: '{srv_name}'. Run 'mws list' to see available servers.")
            continue

        print("\n" + "=" * 70)
        print(f"  Configuration Setup for: {srv['title']}")
        print("=" * 70)

        # 1. Dependency check & optional installation
        env_vars = {}
        if not srv.get("is_installed"):
            req_pip = srv.get("required_pip", [])
            print(f"\n[INFO] '{srv_name}' requires the following Python packages: {', '.join(req_pip)}")
            if sys.stdin.isatty():
                do_install = input("Would you like to install them now via pip? [Y/n]: ").strip().lower()
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
                chosen_dir = (
                    input(f"\nEnter TypeScript project directory to watch [default: {default_dir}]: ").strip()
                    or default_dir
                )
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

        # Special guidance for Git & GitHub CLI
        if srv_name == "git":
            if not shutil.which("git"):
                print("\n[MISSING] Git CLI not found on PATH.")
                print("👉 Install Git: winget install --id Git.Git -e")
                if sys.stdin.isatty():
                    do_git = input("Would you like to install Git now via winget? [Y/n]: ").strip().lower()
                    if do_git not in ("n", "no"):
                        subprocess.run(["winget", "install", "--id", "Git.Git", "-e"])

            # Check git identity
            name_check = subprocess.run(["git", "config", "user.name"], capture_output=True, text=True).stdout.strip()
            email_check = subprocess.run(["git", "config", "user.email"], capture_output=True, text=True).stdout.strip()
            if not name_check or not email_check:
                print("\n[WARN] Git author identity is not configured.")
                if sys.stdin.isatty():
                    u_name = input(f"Enter Git author name [{name_check or 'Developer'}]: ").strip() or (
                        name_check or "Developer"
                    )
                    u_email = input(f"Enter Git author email [{email_check or 'developer@example.com'}]: ").strip() or (
                        email_check or "developer@example.com"
                    )
                    subprocess.run(["git", "config", "--global", "user.name", u_name])
                    subprocess.run(["git", "config", "--global", "user.email", u_email])
                    print(f"[OK] Configured Git author: {u_name} <{u_email}>")

            if not shutil.which("gh"):
                print("\n[INFO] GitHub CLI ('gh') is not installed (optional: unlocks PR, Issue, and Actions tools).")
                print("👉 Install GitHub CLI: winget install --id GitHub.cli -e")
                if sys.stdin.isatty():
                    do_gh = input("Would you like to install GitHub CLI now via winget? [y/N]: ").strip().lower()
                    if do_gh in ("y", "yes"):
                        subprocess.run(["winget", "install", "--id", "GitHub.cli", "-e"])
            else:
                auth_res = subprocess.run(["gh", "auth", "status"], capture_output=True, text=True)
                if "Logged in to" not in (auth_res.stderr or auth_res.stdout):
                    print("\n[INFO] GitHub CLI is installed but not authenticated.")
                    print("👉 Run 'gh auth login' in your terminal to connect your GitHub account.")

        # Special setup for RAG (Playwright Chromium browser binaries)
        if srv_name == "rag":
            print("\nChecking Playwright Chromium browser binaries...")
            try:
                res = subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=False)
                if res.returncode == 0:
                    print("[OK] Playwright Chromium browser is installed and ready.")
                else:
                    print(
                        "[WARN] Could not install Playwright Chromium automatically. Run 'playwright install chromium' manually."
                    )
            except Exception as e:
                print(f"[WARN] Failed to run playwright install: {e}")

        # 2. Transparent Configuration Guidance
        snippet_dict = generate_claude_desktop_snippet(srv_name, env_vars if env_vars else None)
        snippet_json = json.dumps({srv_name: snippet_dict}, indent=2)
        cli_command = generate_claude_cli_command(srv_name, env_vars if env_vars else None)

        print("\n" + "-" * 70)
        print("📋 Claude Desktop Configuration:")
        print("File: %APPDATA%\\Claude\\claude_desktop_config.json")
        print('Add this snippet inside your "mcpServers" object:\n')
        print(snippet_json)

        print("\n" + "-" * 70)
        print("💻 Claude Code CLI Command:")
        print("Run this command in your terminal:\n")
        print(f"  {cli_command}")
        print("-" * 70)

        # 3. Optional Safe Auto-Write
        if sys.stdin.isatty():
            auto_apply = (
                input("\n👉 Would you like mws to safely write this configuration for you? [y/N]: ").strip().lower()
            )
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

    servers_to_remove = list(BUILTIN_SERVERS.keys()) if target == "all" else [target]

    for srv_name in servers_to_remove:
        print(f"\nRemoving '{srv_name}'...")
        if client in ("all", "desktop"):
            ok, msg = remove_server_from_desktop(srv_name)
            print(f"  Claude Desktop: {msg}")
        if client in ("all", "cli"):
            ok, msg = remove_server_from_cli(srv_name)
            print(f"  Claude CLI:     {msg}")


def cmd_update(args: argparse.Namespace) -> None:
    """Check PyPI for latest version and upgrade mcp-win-stdio suite or specific server."""
    target = (args.server or "all").lower()
    print(f"\n=== 🔄 mcp-win-stdio Update Manager (Current: v{__version__}) ===")

    print("Checking PyPI for latest version...")
    update_info = check_for_update(__version__, force=True)
    if update_info:
        cur, latest = update_info
        print(f"✨ New version available on PyPI: v{cur} ➔ v{latest}")
    else:
        latest = get_cached_or_latest_version(force=True)
        print(f"✅ Core CLI is on the latest version: v{__version__} (PyPI: v{latest or __version__})")

    if target == "all":
        print("\n==> 🚀 Updating full suite via 'pip install --upgrade \"mcp-win-stdio[all]\"'...")
        res = subprocess.run([sys.executable, "-m", "pip", "install", "--upgrade", "mcp-win-stdio[all]"])
    elif target in ("core", "mws", "mcp-win-stdio"):
        print("\n==> 🚀 Updating core CLI via 'pip install --upgrade mcp-win-stdio'...")
        res = subprocess.run([sys.executable, "-m", "pip", "install", "--upgrade", "mcp-win-stdio"])
    else:
        srv = get_server_info(target)
        pkg = srv.get("package", f"mcp-win-stdio-{target}") if srv else f"mcp-win-stdio-{target}"
        print(f"\n==> 🚀 Updating '{target}' via 'pip install --upgrade {pkg}'...")
        res = subprocess.run([sys.executable, "-m", "pip", "install", "--upgrade", pkg])

    if res.returncode == 0:
        print("\n✅ Update completed successfully!\n")
    else:
        print(f"\n[WARN] Update process completed with return code: {res.returncode}\n")


def cmd_uninstall(args: argparse.Namespace) -> None:
    """Cleanly uninstall MCP server package(s) and Claude configs while preserving ~/.mcp-win-stdio and mws CLI."""
    target = (args.server or "").lower()

    if not target:
        if sys.stdin.isatty():
            print("\n=== 🗑️  mcp-win-stdio Uninstaller ===")
            print("  [1] excel     -> Uninstall mcp-win-stdio-excel & remove from Claude")
            print("  [2] word      -> Uninstall mcp-win-stdio-word & remove from Claude")
            print("  [3] explorer  -> Uninstall mcp-win-stdio-explorer & remove from Claude")
            print("  [4] tsc       -> Uninstall mcp-win-stdio-tsc & remove from Claude")
            print("  [5] db        -> Uninstall mcp-win-stdio-db & remove from Claude")
            print("  [6] git       -> Uninstall mcp-win-stdio-git & remove from Claude")
            print("  [7] ssh       -> Uninstall mcp-win-stdio-ssh & remove from Claude")
            print("  [8] rag       -> Uninstall mcp-win-stdio-rag & remove from Claude")
            print("  [9] excel-db  -> Uninstall mcp-win-stdio-excel-db & remove from Claude")
            print("  [10] all      -> Uninstall all 9 MCP servers & remove from Claude (keeps mws CLI)")
            print("  [11] self     -> Uninstall mws CLI itself (mcp-win-stdio)")
            print("  [12] Exit")
            choice = input("\nEnter choice (1-12) [default: 10]: ").strip() or "10"
            mapping = {
                "1": "excel",
                "2": "word",
                "3": "explorer",
                "4": "tsc",
                "5": "db",
                "6": "git",
                "7": "ssh",
                "8": "rag",
                "9": "excel-db",
                "10": "all",
                "11": "self",
            }
            if choice not in mapping:
                print("Uninstall cancelled.")
                return
            target = mapping[choice]
        else:
            target = "all"

    known_servers = list(BUILTIN_SERVERS.keys())

    if target == "self":
        print("\n==> 🧹 Uninstalling mws CLI core package (mcp-win-stdio)...")
        ok_pip, msg_pip = uninstall_pip_packages(["mcp-win-stdio"])
        if ok_pip:
            print("[OK] mcp-win-stdio core CLI uninstalled successfully.")
        else:
            print(f"[WARN] {msg_pip}")
        print(f"🔒 Single-source hub directory PRESERVED: {INDALA_DIR}")
        return

    selected_servers = known_servers if target == "all" else [target]

    print(f"\n==> 🧹 Starting clean uninstallation for: {target}...")

    # 1. Remove from Claude Desktop and Claude Code CLI
    print("\n--- 1. Cleaning Claude Registrations ---")
    for srv_name in selected_servers:
        ok_d, msg_d = remove_server_from_desktop(srv_name)
        ok_c, msg_c = remove_server_from_cli(srv_name)
        print(f"  • {srv_name:<10} Desktop: {msg_d} | CLI: {msg_c}")

    # 2. Pip Uninstall packages (only server packages, mws CLI is preserved)
    print("\n--- 2. Removing Python Packages via pip ---")
    packages_to_remove = []
    for srv_name in selected_servers:
        srv = get_server_info(srv_name)
        pkg = srv.get("package", f"mcp-win-stdio-{srv_name}") if srv else f"mcp-win-stdio-{srv_name}"
        packages_to_remove.append(pkg)

    print(f"Packages to uninstall: {', '.join(packages_to_remove)}")
    ok_pip, msg_pip = uninstall_pip_packages(packages_to_remove)
    if ok_pip:
        print("[OK] Server packages uninstalled successfully.")
    else:
        print(f"[WARN] {msg_pip}")

    # 3. Explicitly preserve Single-Source Hub ~/.mcp-win-stdio and mws CLI
    print("\n--- 3. Single-Source Hub & CLI Status ---")
    print(f"🔒 Single-source hub directory PRESERVED: {INDALA_DIR}")
    print("   (Your custom plugins, logs, and configs in ~/.mcp-win-stdio are kept safe.)")
    print("⚙️  mws CLI PRESERVED (You can continue to use 'mws' to install servers or manage plugins.)")
    print("=" * 76)
    print("✅ Uninstallation complete!\n")


def cmd_fix_path(args: argparse.Namespace) -> None:
    """Check and automatically configure Python Scripts / bin directories in Windows User PATH."""
    print("\n=== 🧭 Windows PATH Environment Manager ===")
    candidate_dirs = get_candidate_script_dirs()
    print("Detected Python executable script & binary directories:")
    for d in candidate_dirs:
        status = "[In PATH]" if is_in_path(d) else "[MISSING from PATH]"
        print(f"  • {str(d):<65} {status}")

    missing = [d for d in candidate_dirs if not is_in_path(d) and d.exists()]
    if not missing:
        print("\n✅ All active Python script directories are already registered in your Windows PATH!\n")
        return

    added = check_and_prompt_path_setup(auto_accept=getattr(args, "yes", False))
    if added:
        print("✅ PATH environment variable updated successfully!\n")
    else:
        print("ℹ️  No changes made to PATH.\n")


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
    candidate_dirs = get_candidate_script_dirs()
    missing_dirs = [d for d in candidate_dirs if not is_in_path(d) and d.exists()]
    in_path_dirs = [d for d in candidate_dirs if is_in_path(d) and d.exists()]

    for d in in_path_dirs:
        print(f"[OK] Scripts Directory: {d} (in PATH)")
    for d in missing_dirs:
        print(f"[WARN] Scripts Directory: {d} (NOT in PATH)")
        print("       👉 Run 'mws fix-path' to add it to your Windows User PATH automatically.")

    if not candidate_dirs:
        print("[INFO] Scripts Directory: No standard scripts directory detected.")

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
        ("paramiko", "Paramiko SSH & SFTP Engine (SSH MCP)"),
        ("cryptography", "Cryptography & Key Parsing (SSH MCP)"),
        ("playwright", "Playwright Web Crawler (RAG MCP)"),
        ("networkx", "NetworkX Graph Trees (RAG MCP)"),
        ("numpy", "NumPy Matrix Arrays (RAG & Excel MCP)"),
        ("sklearn", "Scikit-Learn TF-IDF Vectors (RAG MCP)"),
        ("sqlalchemy", "SQLAlchemy Engine (Excel-DB MCP)"),
    ]
    print("\n--- Python Dependencies ---")
    for mod, desc in deps:
        try:
            importlib.import_module(mod)
            print(f"[OK] {mod:<14} : {desc}")
        except ImportError:
            print(f"[MISSING] {mod:<14} : {desc}")

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

    # 6. Version Control & GitHub CLI
    print("\n--- Version Control & GitHub CLI ---")
    git_bin = shutil.which("git")
    if git_bin:
        try:
            ver = subprocess.run(["git", "--version"], capture_output=True, text=True, check=True).stdout.strip()
            print(f"[OK] Git CLI: {ver} ({git_bin})")
        except Exception:
            print(f"[OK] Git CLI: Found at {git_bin}")

        name = subprocess.run(["git", "config", "user.name"], capture_output=True, text=True).stdout.strip()
        email = subprocess.run(["git", "config", "user.email"], capture_output=True, text=True).stdout.strip()
        if name and email:
            print(f"[OK] Git Identity: {name} <{email}>")
        else:
            print("[WARN] Git Identity: Not configured (missing user.name or user.email)")
            print('       👉 Run: git config --global user.name "Your Name"')
            print('       👉 Run: git config --global user.email "you@example.com"')
    else:
        print("[FAIL] Git CLI: Not found on PATH")
        print("       👉 Install Git: winget install --id Git.Git -e")

    gh_bin = shutil.which("gh")
    if gh_bin:
        try:
            ver_line = subprocess.run(
                ["gh", "--version"], capture_output=True, text=True, check=True
            ).stdout.splitlines()[0]
            print(f"[OK] GitHub CLI: {ver_line} ({gh_bin})")
        except Exception:
            print(f"[OK] GitHub CLI: Found at {gh_bin}")

        auth_res = subprocess.run(
            ["gh", "auth", "status"], capture_output=True, text=True, encoding="utf-8", errors="replace"
        )
        auth_out = auth_res.stderr or auth_res.stdout
        if "Logged in to" in auth_out:
            first_account = [ln.strip() for ln in auth_out.splitlines() if "Logged in to" in ln]
            account_str = first_account[0] if first_account else "Active"
            account_str = account_str.replace("✓", "").replace("âœ“", "").strip()
            print(f"[OK] GitHub Auth: Logged in ({account_str})")
        else:
            print("[INFO] GitHub Auth: Not logged in (Run 'gh auth login' to connect)")
    else:
        print("[INFO] GitHub CLI: Not installed (optional: winget install --id GitHub.cli -e)")

    # 7. SSH Environment & Hosts
    print("\n--- SSH Environment & Hosts ---")
    ssh_bin = shutil.which("ssh")
    print(
        f"[{'OK' if ssh_bin else 'INFO'}] OpenSSH Client: {ssh_bin or 'Not found on PATH (Paramiko built-in client active)'}"
    )
    ssh_dir = Path.home() / ".ssh"
    if ssh_dir.is_dir():
        keys = [f.name for f in ssh_dir.iterdir() if f.is_file() and not f.name.endswith(".pub") and "id_" in f.name]
        print(f"[OK] SSH Config Directory: {ssh_dir} ({len(keys)} private keys found)")
    else:
        print(f"[INFO] SSH Config Directory: {ssh_dir} (empty/not yet created)")

    try:
        from mcp_win_stdio.ssh.connection import get_active_host_name, get_all_registered_hosts

        ssh_hosts = get_all_registered_hosts()
        active_ssh = get_active_host_name()
        print(
            f"[OK] Registered SSH Hosts: {len(ssh_hosts)} host{'s' if len(ssh_hosts) != 1 else ''} (Active: {active_ssh or 'None'})"
        )
    except Exception:
        pass

    # 8. Web Documentation Crawler (Playwright Browser Binaries)
    print("\n--- Documentation Crawler & Browser Engine ---")
    try:
        import playwright

        ms_playwright_dir = Path.home() / "AppData" / "Local" / "ms-playwright"
        chrome_shells = (
            list(ms_playwright_dir.glob("**/chrome-headless-shell.exe")) if ms_playwright_dir.exists() else []
        )
        chrome_bins = list(ms_playwright_dir.glob("**/chrome.exe")) if ms_playwright_dir.exists() else []
        if chrome_shells or chrome_bins:
            chosen = chrome_shells[0] if chrome_shells else chrome_bins[0]
            print(f"[OK] Playwright Chromium Browser: Ready ({chosen})")
        else:
            print("[WARN] Playwright Chromium Browser: Not downloaded")
            print("       👉 Run: playwright install chromium (or mws install rag)")
    except ImportError:
        print("[INFO] Playwright Browser Engine: Playwright not installed")

    # 9. Claude Config Files

    print("\n--- Claude Configuration Targets ---")
    desktop_cfg = get_claude_desktop_config_path()
    if desktop_cfg and desktop_cfg.exists():
        print(f"[OK] Claude Desktop: {desktop_cfg}")
    else:
        desktop_str = str(desktop_cfg) if desktop_cfg else r"Not found in %APPDATA%\Claude"
        print(f"[INFO] Claude Desktop config: {desktop_str}")

    cli_cfg = get_claude_cli_config_path()
    if cli_cfg and cli_cfg.exists():
        print(f"[OK] Claude Code CLI: {cli_cfg}")
    else:
        cli_str = str(cli_cfg) if cli_cfg else "Not found in ~/.claude.json"
        print(f"[INFO] Claude Code CLI config: {cli_str}")

    # 8. PyPI Version & Update Status
    print("\n--- PyPI Version & Update Status ---")
    update_info = check_for_update(__version__, force=True)
    if update_info:
        cur, latest = update_info
        print(f"[WARN] New version available on PyPI: v{cur} ➔ v{latest}")
        print("       👉 Run 'mws update' or 'pip install --upgrade mcp-win-stdio' to upgrade.")
    else:
        latest = get_cached_or_latest_version(force=True)
        print(f"[OK] mcp-win-stdio is up to date: v{__version__} (PyPI: v{latest or __version__})")

    print("\nDiagnostic complete.\n")


ALL_BUILTIN_SERVERS = ["rag", "excel-db", "excel", "db", "explorer", "git", "ssh", "tsc", "word"]


def get_server_agents_guide(servers: List[str]) -> str:
    """Generate tailored AGENTS.md markdown guide for specific active servers."""
    lines = [
        "# Repository Agent Guidelines",
        "",
        "This repository is equipped with the **mcp-win-stdio (`mws`)** tool suite.",
        "",
        "## 🛠️ Active Tools & Recommended Selection",
        "",
    ]
    guide_map = {
        "db": "* **Database Operations:** Use `db` MCP (`read_query`, `execute_query`, `describe_table`).",
        "excel": "* **Spreadsheets & Excel:** Use `excel` MCP (`preview_sheet`, `update_cells`, `profile_sheet`).",
        "excel-db": "* **High-Speed Pipelines & Streaming:** Use `excel-db` MCP (`db_to_excel_stream`, `excel_to_db_upsert`, `query_unified_sources`, `reconcile_db_vs_excel`).",
        "rag": "* **Documentation & Web RAG:** Use `rag` MCP (`crawl_and_index_url`, `query_knowledge_base`, `get_knowledge_tree`).",
        "explorer": "* **Code Navigation:** Use `explorer` MCP (`get_directory_tree`, `fuzzy_find`, `grep_search`).",
        "git": "* **Git & PRs:** Use `git` MCP for status, diffs, commits, and GitHub API interactions.",
        "ssh": "* **Remote Shells:** Use `ssh` MCP for multi-host pooling and SFTP.",
        "tsc": "* **TypeScript:** Use `tsc` MCP for 0ms compiler diagnostic checks.",
        "word": "* **Word Documents:** Use `word` MCP for typography, layout, and document generation.",
    }
    for s in servers:
        s_norm = s.lower().strip()
        if s_norm in guide_map:
            lines.append(guide_map[s_norm])
    lines.append("")
    return "\n".join(lines)


def _build_server_entry(s_name: str, is_vscode: bool, cwd: Path) -> Dict[str, Any]:
    """Build smart MCP server config entry with appropriate environment variables for the target client."""
    entry: Dict[str, Any] = {"command": "mws", "args": ["run", s_name]}
    env: Dict[str, str] = {}

    # 1. TypeScript Compiler Watch Directory
    if s_name == "tsc":
        env["TSC_WATCH_DIR"] = "${workspaceFolder}" if is_vscode else str(cwd)

    # 2. Explorer Workspace Root
    elif s_name == "explorer":
        env["EXPLORER_ROOT"] = "${workspaceFolder}" if is_vscode else str(cwd)

    # 3. Local SQLite database auto-detection
    elif s_name in ("db", "excel-db"):
        try:
            sqlite_candidates = [f for f in cwd.glob("*.db") if f.is_file()] + [
                f for f in cwd.glob("*.sqlite*") if f.is_file()
            ]
            if sqlite_candidates:
                first_db = sqlite_candidates[0]
                rel_sql = str(first_db.relative_to(cwd)).replace("\\", "/")
                env["SQLITE_DATABASE"] = f"${{workspaceFolder}}/{rel_sql}" if is_vscode else str(first_db)
        except Exception:
            pass

    if env:
        entry["env"] = env

    return entry


def setup_project_mcp(
    servers: List[str], target_dir: Optional[Path] = None, overwrite: bool = False, clean_deprecated_vscode: bool = True
) -> Dict[str, Any]:
    """
    Write or update root .mcp.json and AGENTS.md in target directory with smart client environment variables.
    Handles migration and cleanup from deprecated .vscode/mcp.json (deprecated in VS Code 1.106+).
    """
    cwd = target_dir or Path.cwd()
    root_file = cwd / ".mcp.json"
    vscode_file = cwd / ".vscode" / "mcp.json"

    # Read existing configurations if updating
    existing_servers: Dict[str, Any] = {}
    if not overwrite and root_file.exists():
        try:
            with open(root_file, "r", encoding="utf-8") as f:
                existing_servers = json.load(f).get("mcpServers", {})
        except Exception:
            pass

    # Check for legacy .vscode/mcp.json to migrate servers
    migrated_from_legacy = False
    if vscode_file.exists():
        try:
            with open(vscode_file, "r", encoding="utf-8") as f:
                legacy_servers = json.load(f).get("mcpServers", {})
                for k, v in legacy_servers.items():
                    if k not in existing_servers or overwrite:
                        existing_servers[k] = v
                        migrated_from_legacy = True
        except Exception:
            pass

        # Clean up deprecated .vscode/mcp.json if requested to avoid VS Code 1.106+ warnings
        if clean_deprecated_vscode:
            try:
                vscode_file.unlink()
                vscode_dir = vscode_file.parent
                if vscode_dir.exists() and not any(vscode_dir.iterdir()):
                    vscode_dir.rmdir()
            except Exception:
                pass

    for s in servers:
        s_norm = s.lower().strip()
        if s_norm:
            existing_servers[s_norm] = _build_server_entry(s_norm, is_vscode=True, cwd=cwd)

    # 1. Root .mcp.json
    with open(root_file, "w", encoding="utf-8") as f:
        json.dump({"mcpServers": existing_servers}, f, indent=2)

    # 2. Antigravity workspace agent (.agents/mcp_config.json)
    try:
        agents_dir = cwd / ".agents"
        agents_dir.mkdir(parents=True, exist_ok=True)
        agents_mcp_file = agents_dir / "mcp_config.json"
        with open(agents_mcp_file, "w", encoding="utf-8") as f:
            json.dump({"mcpServers": existing_servers}, f, indent=2)
    except Exception:
        pass

    # 3. Agent guidelines (AGENTS.md and GEMINI.md)
    content = get_server_agents_guide(list(existing_servers.keys()))
    agents_md = cwd / "AGENTS.md"
    with open(agents_md, "w", encoding="utf-8") as f:
        f.write(content)

    gemini_md = cwd / "GEMINI.md"
    try:
        with open(gemini_md, "w", encoding="utf-8") as f:
            f.write(content)
    except Exception:
        pass

    return {
        "cwd": cwd,
        "servers": list(existing_servers.keys()),
        "migrated_from_legacy_vscode": migrated_from_legacy,
        "config_file": str(root_file),
    }


def remove_project_mcp(servers: List[str], target_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Remove server(s) from .mcp.json, clean up any legacy .vscode/mcp.json, and refresh AGENTS.md / GEMINI.md."""
    cwd = target_dir or Path.cwd()
    root_file = cwd / ".mcp.json"
    vscode_file = cwd / ".vscode" / "mcp.json"

    existing_servers: Dict[str, Any] = {}
    if root_file.exists():
        try:
            with open(root_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                existing_servers = data.get("mcpServers", {})
        except Exception:
            pass

    for s in servers:
        s_norm = s.lower().strip()
        existing_servers.pop(s_norm, None)

    mcp_config = {"mcpServers": existing_servers}

    with open(root_file, "w", encoding="utf-8") as f:
        json.dump(mcp_config, f, indent=2)

    try:
        agents_mcp_file = cwd / ".agents" / "mcp_config.json"
        if agents_mcp_file.exists():
            with open(agents_mcp_file, "w", encoding="utf-8") as f:
                json.dump(mcp_config, f, indent=2)
    except Exception:
        pass

    if vscode_file.exists():
        try:
            vscode_file.unlink()
            if vscode_file.parent.exists() and not any(vscode_file.parent.iterdir()):
                vscode_file.parent.rmdir()
        except Exception:
            pass

    agents_md = cwd / "AGENTS.md"
    content = get_server_agents_guide(list(existing_servers.keys()))
    with open(agents_md, "w", encoding="utf-8") as f:
        f.write(content)

    gemini_md = cwd / "GEMINI.md"
    try:
        with open(gemini_md, "w", encoding="utf-8") as f:
            f.write(content)
    except Exception:
        pass

    return {"cwd": cwd, "servers": list(existing_servers.keys()), "config_file": str(root_file)}


CLIENT_ALIASES = {
    "antigravity": "antigravity",
    "gemini": "antigravity",
    "agy": "antigravity",
    "claude": "claude",
    "claude-desktop": "claude",
    "claude-code": "claude",
    "copilot": "copilot",
    "vscode": "copilot",
    "code": "copilot",
    "github-copilot": "copilot",
    "cursor": "cursor",
    "windsurf": "windsurf",
    "all": "all",
}


def _get_active_python_server_entries(servers: List[str], cwd: Path) -> Dict[str, Any]:
    """Build Python executable server entries for desktop GUI apps."""
    py_exe = sys.executable.replace("\\", "/")
    res = {}
    for s in servers:
        s_norm = s.lower().strip()
        mod_name = s_norm.replace("-", "_")
        entry: Dict[str, Any] = {"command": py_exe, "args": ["-m", f"mcp_win_stdio.{mod_name}"]}
        env: Dict[str, str] = {}
        if s_norm == "tsc":
            env["TSC_WATCH_DIR"] = str(cwd)
        elif s_norm == "explorer":
            env["EXPLORER_ROOT"] = str(cwd)
        elif s_norm in ("db", "excel-db"):
            servers_env = os.environ.get("SERVERS")
            if servers_env:
                env["SERVERS"] = servers_env
            else:
                env["SERVERS"] = '{"showreel_dev": "postgresql://postgres:postgres@localhost:5432/showreel_dev"}'
        if env:
            entry["env"] = env
        res[s_norm] = entry
    return res


def init_antigravity(servers: List[str], cwd: Path) -> Dict[str, Any]:
    """Initialize Antigravity MCP configurations (global ~/.gemini/config and workspace .agents)."""
    updated_files = []
    gemini_dir = Path.home() / ".gemini"
    gemini_cfg_dir = gemini_dir / "config"
    gemini_cfg_dir.mkdir(parents=True, exist_ok=True)
    gemini_cfg_file = gemini_cfg_dir / "mcp_config.json"

    existing: Dict[str, Any] = {}
    if gemini_cfg_file.exists():
        try:
            with open(gemini_cfg_file, "r", encoding="utf-8") as f:
                existing = json.load(f)
        except Exception:
            existing = {}

    mcp_servers = existing.setdefault("mcpServers", {})
    py_servers = _get_active_python_server_entries(servers, cwd)
    for s_name, s_entry in py_servers.items():
        if s_name in mcp_servers:
            if "env" in mcp_servers[s_name] and "env" in s_entry:
                s_entry["env"].update(mcp_servers[s_name]["env"])
        mcp_servers[s_name] = s_entry

    mcp_servers.pop("excel_db", None)

    with open(gemini_cfg_file, "w", encoding="utf-8") as f:
        json.dump(existing, f, indent=2)
    updated_files.append(str(gemini_cfg_file))

    # Workspace project configuration
    proj_res = setup_project_mcp(servers, target_dir=cwd, overwrite=False)
    updated_files.append(proj_res["config_file"])
    agents_cfg = cwd / ".agents" / "mcp_config.json"
    if agents_cfg.exists():
        updated_files.append(str(agents_cfg))
    updated_files.append(str(cwd / "AGENTS.md"))
    updated_files.append(str(cwd / "GEMINI.md"))

    local_app_ide = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Antigravity IDE"
    detected = gemini_dir.exists() or local_app_ide.exists()

    return {
        "client": "Antigravity",
        "detected": detected,
        "status": "Configured",
        "primary_config": str(gemini_cfg_file),
        "files_updated": updated_files,
        "servers_count": len(servers),
    }


def init_claude(servers: List[str], cwd: Path) -> Dict[str, Any]:
    """Initialize Claude Desktop (%APPDATA%\\Claude) and Claude Code (~/.claude.json)."""
    updated_files = []
    appdata = Path(os.environ.get("APPDATA", ""))
    claude_dir = appdata / "Claude"
    claude_code_file = Path.home() / ".claude.json"
    detected = claude_dir.exists() or claude_code_file.exists() or bool(shutil.which("claude"))

    claude_dir.mkdir(parents=True, exist_ok=True)
    claude_cfg = claude_dir / "claude_desktop_config.json"
    existing: Dict[str, Any] = {}
    if claude_cfg.exists():
        try:
            with open(claude_cfg, "r", encoding="utf-8") as f:
                existing = json.load(f)
        except Exception:
            existing = {}

    mcp_servers = existing.setdefault("mcpServers", {})
    py_servers = _get_active_python_server_entries(servers, cwd)
    for s_name, s_entry in py_servers.items():
        if s_name in mcp_servers:
            if "env" in mcp_servers[s_name] and "env" in s_entry:
                s_entry["env"].update(mcp_servers[s_name]["env"])
        mcp_servers[s_name] = s_entry

    mcp_servers.pop("excel_db", None)

    with open(claude_cfg, "w", encoding="utf-8") as f:
        json.dump(existing, f, indent=2)
    updated_files.append(str(claude_cfg))

    if claude_code_file.exists() or (Path.home() / ".claude").exists() or shutil.which("claude"):
        code_data: Dict[str, Any] = {}
        if claude_code_file.exists():
            try:
                with open(claude_code_file, "r", encoding="utf-8") as f:
                    code_data = json.load(f)
            except Exception:
                code_data = {}
        c_servers = code_data.setdefault("mcpServers", {})
        for s_name, s_entry in py_servers.items():
            c_servers[s_name] = s_entry
        c_servers.pop("excel_db", None)
        with open(claude_code_file, "w", encoding="utf-8") as f:
            json.dump(code_data, f, indent=2)
        updated_files.append(str(claude_code_file))

    setup_project_mcp(servers, target_dir=cwd, overwrite=False)

    return {
        "client": "Claude (Desktop & CLI)",
        "detected": detected,
        "status": "Configured",
        "primary_config": str(claude_cfg),
        "files_updated": updated_files,
        "servers_count": len(servers),
    }


def init_copilot(servers: List[str], cwd: Path) -> Dict[str, Any]:
    """Initialize GitHub Copilot (VS Code ~/.copilot, %APPDATA%\\Code\\User, and workspace .mcp.json)."""
    updated_files = []
    code_dir = Path(os.environ.get("APPDATA", "")) / "Code"
    copilot_home = Path.home() / ".copilot"
    detected = (
        code_dir.exists()
        or copilot_home.exists()
        or bool(shutil.which("code"))
        or bool(shutil.which("code.cmd"))
        or bool(shutil.which("gh"))
    )

    copilot_home.mkdir(parents=True, exist_ok=True)
    copilot_cfg = copilot_home / "mcp-config.json"
    existing: Dict[str, Any] = {}
    if copilot_cfg.exists():
        try:
            with open(copilot_cfg, "r", encoding="utf-8") as f:
                existing = json.load(f)
        except Exception:
            existing = {}
    mcp_servers = existing.setdefault("mcpServers", {})
    py_servers = _get_active_python_server_entries(servers, cwd)
    for s_name, s_entry in py_servers.items():
        mcp_servers[s_name] = s_entry
    mcp_servers.pop("excel_db", None)
    with open(copilot_cfg, "w", encoding="utf-8") as f:
        json.dump(existing, f, indent=2)
    updated_files.append(str(copilot_cfg))

    code_user = code_dir / "User"
    if code_user.exists():
        code_mcp_cfg = code_user / "mcp.json"
        with open(code_mcp_cfg, "w", encoding="utf-8") as f:
            json.dump({"mcpServers": mcp_servers}, f, indent=2)
        updated_files.append(str(code_mcp_cfg))

    proj_res = setup_project_mcp(servers, target_dir=cwd, overwrite=False)
    updated_files.append(proj_res["config_file"])

    return {
        "client": "GitHub Copilot (VS Code)",
        "detected": detected,
        "status": "Configured",
        "primary_config": str(copilot_cfg),
        "files_updated": updated_files,
        "servers_count": len(servers),
    }


def init_cursor(servers: List[str], cwd: Path) -> Dict[str, Any]:
    """Initialize Cursor AI editor MCP configuration."""
    updated_files = []
    cursor_dir = Path(os.environ.get("APPDATA", "")) / "Cursor"
    cursor_home = Path.home() / ".cursor"
    detected = cursor_dir.exists() or cursor_home.exists() or bool(shutil.which("cursor"))

    if cursor_dir.exists():
        target_cfg = cursor_dir / "User" / "mcp.json"
        target_cfg.parent.mkdir(parents=True, exist_ok=True)
    else:
        cursor_home.mkdir(parents=True, exist_ok=True)
        target_cfg = cursor_home / "mcp.json"

    py_servers = _get_active_python_server_entries(servers, cwd)
    with open(target_cfg, "w", encoding="utf-8") as f:
        json.dump({"mcpServers": py_servers}, f, indent=2)
    updated_files.append(str(target_cfg))

    setup_project_mcp(servers, target_dir=cwd, overwrite=False)
    return {
        "client": "Cursor",
        "detected": detected,
        "status": "Configured",
        "primary_config": str(target_cfg),
        "files_updated": updated_files,
        "servers_count": len(servers),
    }


def init_windsurf(servers: List[str], cwd: Path) -> Dict[str, Any]:
    """Initialize Codeium Windsurf MCP configuration."""
    updated_files = []
    windsurf_home = Path.home() / ".codeium" / "windsurf"
    appdata_windsurf = Path(os.environ.get("APPDATA", "")) / "Windsurf"
    detected = windsurf_home.exists() or appdata_windsurf.exists() or bool(shutil.which("windsurf"))

    windsurf_home.mkdir(parents=True, exist_ok=True)
    target_cfg = windsurf_home / "mcp_config.json"
    py_servers = _get_active_python_server_entries(servers, cwd)
    with open(target_cfg, "w", encoding="utf-8") as f:
        json.dump({"mcpServers": py_servers}, f, indent=2)
    updated_files.append(str(target_cfg))

    setup_project_mcp(servers, target_dir=cwd, overwrite=False)
    return {
        "client": "Windsurf",
        "detected": detected,
        "status": "Configured",
        "primary_config": str(target_cfg),
        "files_updated": updated_files,
        "servers_count": len(servers),
    }


def init_all_clients(servers: List[str], cwd: Path) -> List[Dict[str, Any]]:
    """Auto-detect all AI clients installed on the system and configure them all."""
    results = []
    client_handlers = [
        ("antigravity", init_antigravity),
        ("claude", init_claude),
        ("copilot", init_copilot),
        ("cursor", init_cursor),
        ("windsurf", init_windsurf),
    ]

    for _, handler in client_handlers:
        res = handler(servers, cwd)
        results.append(res)

    return results


def cmd_init_project(args: argparse.Namespace) -> None:
    """Initialize MCP configuration for specific AI client (antigravity, claude, copilot, all) or project repository."""
    raw_targets = getattr(args, "targets", []) or getattr(args, "servers", [])
    cwd = Path.cwd()
    avail = list_available_servers()
    installed_servers = [name for name, info in avail.items() if info.get("is_installed", False)]
    active_servers = installed_servers if installed_servers else list(BUILTIN_SERVERS.keys())

    # Check if any target is a recognized client
    client_tokens = [CLIENT_ALIASES[t.lower()] for t in raw_targets if t.lower() in CLIENT_ALIASES]
    server_tokens = [t.lower() for t in raw_targets if t.lower() not in CLIENT_ALIASES]

    selected_servers = server_tokens if server_tokens else active_servers

    if "all" in client_tokens or raw_targets == ["all"]:
        # User requested 'mws init all' -> scan system, init all detected clients!
        print(f"\n🚀 Initializing mws MCP suite across all system clients & project: {cwd}\n")
        results = init_all_clients(selected_servers, cwd)
        print("=" * 86)
        print(f" {'CLIENT':<26} {'DETECTED':<12} {'STATUS':<14} {'PRIMARY CONFIG'}")
        print("-" * 86)
        for r in results:
            det = "[Yes]" if r["detected"] else "[No]"
            stat = f"[{r['status']}]" if r["detected"] else "[Skipped]"
            cfg = r["primary_config"] if r["detected"] else "Not detected on system"
            print(f" {r['client']:<26} {det:<12} {stat:<14} {cfg}")
        print("=" * 86)
        print(f"\n✅ Workspace Project Initialized ({len(selected_servers)} servers):")
        print("   • .mcp.json (Unified standard for VS Code 1.106+, Copilot, Antigravity, Cursor)")
        print("   • .agents/mcp_config.json (Antigravity workspace agent)")
        print("   • AGENTS.md & GEMINI.md (Agent pair-programming guidelines)\n")
        return

    elif client_tokens:
        # User specified specific client(s), e.g. 'mws init antigravity', 'mws init copilot'
        client_dispatch = {
            "antigravity": init_antigravity,
            "claude": init_claude,
            "copilot": init_copilot,
            "cursor": init_cursor,
            "windsurf": init_windsurf,
        }
        for c in client_tokens:
            handler = client_dispatch.get(c)
            if handler:
                res = handler(selected_servers, cwd)
                status_icon = "✅" if res["detected"] else "ℹ️"
                print(f"\n{status_icon} Initialized MCP configuration for {res['client']}:")
                print(f"   • Primary Config: {res['primary_config']}")
                print(f"   • Active Servers ({res['servers_count']}): {', '.join(selected_servers)}")
                print(f"   • Workspace: {cwd}")
                print(f"   • Detected on system: {'Yes' if res['detected'] else 'No (configuration created)'}")
                for f_path in res["files_updated"]:
                    print(f"     -> {f_path}")
        print()
        return

    else:
        # Default project initialization: .mcp.json, .agents/mcp_config.json, AGENTS.md, GEMINI.md
        result = setup_project_mcp(selected_servers, overwrite=True)
        configured = ", ".join(result["servers"])
        print(f"\n✅ Successfully initialized mws auto-configuration in: {cwd}")
        print(f"   • Active Servers ({len(result['servers'])}): {configured}")
        print("   • Created: .mcp.json (Unified standard for VS Code 1.106+, Copilot, Antigravity, Cursor)")
        print("   • Created: .agents/mcp_config.json (Antigravity workspace agent)")
        if result.get("migrated_from_legacy_vscode"):
            print("   • Migrated & cleaned: Deprecated .vscode/mcp.json (VS Code 1.106+ deprecation)")
        print("   • Created: AGENTS.md & GEMINI.md (Tailored AI Agent tool guidelines)\n")


def cmd_setup_project(args: argparse.Namespace) -> None:
    """Add specific MCP server(s) to the current repository configuration."""
    targets = args.servers
    if not targets:
        print("Error: Specify at least one server to add (e.g. 'mws setup-project excel db').", file=sys.stderr)
        sys.exit(1)

    result = setup_project_mcp(targets, overwrite=False)
    cwd = result["cwd"]
    configured = ", ".join(result["servers"])

    print(f"\n✅ Added server(s) {targets} to project: {cwd}")
    print(f"   • Total Active Servers ({len(result['servers'])}): {configured}")
    print("   • Updated: .mcp.json (Unified standard for VS Code 1.106+, Antigravity, Claude Code, Cursor)")
    if result.get("migrated_from_legacy_vscode"):
        print("   • Migrated & cleaned: Deprecated .vscode/mcp.json (VS Code 1.106+ deprecation)")
    print("   • Updated: AGENTS.md\n")


def cmd_remove_project(args: argparse.Namespace) -> None:
    """Remove specific MCP server(s) from the current repository configuration."""
    targets = args.servers
    if not targets:
        print("Error: Specify at least one server to remove (e.g. 'mws remove-project excel').", file=sys.stderr)
        sys.exit(1)

    result = remove_project_mcp(targets)
    cwd = result["cwd"]
    configured = ", ".join(result["servers"]) if result["servers"] else "None"

    print(f"\n✅ Removed server(s) {targets} from project: {cwd}")
    print(f"   • Remaining Active Servers ({len(result['servers'])}): {configured}")
    print("   • Updated: .mcp.json")
    print("   • Updated: AGENTS.md\n")


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
    sub_guide.add_argument(
        "server",
        nargs="?",
        default="all",
        help="Server name ('excel', 'word', 'explorer', 'tsc', 'db', 'git', 'ssh', 'rag', 'excel-db', 'all')",
    )
    sub_guide.set_defaults(func=cmd_guide)

    # install
    sub_install = subparsers.add_parser("install", help="Install standalone MCP server package(s) from PyPI")
    sub_install.add_argument(
        "server",
        nargs="?",
        default=None,
        help="Server package to install ('excel', 'word', 'explorer', 'tsc', 'db', 'git', 'ssh', 'rag', 'excel-db', 'all')",
    )
    sub_install.set_defaults(func=cmd_install)

    # update / upgrade
    sub_update = subparsers.add_parser(
        "update", aliases=["upgrade"], help="Check PyPI and upgrade mcp-win-stdio suite or specific server"
    )
    sub_update.add_argument(
        "server",
        nargs="?",
        default="all",
        help="Server or 'all' to update ('excel', 'word', 'explorer', 'tsc', 'db', 'git', 'ssh', 'rag', 'excel-db', 'all')",
    )
    sub_update.set_defaults(func=cmd_update)

    # setup
    sub_setup = subparsers.add_parser("setup", help="Configure server(s) into Claude Desktop and CLI")
    sub_setup.add_argument(
        "server",
        nargs="?",
        default=None,
        help="Server to configure ('excel', 'word', 'explorer', 'tsc', 'db', 'git', 'ssh', 'rag', 'excel-db', 'all')",
    )
    sub_setup.add_argument("--client", "-c", choices=["all", "desktop", "cli"], default="all", help="Target client")
    sub_setup.set_defaults(func=cmd_setup)

    # setup-project / add-project / add
    sub_setup_proj = subparsers.add_parser(
        "setup-project",
        aliases=["add-project", "add"],
        help="Add specific MCP server(s) to current project (.mcp.json, AGENTS.md)",
    )
    sub_setup_proj.add_argument("servers", nargs="+", help="Server name(s) to add (e.g. 'excel', 'db', 'tsc')")
    sub_setup_proj.set_defaults(func=cmd_setup_project)

    # remove-project
    sub_rm_proj = subparsers.add_parser("remove-project", help="Remove specific MCP server(s) from current project")
    sub_rm_proj.add_argument("servers", nargs="+", help="Server name(s) to remove (e.g. 'excel', 'word')")
    sub_rm_proj.set_defaults(func=cmd_remove_project)

    # remove
    sub_remove = subparsers.add_parser("remove", help="Remove server(s) from Claude Desktop and CLI")
    sub_remove.add_argument(
        "server",
        help="Server to remove ('excel', 'word', 'explorer', 'tsc', 'db', 'git', 'ssh', 'rag', 'excel-db', 'all')",
    )
    sub_remove.add_argument("--client", "-c", choices=["all", "desktop", "cli"], default="all", help="Target client")
    sub_remove.set_defaults(func=cmd_remove)

    # uninstall
    sub_uninstall = subparsers.add_parser(
        "uninstall", help="Uninstall MCP server(s) & clean Claude configs while preserving ~/.mcp-win-stdio"
    )
    sub_uninstall.add_argument(
        "server",
        nargs="?",
        default=None,
        help="Server to uninstall ('excel', 'word', 'explorer', 'tsc', 'db', 'git', 'ssh', 'rag', 'excel-db', 'all')",
    )
    sub_uninstall.set_defaults(func=cmd_uninstall)

    # run
    sub_run = subparsers.add_parser("run", help="Launch an MCP server over stdio for Claude")
    sub_run.add_argument("server", help="Server name to launch ('excel', 'word', 'explorer', 'tsc', or custom plugin)")
    sub_run.set_defaults(func=cmd_run)

    # doctor
    sub_doctor = subparsers.add_parser("doctor", help="Check system health, dependencies, and COM readiness")
    sub_doctor.set_defaults(func=cmd_doctor)

    # init-project / init
    sub_init = subparsers.add_parser(
        "init-project",
        aliases=["init"],
        help="Initialize MCP configuration for specific AI client (antigravity, claude, copilot, all) or project (.mcp.json, AGENTS.md)",
    )
    sub_init.add_argument(
        "targets",
        nargs="*",
        default=[],
        help="Target AI client ('antigravity', 'claude', 'copilot', 'cursor', 'windsurf', 'all') or server names ('excel', 'db'). If omitted or 'all', auto-detects all installed clients.",
    )
    sub_init.set_defaults(func=cmd_init_project)

    # fix-path / path
    sub_path = subparsers.add_parser(
        "fix-path", aliases=["path"], help="Check and configure Python Scripts directory in Windows User PATH"
    )
    sub_path.add_argument(
        "--yes", "-y", action="store_true", help="Automatically accept adding missing directories to PATH"
    )
    sub_path.set_defaults(func=cmd_fix_path)

    # Support alternate command syntax: `mws git guide` -> `mws guide git` or `mws db run` -> `mws run db`
    known_srvs = {
        "git",
        "github",
        "db",
        "database",
        "excel",
        "word",
        "explorer",
        "workspace-explorer",
        "tsc",
        "rag",
        "excel-db",
        "excel_db",
        "ssh",
        "antigravity",
        "claude",
        "copilot",
        "cursor",
        "windsurf",
        "all",
    }
    known_cmds = {
        "guide",
        "run",
        "setup",
        "setup-project",
        "add",
        "add-project",
        "remove-project",
        "doctor",
        "remove",
        "install",
        "update",
        "upgrade",
        "uninstall",
        "fix-path",
        "path",
        "init",
        "init-project",
    }
    if len(sys.argv) >= 3 and sys.argv[1].lower() in known_srvs and sys.argv[2].lower() in known_cmds:
        srv_token = sys.argv[1].lower()
        cmd_token = sys.argv[2].lower()
        sys.argv = [sys.argv[0], cmd_token, srv_token] + sys.argv[3:]

    args = parser.parse_args()
    if not args.command:
        # Default action when run with no arguments: show interactive dashboard
        print_dashboard()
        sys.exit(0)

    args.func(args)


if __name__ == "__main__":
    main()
