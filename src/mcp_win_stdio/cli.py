"""
mcp-win-stdio CLI: Windows-optimized Model Context Protocol suite orchestrator.
"""

import argparse
import getpass
import importlib
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Ensure Windows console uses UTF-8 without crashing on cp1252
if sys.platform == "win32":
    try:
        if hasattr(sys.stdout, "reconfigure"):
            getattr(sys.stdout, "reconfigure")(encoding="utf-8", errors="replace")
        if hasattr(sys.stderr, "reconfigure"):
            getattr(sys.stderr, "reconfigure")(encoding="utf-8", errors="replace")
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
from mcp_win_stdio.core.clients import (
    SUPPORTED_CLIENTS,
    generate_snippet,
    get_actual_windows_paths,
    get_all_clients,
    resolve_client,
)
from mcp_win_stdio.core.config import USER_DIR, ensure_workspace_dirs
from mcp_win_stdio.core.dialogs import prompt_path_or_dialog
from mcp_win_stdio.core.discovery import BUILTIN_SERVERS, get_server_info, list_available_servers
from mcp_win_stdio.core.environment import (
    check_and_prompt_path_setup,
    get_candidate_script_dirs,
    is_in_path,
)
from mcp_win_stdio.core.external_updater import spawn_external_updater
from mcp_win_stdio.core.installer import (
    cleanup_old_executables,
    generate_claude_cli_command,
    generate_claude_desktop_snippet,
    get_claude_cli_config_path,
    get_claude_desktop_config_path,
    get_installed_mws_packages,
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

    # Check for PyPI updates (fast/cached)
    update_info = check_for_update(__version__)
    if update_info:
        cur, latest = update_info
        print("\n" + format_update_banner(cur, latest))

    # Check if Python Scripts directory is missing from PATH and prompt user
    check_and_prompt_path_setup()

    print("\n" + "=" * 76)
    print(f"   🚀  mcp-win-stdio — Universal Windows MCP Suite (v{__version__})")
    print("=" * 76)
    print(f" Single-Source Hub:      {USER_DIR}")
    print(" Supported AI Clients:   Gemini / Antigravity, Claude Desktop & Code,")
    print("                         ChatGPT, Cursor, Kiro, OpenCode, Windsurf,")
    print("                         GitHub Copilot, OpenAI Codex")
    print(" Architecture:           Non-invasive (zero automatic config file mutations)")
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
    print(" 🛠️  Quick Commands:")
    print("   mws guide [server] [client] -> Copy-paste configs & instructions for any agent")
    print("   mws server                 -> Run Unified Gateway MCP over stdio (ALL 220+ tools)")
    print("   mws run <server>           -> Launch individual MCP server over stdio")
    print("   mws config [db|ssh|tsc]    -> Interactive wizard for DBs, SSH keys, & TS projects")
    print("   mws doctor [--fix-path]    -> Run health checks (COM, Python, DB, Git, PATH)")
    print("   mws list                   -> Show concise server inventory")
    print("   mws update [server|all]    -> Check & upgrade to latest PyPI version")
    print("=" * 76 + "\n")


def print_server_list() -> None:
    """Print a clean, beautifully formatted inventory of built-in servers and custom plugins."""
    import textwrap

    servers = list_available_servers()
    term_width = min(shutil.get_terminal_size(fallback=(80, 24)).columns, 88)

    print("\n" + "=" * term_width)
    print(f"   📦  MCP Server Inventory ({len(servers)} Available)")
    print("=" * term_width)

    for name, server in servers.items():
        is_inst = server.get("is_installed", False)
        status_badge = "[Installed]" if is_inst else "[Not Installed]"
        bullet = "●" if is_inst else "○"
        tools = str(server.get("tools_count", "?"))
        server_type = "Plugin" if not server.get("is_builtin") else "Built-in"

        print(f"\n  {bullet} {name:<14} {status_badge:<16} • {tools} tools • {server_type}")

        # Clean description without redundant "XX tools: " prefix
        raw_desc = server.get("description", "").strip().replace("\n", " ")
        cleaned_desc = re.sub(r"^\d+\s+(?:meta-)?tools:\s*", "", raw_desc, flags=re.IGNORECASE)

        wrapped_lines = textwrap.wrap(cleaned_desc, width=max(term_width - 6, 40))
        for line in wrapped_lines:
            print(f"    {line}")

        if not is_inst:
            print(f"    → Install: mws install {name}")

    print("\n" + "-" * term_width)
    print(f" Total: {len(servers)} servers available. All accessible via 'mws server'.")
    print(" 💡 Tips:")
    print("   • Run 'mws' for the interactive home dashboard.")
    print("   • Run 'mws guide <server>' for tool documentation and copy-paste configs.")
    print("   • Run 'mws server' to start the unified on-demand gateway.")
    print("=" * term_width + "\n")


def cmd_list(args: argparse.Namespace) -> None:
    """Show the focused server inventory."""
    print_server_list()


def _get_guide_func(srv_name: str):
    """Look for guide function in server package or legacy guides module."""
    if srv_name in ("server", "mws", "gateway"):
        try:
            from mcp_win_stdio.server.guide import print_server_guide

            return print_server_guide
        except ImportError:
            pass

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


def print_global_guide() -> None:
    """Print the universal multi-agent configuration guide and index."""
    print("\n" + "=" * 80)
    print("   📖  mws Universal MCP Guide — Multi-Agent Configuration Hub")
    print("=" * 80)
    print("\nmws provides 220+ tools across 10 modular servers on Windows.")
    print("Zero-Mutation Philosophy: mws never modifies your agent's config files automatically.")
    print("Simply copy and paste the snippet below into your AI client of choice!\n")

    print("-" * 80)
    print(" 🚀 RECOMMENDED: Unified On-Demand Gateway (Single Entry Point for ALL Tools)")
    print("-" * 80)
    print("Instead of configuring 9 separate servers and bloating context with 30,000+ tokens,")
    print("the Gateway exposes lightweight meta-tools that dynamically load child servers on demand.\n")
    print("Copy & paste under 'mcpServers' in your client configuration file:")
    print("```json")
    print(generate_snippet("server"))
    print("```")
    print("\n(Alternative using direct Python path if 'mws' is not on PATH):")
    print("```json")
    print(generate_snippet("server", use_python_exe=True))
    print("```\n")

    print("-" * 80)
    print(" 📁 Supported AI Clients & Windows Configuration Paths:")
    print("-" * 80)
    clients = get_all_clients()
    for idx, c in enumerate(clients, 1):
        paths_str = ", ".join(c["paths"][:2])
        print(f" {idx:>2}. {c['name']:<26} -> {paths_str}")
        print(f"     Run: mws guide {c['id']}")

    print("\n" + "-" * 80)
    print(" 🛠️  Available Standalone MCP Servers:")
    print("-" * 80)
    servers = list_available_servers()
    for name, srv in servers.items():
        if name in ("server", "mws"):
            continue
        tools = str(srv.get("tools_count", "?"))
        desc = srv.get("description", "")
        if len(desc) > 55:
            desc = desc[:52] + "..."
        print(f"   • {name:<10} ({tools:>2} tools) : {desc}")

    print("\n" + "-" * 80)
    print(" 💡 Guide Commands:")
    print("   mws guide <server>           -> Tool reference & config snippets for all clients")
    print("   mws guide <client>           -> Client-specific instructions & file paths")
    print("   mws guide <server> <client>  -> Client-tailored standalone config snippet")
    print("   (Examples: 'mws guide tsc', 'mws guide gemini', 'mws guide tsc gemini')")
    print("=" * 80 + "\n")


def print_client_guide(client_data: Dict[str, Any]) -> None:
    """Print setup instructions and Unified Gateway config for a specific client."""
    c_name = client_data["name"]
    c_id = client_data["id"]
    paths = client_data.get("paths", [])
    expanded_paths = get_actual_windows_paths(client_data)
    instructions = client_data.get("instructions", "")

    print("\n" + "=" * 80)
    print(f"   📖  mws Guide: {c_name} Configuration")
    print("=" * 80)

    print("\n📁 Target Configuration Files on Windows:")
    for p, ep in zip(paths, expanded_paths):
        exists_marker = " [Found on system]" if Path(ep).exists() else ""
        print(f"   • {p}{exists_marker}")
        if p != ep and "%" in p:
            print(f"     -> Actual path: {ep}")

    print("\n" + "-" * 80)
    print(" 📋 Recommended Configuration (Unified On-Demand Gateway — ALL Tools)")
    print("-" * 80)
    fmt = client_data.get("format", "json")
    print(f"Copy & paste into your {fmt.upper()} configuration file:\n")
    print(f"```{fmt}")
    print(generate_snippet("server", c_id))
    print("```")

    if fmt == "json":
        print("\n(Alternative using direct Python executable if 'mws' is not in PATH):")
        print("```json")
        print(generate_snippet("server", c_id, use_python_exe=True))
        print("```")

    print("\n" + "-" * 80)
    print(" 📝 Setup Instructions:")
    print("-" * 80)
    print(instructions)

    print("\n" + "-" * 80)
    print(f" 💡 To configure a specific standalone server for {c_name}:")
    print(f"    mws guide <server> {c_id}    (e.g. 'mws guide tsc {c_id}')")
    print("=" * 80 + "\n")


def print_server_client_guide(server_name: str, client_data: Dict[str, Any]) -> None:
    """Print configuration snippet and instructions for a specific server and client."""
    s_norm = server_name.lower().strip()
    c_name = client_data["name"]
    c_id = client_data["id"]
    fmt = client_data.get("format", "json")
    paths = client_data.get("paths", [])
    expanded_paths = get_actual_windows_paths(client_data)
    instructions = client_data.get("instructions", "")

    print("\n" + "=" * 80)
    print(f"   📖  mws Guide: '{s_norm}' for {c_name}")
    print("=" * 80)

    print("\n📁 Target Configuration Files on Windows:")
    for p, ep in zip(paths, expanded_paths):
        exists_marker = " [Found on system]" if Path(ep).exists() else ""
        print(f"   • {p}{exists_marker}")
        if p != ep and "%" in p:
            print(f"     -> Actual path: {ep}")

    print("\n" + "-" * 80)
    print(f" 📋 Copy & Paste Configuration Snippet for '{s_norm}':")
    print("-" * 80)
    print(f"```{fmt}")
    print(generate_snippet(s_norm, c_id))
    print("```")

    if fmt == "json":
        print("\n(Alternative using direct Python executable):")
        print("```json")
        print(generate_snippet(s_norm, c_id, use_python_exe=True))
        print("```")

    if s_norm == "db":
        print("\n🔒 Database Tip: Set DATABASE_URL in 'env', or manage credentials centrally")
        print("   without hardcoding passwords using: mws config db")
    elif s_norm == "ssh":
        print("\n🔑 SSH Tip: Manage host credentials and private keys dynamically with: mws config ssh")

    print("\n" + "-" * 80)
    print(f" 📝 Setup Instructions for {c_name}:")
    print("-" * 80)
    print(instructions)
    print("=" * 80 + "\n")


def print_server_guide_universal(server_name: str) -> None:
    """Print server specifications, universal copy-paste snippet, and tool recipes."""
    s_norm = server_name.lower().strip()
    target_aliases = {
        "github": "git",
        "database": "db",
        "workspace-explorer": "explorer",
        "excel-db": "excel_db",
        "exceldb": "excel_db",
        "mws": "server",
        "gateway": "server",
    }
    s_norm = target_aliases.get(s_norm, s_norm)

    print("\n" + "=" * 80)
    print(f"   📖  mws Guide: '{s_norm}' Standalone MCP Server")
    print("=" * 80)

    print("\n📋 Universal Copy & Paste Configuration Snippet:")
    print("Add this under 'mcpServers' in any standard MCP client config:")
    print("```json")
    print(generate_snippet(s_norm))
    print("```")

    print("\n(Alternative using direct Python executable if 'mws' is not on PATH):")
    print("```json")
    print(generate_snippet(s_norm, use_python_exe=True))
    print("```")

    if s_norm == "db":
        print("\n🔒 Database Tip: Set DATABASE_URL in 'env', or manage credentials centrally")
        print("   without hardcoding passwords using: mws config db")
    elif s_norm == "ssh":
        print("\n🔑 SSH Tip: Manage host credentials and private keys dynamically with: mws config ssh")

    print("\n" + "-" * 80)
    print(" 📁 Common Configuration File Paths on Windows:")
    print("-" * 80)
    for c in get_all_clients():
        print(f"   • {c['name']:<24} : {', '.join(c['paths'][:2])}")

    print(f"\n💡 For client-tailored instructions, run: mws guide {s_norm} <client>")
    print(f"   (e.g. 'mws guide {s_norm} gemini' or 'mws guide {s_norm} cursor')")

    fn = _get_guide_func(s_norm)
    if fn:
        print("\n" + "=" * 80)
        print(f" 🛠️  Tools Reference, Parameter Schemas & Prompt Recipes for '{s_norm}'")
        print("=" * 80)
        fn()
    else:
        print(f"\n[!] Note: Server package 'mcp-win-stdio-{s_norm}' is not currently installed.")
        print(f"    -> Run: mws install {s_norm}\n")


def cmd_guide(args: argparse.Namespace) -> None:
    """Universal guide dispatcher for AI clients, standalone servers, and multi-agent setups."""
    arg1 = getattr(args, "target", None) or getattr(args, "server", None)
    arg2 = getattr(args, "client", None)

    if arg1:
        arg1 = arg1.lower().strip()
    if arg2:
        arg2 = arg2.lower().strip()

    # Case 1: Both arguments provided (e.g. 'mws guide tsc gemini' or 'mws guide gemini tsc')
    if arg1 and arg2:
        c1 = resolve_client(arg1)
        c2 = resolve_client(arg2)
        if c1 and not c2:
            print_server_client_guide(arg2, c1)
            return
        elif c2:
            print_server_client_guide(arg1, c2)
            return
        else:
            print(f"[!] Unrecognized client '{arg2}'. Run 'mws guide' to list all supported AI clients.")
            return

    # Case 2: Exactly one argument provided
    if arg1:
        if arg1 == "all":
            print_global_guide()
            return

        client_match = resolve_client(arg1)
        if client_match:
            print_client_guide(client_match)
            return

        print_server_guide_universal(arg1)
        return

    # Case 3: No arguments provided -> show universal global guide
    print_global_guide()


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
        ok, msg = install_pip_dependencies(["mcp-win-stdio[all]"])
        if not ok:
            print(f"[ERROR] {msg}")
    else:
        for srv_name in selected_servers:
            srv = get_server_info(srv_name)
            if not srv:
                print(f"[ERROR] Unknown server: '{srv_name}'. Run 'mws list' to see available servers.")
                continue
            pkg = srv.get("package", f"mcp-win-stdio-{srv_name}")
            ok, msg = install_pip_dependencies([pkg])
            if not ok:
                print(f"[ERROR] {msg}")

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

    print("\n✅ Installation complete! Run 'mws list' to verify status or 'mws guide' to view agent setup snippets.\n")


def cmd_retired(args: argparse.Namespace) -> None:
    """Friendly guidance when a retired auto-configuration command is invoked."""
    cmd_name = getattr(args, "command", "this command")
    print("\n" + "=" * 76)
    print(" ℹ️  Notice: mws has transitioned to a Non-Invasive Multi-Agent Architecture")
    print("=" * 76)
    print(f"The '{cmd_name}' command has been retired because mws no longer automatically")
    print("modifies client configuration files. We support all major AI environments:")
    print("  • Gemini / Antigravity IDE     • Claude Desktop & Claude Code")
    print("  • ChatGPT Desktop              • Cursor AI")
    print("  • Kiro IDE                     • OpenCode")
    print("  • Codeium Windsurf             • GitHub Copilot / VS Code")
    print("  • OpenAI Codex")
    print("\n👉 To view copy-paste configuration snippets and exact file paths:")
    print("   mws guide                   -> Universal multi-agent guide")
    print("   mws guide <client>          -> Recommended Unified Gateway setup (e.g. 'mws guide gemini')")
    print("   mws guide <server> <client> -> Standalone server snippet (e.g. 'mws guide tsc gemini')")
    print("=" * 76 + "\n")


def cmd_setup(args: argparse.Namespace) -> None:
    """Retired auto-setup command."""
    cmd_retired(args)


def cmd_remove(args: argparse.Namespace) -> None:
    """Retired auto-remove command."""
    cmd_retired(args)


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

    # Determine target packages: ONLY update what is currently installed
    if target in ("all", "", "installed"):
        installed = get_installed_mws_packages()
        pkg_targets = installed if installed else ["mcp-win-stdio"]
    elif target in ("core", "mws", "mcp-win-stdio"):
        pkg_targets = ["mcp-win-stdio"]
    else:
        srv = get_server_info(target)
        pkg_name = srv.get("package", f"mcp-win-stdio-{target}") if srv else f"mcp-win-stdio-{target}"
        pkg_targets = [pkg_name]

    print(f"\n📦 Target package(s) to update ({len(pkg_targets)}): {', '.join(pkg_targets)}")

    # On Windows interactive terminals, hand off update to external supervisor
    # whenever mcp-win-stdio CLI itself is among targets to release executable locks on mws.exe
    if sys.platform == "win32" and any(p == "mcp-win-stdio" for p in pkg_targets) and sys.stdin.isatty():
        spawn_external_updater("update", pkg_targets)
        return

    ok, msg = install_pip_dependencies(pkg_targets, upgrade=True)

    if ok:
        print("\n✅ Update completed successfully!\n")
    else:
        print(f"\n[WARN] Update process warning:\n{msg}\n")


def cmd_uninstall(args: argparse.Namespace) -> None:
    """Cleanly uninstall MCP server package(s) while preserving ~/.mcp-win-stdio user configurations."""
    target = (args.server or "").lower()

    if not target:
        if sys.stdin.isatty():
            print("\n=== 🗑️  mcp-win-stdio Uninstaller ===")
            print("  [1] excel     -> Uninstall mcp-win-stdio-excel")
            print("  [2] word      -> Uninstall mcp-win-stdio-word")
            print("  [3] explorer  -> Uninstall mcp-win-stdio-explorer")
            print("  [4] tsc       -> Uninstall mcp-win-stdio-tsc")
            print("  [5] db        -> Uninstall mcp-win-stdio-db")
            print("  [6] git       -> Uninstall mcp-win-stdio-git")
            print("  [7] ssh       -> Uninstall mcp-win-stdio-ssh")
            print("  [8] rag       -> Uninstall mcp-win-stdio-rag")
            print("  [9] excel-db  -> Uninstall mcp-win-stdio-excel-db")
            print("  [10] all      -> Uninstall all 9 standalone MCP servers (keeps mws CLI)")
            print("  [11] self     -> Completely uninstall mws CLI & all mcp-win-stdio-* packages")
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

    # CASE 1: Completely uninstall mws CLI and ALL installed mcp-win-stdio-* subpackages
    if target in ("self", "purge"):
        all_installed = get_installed_mws_packages()
        if not all_installed:
            all_installed = ["mcp-win-stdio"]
        if "mcp-win-stdio" not in all_installed:
            all_installed.insert(0, "mcp-win-stdio")

        print(f"\n==> 🧹 Completely uninstalling mws suite ({len(all_installed)} packages found):")
        for p in all_installed:
            print(f"   • {p}")

        if sys.platform == "win32" and sys.stdin.isatty():
            spawn_external_updater("uninstall", all_installed)
            return

        ok_pip, msg_pip = uninstall_pip_packages(all_installed)
        if ok_pip:
            print("\n[OK] All mcp-win-stdio packages uninstalled successfully.")
        else:
            print(f"\n[WARN] {msg_pip}")

        print("\n" + "=" * 76)
        print(f"🔒 Single-source hub directory PRESERVED: {USER_DIR}")
        print("   (Your custom plugins, logs, and configs in ~/.mcp-win-stdio remain safe.)")
        print("ℹ️  Zero-Mutation Policy: Client config files were untouched.")
        print("=" * 76)
        print("✅ Uninstallation complete!\n")
        return

    # CASE 2: Uninstall all standalone servers but KEEP mws CLI core
    if target == "all":
        installed_subpkgs = [p for p in get_installed_mws_packages() if p != "mcp-win-stdio"]
        if not installed_subpkgs:
            print("\nℹ️  No standalone MCP server packages are currently installed to remove.")
            return

        print(f"\n==> 🧹 Uninstalling all standalone MCP server packages ({len(installed_subpkgs)} targets)...")
        for p in installed_subpkgs:
            print(f"   • {p}")

        ok_pip, msg_pip = uninstall_pip_packages(installed_subpkgs)
        if ok_pip:
            print("[OK] Standalone server packages uninstalled successfully.")
        else:
            print(f"[WARN] {msg_pip}")

        print("\n" + "=" * 76)
        print(f"🔒 Single-source hub directory PRESERVED: {USER_DIR}")
        print("⚙️  mws CLI PRESERVED (You can continue using 'mws' or reinstall anytime).")
        print("ℹ️  Zero-Mutation Policy: Client config files were untouched.")
        print("=" * 76)
        print("✅ Uninstallation complete!\n")
        return

    # CASE 3: Uninstall a single specific server package
    srv = get_server_info(target)
    pkg = srv.get("package", f"mcp-win-stdio-{target}") if srv else f"mcp-win-stdio-{target}"

    if pkg not in get_installed_mws_packages():
        print(f"\nℹ️  Package '{pkg}' is not currently installed.")
        return

    print(f"\n==> 🧹 Uninstalling server package '{target}' ({pkg})...")
    ok_pip, msg_pip = uninstall_pip_packages([pkg])
    if ok_pip:
        print(f"[OK] Package '{pkg}' uninstalled successfully.")
    else:
        print(f"[WARN] {msg_pip}")

    print("\n" + "=" * 76)
    print(f"🔒 Single-source hub directory PRESERVED: {USER_DIR}")
    print("⚙️  mws CLI PRESERVED")
    print("ℹ️  Zero-Mutation Policy: Client config files were untouched.")
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
    env_file = Path(getattr(args, "env_file", ".env"))
    if not env_file.is_absolute():
        env_file = Path.cwd() / env_file
    if env_file.exists():
        try:
            for line_number, raw_line in enumerate(env_file.read_text(encoding="utf-8-sig").splitlines(), start=1):
                line = raw_line.strip()
                if not line or line.startswith("#"):
                    continue
                if line.startswith("export "):
                    line = line[7:].lstrip()
                key, separator, value = line.partition("=")
                key = key.strip()
                if not separator or not key or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
                    print(f"Error: Invalid environment entry in {env_file} at line {line_number}.", file=sys.stderr)
                    sys.exit(1)
                value = value.strip()
                if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
                    value = value[1:-1]
                os.environ.setdefault(key, value)
        except OSError as exc:
            print(f"Error: Could not read environment file '{env_file}': {exc}", file=sys.stderr)
            sys.exit(1)

    server_name = args.server.lower()
    if server_name in ("self", "mws", "server"):
        from mcp_win_stdio.server.server import mcp

        mcp.run()
        return

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
        except ModuleNotFoundError as e:
            pkg = srv.get("package", f"mcp-win-stdio-{server_name}")
            print(f"Error: Server package '{pkg}' is not installed in the current environment.", file=sys.stderr)
            print(
                f"👉 To install: mws install {server_name}  (or: uv pip install {pkg} / pip install {pkg})",
                file=sys.stderr,
            )
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


def cmd_server(args: argparse.Namespace) -> None:
    """Run mws as the unified on-demand MCP server or run server subcommands."""
    action = getattr(args, "server_action", "run")
    target = getattr(args, "target_server", None)
    if target and not getattr(args, "server", None):
        args.server = target

    if action == "list":
        from mcp_win_stdio.server.cli import cmd_list

        cmd_list(args)
    elif action == "doctor":
        from mcp_win_stdio.server.cli import cmd_doctor

        cmd_doctor(args)
    elif action == "guide":
        from mcp_win_stdio.server.guide import print_server_guide

        print_server_guide()
    elif action == "stop":
        from mcp_win_stdio.server.cli import cmd_stop

        cmd_stop(args)
    else:
        from mcp_win_stdio.server.server import mcp

        mcp.run()


def cmd_config(args: argparse.Namespace) -> None:
    """Launch interactive configuration hub for DB, SSH, TSC, and Gateway."""
    from mcp_win_stdio.core.wizard import main_config_interactive

    main_config_interactive(getattr(args, "domain", None))


def cmd_doctor(args: argparse.Namespace) -> None:
    """Run diagnostic health checks on Windows environment, COM automation, and dependencies."""
    if getattr(args, "fix_path", False):
        cmd_fix_path(args)
        return

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
        print("       👉 Run 'mws doctor --fix-path' to add it to your Windows User PATH automatically.")

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


ALL_BUILTIN_SERVERS = ["server", "rag", "excel-db", "excel", "db", "explorer", "git", "ssh", "tsc", "word"]


def get_server_agents_guide(servers: List[str]) -> str:
    """Generate tailored AGENTS.md markdown guide for specific active servers."""
    lines = [
        "# Repository Agent Guidelines",
        "",
        "This repository is equipped with the **mcp-win-stdio (`mws`)** tool suite.",
        "",
        "Project MCP commands use the active Python runtime and load an optional root `.env` file. Keep secrets in `.env`, never in committed MCP configuration.",
        "",
        "## 🛠️ Active Tools & Recommended Selection",
        "",
    ]
    guide_map = {
        "server": "* **Unified On-Demand Gateway:** Use `mws` MCP (`list_servers`, `search_tools`, `call_tool`) to route and execute tools on demand with zero context bloat.",
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
    if s_name in ("server", "mws"):
        return {
            "command": sys.executable.replace("\\", "/"),
            "args": [
                "-m",
                "mcp_win_stdio.server",
            ],
        }

    entry: Dict[str, Any] = {
        "command": sys.executable.replace("\\", "/"),
        "args": [
            "-m",
            "mcp_win_stdio",
            "run",
            s_name,
            "--env-file",
            "${workspaceFolder}/.env" if is_vscode else str(cwd / ".env"),
        ],
    }
    env: Dict[str, str] = {}

    # 1. Explorer Workspace Root
    if s_name == "explorer":
        env["EXPLORER_ROOT"] = "${workspaceFolder}" if is_vscode else str(cwd)

    elif s_name == "git":
        env["GIT_REPO_DIR"] = "${workspaceFolder}" if is_vscode else str(cwd)

    if env:
        entry["env"] = env

    return entry


def _upsert_managed_section(path: Path, section: str, content: str) -> None:
    """Update only mws-owned content while preserving user-authored file contents."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if section == "environment":
        begin = f"# mws:{section}:begin"
        end = f"# mws:{section}:end"
    else:
        begin = f"<!-- mws:{section}:begin -->"
        end = f"<!-- mws:{section}:end -->"
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    start_index = existing.find(begin)
    end_index = existing.find(end, start_index + len(begin)) if start_index >= 0 else -1
    block = f"{begin}\n{content.rstrip()}\n{end}"

    if start_index >= 0 and end_index >= 0:
        end_index += len(end)
        updated = f"{existing[:start_index]}{block}{existing[end_index:]}"
    else:
        separator = "\n\n" if existing and not existing.endswith("\n\n") else ""
        updated = f"{existing}{separator}{block}\n"
    path.write_text(updated, encoding="utf-8")


def _project_env_template(servers: List[str]) -> str:
    """Return secret-free examples for environment variables read by selected servers."""
    lines = [
        "# Copy this file to .env and fill in only the values you need.",
        "# Never commit .env or put credentials in .mcp.json.",
    ]
    env_by_server = {
        "db": [
            ("DATABASE_URL", "# Optional single database URL; prefer a local connections file for multiple databases."),
            ("SERVERS", "# Optional JSON object mapping database aliases to connection URLs."),
        ],
        "excel-db": [("SERVERS", "# Optional JSON object mapping database aliases to connection URLs.")],
        "ssh": [("SSH_SERVERS", "# Optional JSON object mapping SSH aliases to host configuration.")],
        "git": [("GIT_REPO_DIR", "# Optional default repository path.")],
        "rag": [("MCP_RAG_DATA_DIR", "# Optional directory for the local RAG index.")],
    }
    seen = set()
    for server in servers:
        for key, description in env_by_server.get(server, []):
            if key in seen:
                continue
            seen.add(key)
            lines.extend(["", f"# {server}: {description}", f"{key}="])
    return "\n".join(lines)


def _confirm_project_setup(servers: List[str], cwd: Path, assume_yes: bool) -> bool:
    if assume_yes:
        return True
    print(f"\nProject setup in: {cwd}")
    print(f"Servers to configure: {', '.join(servers)}")
    print("This updates project MCP configs and mws-managed agent guidance; existing entries are preserved.")
    if not sys.stdin.isatty():
        print("Setup not confirmed in a non-interactive terminal. Re-run with --yes to proceed.", file=sys.stderr)
        return False
    return input("Continue? [y/N]: ").strip().lower() in ("y", "yes")


def _write_env_values(env_file: Path, values: Dict[str, str]) -> None:
    existing = env_file.read_text(encoding="utf-8") if env_file.exists() else ""
    lines = existing.splitlines()
    remaining = dict(values)
    updated = []
    for line in lines:
        match = re.match(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=", line)
        key = match.group(1) if match else None
        if key in remaining:
            updated.append(f"{key}={remaining.pop(key)}")
        else:
            updated.append(line)
    for key, value in remaining.items():
        if updated and updated[-1]:
            updated.append("")
        updated.append(f"{key}={value}")
    env_file.write_text("\n".join(updated) + ("\n" if updated else ""), encoding="utf-8")


def _configure_project_environment(servers: List[str], cwd: Path, interactive: bool) -> List[str]:
    """Ask for optional server credentials and persist them only in the ignored project .env."""
    db_url_key = "DATABASE_URL" if "db" in servers else None
    excel_db_key = "SERVERS" if "excel-db" in servers else None
    requested_keys = [key for key in (db_url_key, excel_db_key) if key]
    if not requested_keys:
        return []

    env_file = cwd / ".env"
    existing_values = {}
    if env_file.exists():
        for raw_line in env_file.read_text(encoding="utf-8-sig").splitlines():
            line = raw_line.strip()
            if line.startswith("export "):
                line = line[7:].lstrip()
            key, separator, value = line.partition("=")
            if separator:
                existing_values[key.strip()] = value.strip().strip("'\"")

    updates: Dict[str, str] = {}
    if interactive and sys.stdin.isatty():
        if db_url_key:
            sqlite_candidates = sorted(
                [*cwd.glob("*.db"), *cwd.glob("*.sqlite"), *cwd.glob("*.sqlite3")],
                key=lambda path: path.name.lower(),
            )
            default_url = f"sqlite:///{sqlite_candidates[0].resolve().as_posix()}" if sqlite_candidates else ""
            if default_url:
                print(f"Detected local SQLite database: {sqlite_candidates[0].name}")
            prompt = (
                "DATABASE_URL [Enter uses detected SQLite; '-' skips]: "
                if default_url and "DATABASE_URL" not in existing_values
                else "DATABASE_URL (optional; Enter keeps current value or skips): "
            )
            value = getpass.getpass(prompt)
            if value == "-":
                pass
            elif value:
                updates["DATABASE_URL"] = value
            elif "DATABASE_URL" not in existing_values and default_url:
                updates["DATABASE_URL"] = default_url

        if excel_db_key:
            value = getpass.getpass("SERVERS JSON for excel-db (Enter keeps current value; '-' skips): ")
            if value == "-":
                pass
            elif value:
                try:
                    parsed = json.loads(value)
                except json.JSONDecodeError as exc:
                    raise ValueError(f"Invalid SERVERS JSON: {exc}") from exc
                if not isinstance(parsed, dict) or not all(isinstance(item, str) for item in parsed.values()):
                    raise ValueError("SERVERS must be a JSON object mapping aliases to connection URL strings.")
                updates["SERVERS"] = json.dumps(parsed)

    if updates:
        _ensure_env_gitignored(cwd)
        _write_env_values(env_file, updates)
    return requested_keys


def _project_change_preview(servers: List[str], cwd: Path, clients: List[str]) -> List[str]:
    files = [
        ".mcp.json",
        ".agents/mcp_config.json",
        ".codex/config.toml",
        "AGENTS.md",
        "GEMINI.md",
        "CLAUDE.md",
        ".github/copilot-instructions.md",
        ".env.example",
    ]
    if any(server in ("db", "excel-db", "ssh", "git", "rag") for server in servers):
        files.append(".gitignore (ensure .env is ignored)")
    if any(server in ("db", "excel-db") for server in servers):
        files.append(".env (only if environment values are entered)")
    if (cwd / ".vscode" / "mcp.json").exists():
        files.append(".vscode/mcp.json (legacy config may be migrated and removed)")

    print("\nDry run: no files will be changed.")
    print(f"Workspace: {cwd}")
    print(f"Servers: {', '.join(servers)}")
    if clients:
        print(f"Agent targets: {', '.join(clients)}")
    print("Planned project files:")
    for path in files:
        print(f"  - {path}")
    environment_keys = []
    if "db" in servers:
        environment_keys.append("DATABASE_URL")
    if "excel-db" in servers:
        environment_keys.append("SERVERS")
    if environment_keys:
        print(f"Environment values to review (not shown or written in dry-run): {', '.join(environment_keys)}")
    machine_configs = {
        "antigravity": str(Path.home() / ".gemini" / "config" / "mcp_config.json"),
        "claude": f"{os.environ.get('APPDATA', '')}\\Claude\\claude_desktop_config.json and {Path.home() / '.claude.json'}",
        "copilot": f"{Path.home() / '.copilot' / 'mcp-config.json'} and {os.environ.get('APPDATA', '')}\\Code\\User\\mcp.json",
        "cursor": f"{os.environ.get('APPDATA', '')}\\Cursor\\User\\mcp.json or {Path.home() / '.cursor' / 'mcp.json'}",
        "windsurf": str(Path.home() / ".codeium" / "windsurf" / "mcp_config.json"),
    }
    if clients:
        print("Potential machine-level client config targets:")
        selected_clients = list(machine_configs) if "all" in clients else clients
        for client in selected_clients:
            if client in machine_configs:
                print(f"  - {client}: {machine_configs[client]}")
    print("Existing unrelated MCP entries and text outside mws-managed guidance blocks will be preserved.")
    return files


def _detected_project_clients() -> Dict[str, bool]:
    appdata = Path(os.environ.get("APPDATA", ""))
    local_appdata = Path(os.environ.get("LOCALAPPDATA", ""))
    return {
        "antigravity": (Path.home() / ".gemini").exists() or (local_appdata / "Programs" / "Antigravity IDE").exists(),
        "codex": bool(shutil.which("codex")) or (Path.home() / ".codex").exists(),
        "claude": (appdata / "Claude").exists()
        or (Path.home() / ".claude.json").exists()
        or (Path.home() / ".claude").exists()
        or bool(shutil.which("claude")),
        "copilot": (appdata / "Code").exists()
        or (Path.home() / ".copilot").exists()
        or bool(shutil.which("code"))
        or bool(shutil.which("code.cmd"))
        or bool(shutil.which("gh")),
        "cursor": (appdata / "Cursor").exists() or (Path.home() / ".cursor").exists() or bool(shutil.which("cursor")),
        "windsurf": (Path.home() / ".codeium" / "windsurf").exists()
        or (appdata / "Windsurf").exists()
        or bool(shutil.which("windsurf")),
    }


def _read_project_env_keys(env_file: Path) -> set[str]:
    if not env_file.exists():
        return set()
    keys = set()
    for raw_line in env_file.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if line.startswith("export "):
            line = line[7:].lstrip()
        key, separator, _ = line.partition("=")
        if separator and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key.strip()):
            keys.add(key.strip())
    return keys


def cmd_status(args: argparse.Namespace) -> None:
    """Show project MCP setup state without modifying files."""
    cwd = Path.cwd()
    available = list_available_servers()
    mcp_file = cwd / ".mcp.json"
    config = _read_json_object(mcp_file) if mcp_file.exists() else {}
    configured = config.get("mcpServers", {})
    if not isinstance(configured, dict):
        raise ValueError(f"Expected 'mcpServers' to be an object in '{mcp_file}'.")
    env_keys = _read_project_env_keys(cwd / ".env")

    print(f"Workspace: {cwd}")
    print(f"MCP config: {'present' if mcp_file.exists() else 'not initialized'}")
    print("Detected agent clients:")
    for client, detected in _detected_project_clients().items():
        print(f"  {client}: {'detected' if detected else 'not detected'}")
    print("Servers:")
    server_names = sorted(set(available) | set(configured))
    if not server_names:
        print("  (no known servers)")
    for server in server_names:
        installed = bool(available.get(server, {}).get("is_installed"))
        configured_state = "configured" if server in configured else "not configured"
        installed_state = "installed" if installed else "not installed"
        print(f"  {server}: {installed_state}; {configured_state}")

    required_environment = {}
    if "db" in configured:
        required_environment["DATABASE_URL"] = "optional DB connection"
    if "excel-db" in configured:
        required_environment["SERVERS"] = "optional Excel-DB connections"
    print("Environment:")
    if not required_environment:
        print(f"  .env: {'present' if (cwd / '.env').exists() else 'not present'}")
    for key, label in required_environment.items():
        print(f"  {key}: {'set' if key in env_keys else 'not set'} ({label})")

    issues = []
    if mcp_file.exists() and not configured:
        issues.append(".mcp.json has no MCP server entries")
    for server, entry in configured.items():
        if not isinstance(entry, dict) or not isinstance(entry.get("command"), str):
            issues.append(f"{server}: missing or invalid command")
        elif not isinstance(entry.get("args", []), list):
            issues.append(f"{server}: args must be a list")
    print("Configuration:")
    if issues:
        for issue in issues:
            print(f"  WARNING: {issue}")
    else:
        print("  No basic MCP config problems found.")


def _update_project_agent_guides(cwd: Path, servers: List[str]) -> None:
    content = get_server_agents_guide(servers)
    _upsert_managed_section(cwd / "AGENTS.md", "agent-guidance", content)
    _upsert_managed_section(cwd / "GEMINI.md", "agent-guidance", content)
    _upsert_managed_section(cwd / "CLAUDE.md", "agent-guidance", content)
    _upsert_managed_section(cwd / ".github" / "copilot-instructions.md", "agent-guidance", content)


def _ensure_env_gitignored(target_dir: Path) -> None:
    gitignore = target_dir / ".gitignore"
    existing = gitignore.read_text(encoding="utf-8") if gitignore.exists() else ""
    if ".env" in {line.strip() for line in existing.splitlines()} or "*.env" in existing.splitlines():
        return
    separator = "" if not existing or existing.endswith("\n") else "\n"
    gitignore.write_text(f"{existing}{separator}\n# Local mws environment secrets\n.env\n", encoding="utf-8")


def _read_json_object(path: Path) -> Dict[str, Any]:
    """Read a JSON object without treating invalid user configuration as empty."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Could not read valid JSON from '{path}': {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"Expected a JSON object in '{path}'.")
    return data


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
    config_data = _read_json_object(root_file) if root_file.exists() else {}

    # Preserve existing user and agent configurations; only update requested server entries.
    existing_servers = config_data.get("mcpServers", {})
    if not isinstance(existing_servers, dict):
        raise ValueError(f"Expected 'mcpServers' to be an object in '{root_file}'.")

    # Check for legacy .vscode/mcp.json to migrate servers
    migrated_from_legacy = False
    if vscode_file.exists():
        legacy_config = _read_json_object(vscode_file)
        legacy_servers = legacy_config.get("mcpServers", {})
        if not isinstance(legacy_servers, dict):
            raise ValueError(f"Expected 'mcpServers' to be an object in '{vscode_file}'.")
        for k, v in legacy_servers.items():
            if k not in existing_servers:
                existing_servers[k] = v
                migrated_from_legacy = True

        # Clean up deprecated .vscode/mcp.json if requested to avoid VS Code 1.106+ warnings
        if clean_deprecated_vscode:
            vscode_file.unlink()
            vscode_dir = vscode_file.parent
            if vscode_dir.exists() and not any(vscode_dir.iterdir()):
                vscode_dir.rmdir()

    for s in servers:
        s_norm = s.lower().strip()
        if s_norm:
            existing_servers[s_norm] = _build_server_entry(s_norm, is_vscode=True, cwd=cwd)

    # 1. Root .mcp.json
    config_data["mcpServers"] = existing_servers
    with open(root_file, "w", encoding="utf-8") as f:
        json.dump(config_data, f, indent=2)

    # 2. Antigravity workspace agent (.agents/mcp_config.json)
    agents_dir = cwd / ".agents"
    agents_dir.mkdir(parents=True, exist_ok=True)
    agents_mcp_file = agents_dir / "mcp_config.json"
    agents_config = _read_json_object(agents_mcp_file) if agents_mcp_file.exists() else {}
    agents_servers = agents_config.get("mcpServers", {})
    if not isinstance(agents_servers, dict):
        raise ValueError(f"Expected 'mcpServers' to be an object in '{agents_mcp_file}'.")
    agents_servers.update(existing_servers)
    with open(agents_mcp_file, "w", encoding="utf-8") as f:
        agents_config["mcpServers"] = agents_servers
        json.dump(agents_config, f, indent=2)

    # 3. Agent guidelines and safe local environment scaffold.
    _update_project_agent_guides(cwd, list(existing_servers.keys()))

    env_template = _project_env_template(list(existing_servers.keys()))
    _upsert_managed_section(cwd / ".env.example", "environment", env_template)
    if any(server in ("db", "excel-db", "ssh", "git", "rag") for server in existing_servers):
        _ensure_env_gitignored(cwd)
    _update_codex_project_config(servers, cwd)

    return {
        "cwd": cwd,
        "servers": list(existing_servers.keys()),
        "migrated_from_legacy_vscode": migrated_from_legacy,
        "config_file": str(root_file),
    }


def _update_codex_project_config(servers: List[str], cwd: Path) -> Path:
    """Merge selected MCP server tables into Codex's trusted project config."""
    config_dir = cwd / ".codex"
    config_dir.mkdir(parents=True, exist_ok=True)
    config_path = config_dir / "config.toml"
    existing = config_path.read_text(encoding="utf-8") if config_path.exists() else ""
    lines = existing.splitlines()
    output = []
    index = 0
    selected = {server.lower().strip() for server in servers if server.strip()}
    while index < len(lines):
        match = re.fullmatch(r"\[mcp_servers\.([A-Za-z0-9_-]+)\]", lines[index].strip())
        if match and match.group(1) in selected:
            server_prefix = f"[mcp_servers.{match.group(1)}."
            index += 1
            while index < len(lines):
                current = lines[index].strip()
                if re.fullmatch(r"\[[^]]+\]", current) and not current.startswith(server_prefix):
                    break
                index += 1
            continue
        output.append(lines[index])
        index += 1

    blocks = []
    for server in sorted(selected):
        entry = _build_server_entry(server, is_vscode=False, cwd=cwd)
        args = ", ".join(json.dumps(arg) for arg in entry["args"])
        fields = [
            f"[mcp_servers.{server}]",
            f"command = {json.dumps(entry['command'])}",
            f"args = [{args}]",
            'cwd = "."',
            "startup_timeout_sec = 20",
        ]
        if entry.get("env"):
            env = ", ".join(f"{json.dumps(key)} = {json.dumps(value)}" for key, value in entry["env"].items())
            fields.append(f"env = {{ {env} }}")
        blocks.append("\n".join(fields))

    preserved = "\n".join(output).rstrip()
    updated = (f"{preserved}\n\n" if preserved else "") + "\n\n".join(blocks)
    config_path.write_text(f"{updated}\n" if updated else "", encoding="utf-8")
    return config_path


def _remove_codex_project_servers(servers: List[str], cwd: Path) -> None:
    config_path = cwd / ".codex" / "config.toml"
    if not config_path.exists():
        return
    selected = {server.lower().strip() for server in servers if server.strip()}
    lines = config_path.read_text(encoding="utf-8").splitlines()
    output = []
    index = 0
    while index < len(lines):
        match = re.fullmatch(r"\[mcp_servers\.([A-Za-z0-9_-]+)\]", lines[index].strip())
        if match and match.group(1) in selected:
            server_prefix = f"[mcp_servers.{match.group(1)}."
            index += 1
            while index < len(lines):
                current = lines[index].strip()
                if re.fullmatch(r"\[[^]]+\]", current) and not current.startswith(server_prefix):
                    break
                index += 1
            continue
        output.append(lines[index])
        index += 1
    config_path.write_text("\n".join(output).rstrip() + ("\n" if output else ""), encoding="utf-8")


def remove_project_mcp(servers: List[str], target_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Remove server(s) from .mcp.json, clean up any legacy .vscode/mcp.json, and refresh AGENTS.md / GEMINI.md."""
    cwd = target_dir or Path.cwd()
    root_file = cwd / ".mcp.json"
    vscode_file = cwd / ".vscode" / "mcp.json"

    config_data = _read_json_object(root_file) if root_file.exists() else {}
    existing_servers = config_data.get("mcpServers", {})
    if not isinstance(existing_servers, dict):
        raise ValueError(f"Expected 'mcpServers' to be an object in '{root_file}'.")

    for s in servers:
        s_norm = s.lower().strip()
        existing_servers.pop(s_norm, None)

    config_data["mcpServers"] = existing_servers

    with open(root_file, "w", encoding="utf-8") as f:
        json.dump(config_data, f, indent=2)

    agents_mcp_file = cwd / ".agents" / "mcp_config.json"
    if agents_mcp_file.exists():
        agents_config = _read_json_object(agents_mcp_file)
        agents_servers = agents_config.get("mcpServers", {})
        if not isinstance(agents_servers, dict):
            raise ValueError(f"Expected 'mcpServers' to be an object in '{agents_mcp_file}'.")
        for server in servers:
            agents_servers.pop(server.lower().strip(), None)
        with open(agents_mcp_file, "w", encoding="utf-8") as f:
            agents_config["mcpServers"] = agents_servers
            json.dump(agents_config, f, indent=2)

    if vscode_file.exists():
        try:
            vscode_file.unlink()
            if vscode_file.parent.exists() and not any(vscode_file.parent.iterdir()):
                vscode_file.parent.rmdir()
        except Exception:
            pass

    _update_project_agent_guides(cwd, list(existing_servers.keys()))
    _upsert_managed_section(cwd / ".env.example", "environment", _project_env_template(list(existing_servers.keys())))
    _remove_codex_project_servers(servers, cwd)

    return {"cwd": cwd, "servers": list(existing_servers.keys()), "config_file": str(root_file)}


CLIENT_ALIASES = {
    "antigravity": "antigravity",
    "gemini": "antigravity",
    "agy": "antigravity",
    "claude": "claude",
    "claude-desktop": "claude",
    "claude-code": "claude",
    "codex": "codex",
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
        if s_norm in ("server", "mws"):
            res[s_norm] = {
                "command": py_exe,
                "args": ["-m", "mcp_win_stdio.server"],
            }
            continue
        entry: Dict[str, Any] = {
            "command": py_exe,
            "args": ["-m", "mcp_win_stdio", "run", s_norm, "--env-file", str(cwd / ".env")],
        }
        env: Dict[str, str] = {}
        if s_norm == "explorer":
            env["EXPLORER_ROOT"] = str(cwd)
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


def init_codex(servers: List[str], cwd: Path) -> Dict[str, Any]:
    """Initialize Codex with a trusted project-scoped MCP configuration."""
    setup_project_mcp(servers, target_dir=cwd, overwrite=False)
    project_config = cwd / ".codex" / "config.toml"
    return {
        "client": "OpenAI Codex",
        "detected": bool(shutil.which("codex")) or (Path.home() / ".codex").exists(),
        "status": "Configured",
        "primary_config": str(project_config),
        "files_updated": [str(project_config), str(cwd / ".mcp.json"), str(cwd / "AGENTS.md")],
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
        ("codex", init_codex),
        ("claude", init_claude),
        ("copilot", init_copilot),
        ("cursor", init_cursor),
        ("windsurf", init_windsurf),
    ]

    detected_clients = _detected_project_clients()

    for name, handler in client_handlers:
        if detected_clients[name]:
            res = handler(servers, cwd)
        else:
            res = {
                "client": name.capitalize() if name != "codex" else "OpenAI Codex",
                "detected": False,
                "status": "Skipped",
                "primary_config": "",
                "files_updated": [],
                "servers_count": len(servers),
            }
        results.append(res)

    if not any(detected_clients.values()):
        setup_project_mcp(servers, target_dir=cwd)

    return results


def cmd_init_project(args: argparse.Namespace) -> None:
    """Retired project bootstrap command."""
    cmd_retired(args)


cmd_init = cmd_init_project


def cmd_setup_project(args: argparse.Namespace) -> None:
    """Retired project setup command."""
    cmd_retired(args)


def cmd_remove_project(args: argparse.Namespace) -> None:
    """Retired project removal command."""
    cmd_retired(args)


def cmd_workflow(args: argparse.Namespace) -> None:
    """Manage and execute custom composite workflows."""
    from mcp_win_stdio.core.workflows import (
        delete_workflow,
        list_workflows,
        load_workflow,
        run_workflow,
    )

    action = getattr(args, "wf_action", "list") or "list"
    name = getattr(args, "wf_name", None)

    if action == "list":
        wfs = list_workflows()
        print("\n" + "=" * 70)
        print("  ⚡ mws Composite Workflows (Zero-Latency Multi-Tool Pipelines)")
        print("=" * 70)
        if not wfs:
            print("  No workflows found.")
            print("\n  Create one in your workspace at `.mws/workflows/<name>.json` or via:")
            print("  AI Agent MCP tool: save_workflow(...)")
            print("=" * 70 + "\n")
            return

        print(f"  {'NAME':<20} {'SCOPE':<10} {'STEPS':<8} {'TITLE'}")
        print("  " + "-" * 66)
        for w in wfs:
            print(f"  {w['name']:<20} {w['scope']:<10} {w['steps_count']:<8} {w['title']}")
        print("=" * 70)
        print("  Run a workflow:  mws workflow run <name>")
        print("  View recipe:     mws workflow view <name>\n")

    elif action == "view":
        if not name:
            print("Error: Missing workflow name. Usage: mws workflow view <name>")
            sys.exit(1)
        wf = load_workflow(name)
        if not wf:
            print(f"Error: Workflow '{name}' not found.")
            sys.exit(1)
        print(json.dumps(wf, indent=2))

    elif action == "delete":
        if not name:
            print("Error: Missing workflow name. Usage: mws workflow delete <name>")
            sys.exit(1)
        res = delete_workflow(name)
        print(res["message"])

    elif action == "run":
        if not name:
            print("Error: Missing workflow name. Usage: mws workflow run <name> [--params '{...}']")
            sys.exit(1)
        params = {}
        if getattr(args, "params", None):
            try:
                params = json.loads(args.params)
            except Exception as e:
                print(f"Error: Invalid JSON string for --params: {e}")
                sys.exit(1)

        print(f"\n⚡ Executing composite workflow '{name}'...")
        res = run_workflow(name, parameters=params)
        print(f"Status: {res['status'].upper()} (Duration: {res.get('duration_ms', 0)}ms)")
        if res.get("status") == "success":
            print(f"Completed {res.get('steps_completed', 0)} / {res.get('total_steps', 0)} steps successfully.\n")
            for step in res.get("trace", []):
                print(f"  ✓ [{step['step_id']}] {step['server']}.{step['tool']} ({step['duration_ms']}ms)")
        else:
            print(f"Failed at step: {res.get('failed_step')}")
            print(json.dumps(res.get("error"), indent=2))
        print()


def cmd_hub_start(args: argparse.Namespace) -> None:
    """Start the MCP Hub orchestrator in foreground or background daemon mode."""
    config_path = getattr(args, "config", None)
    is_daemon = bool(getattr(args, "daemon", False))
    is_internal_daemon = bool(getattr(args, "internal_daemon", False))

    from mcp_win_stdio.core.hub.control import (
        HubControlServer,
        HubInstanceManager,
        get_default_pipe_name,
    )
    from mcp_win_stdio.core.hub.orchestrator import HubOrchestrator

    instance_mgr = HubInstanceManager()
    running, existing_meta = instance_mgr.is_running()
    if running and existing_meta:
        print(
            f"Error: MCP Hub is already running (PID {existing_meta.pid}) on "
            f"http://{existing_meta.http_host}:{existing_meta.http_port}."
        )
        sys.exit(1)

    if is_daemon and not is_internal_daemon:
        # Launch detached background process
        ensure_workspace_dirs()
        log_dir = USER_DIR / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / "hub.log"

        cmd = [sys.executable, "-u", "-m", "mcp_win_stdio.cli", "hub", "start", "--internal-daemon"]
        if config_path:
            cmd.extend(["--config", str(Path(config_path).resolve())])

        creationflags = 0
        if sys.platform == "win32":
            creationflags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP

        with open(log_file, "a", encoding="utf-8") as out_f:
            proc = subprocess.Popen(
                cmd,
                creationflags=creationflags,
                stdin=subprocess.DEVNULL,
                stdout=out_f,
                stderr=out_f,
                close_fds=True,
            )

        # Poll for daemon readiness (up to 10 seconds)
        deadline = time.time() + 10.0
        started = False
        meta = None
        while time.time() < deadline:
            time.sleep(0.3)
            is_alive, meta = instance_mgr.is_running()
            if is_alive and meta:
                started = True
                break
            if proc.poll() is not None:
                break

        if started and meta:
            print("=" * 65)
            print(f"   🚀 MCP Hub started in background (PID {meta.pid})")
            print("=" * 65)
            print(f" • HTTP Bridge:   http://{meta.http_host}:{meta.http_port}")
            print(f" • Control Pipe:  {meta.pipe_name}")
            print(f" • Config Source: {meta.config_source} ({meta.config_path or 'default'})")
            print(f" • Log File:      {log_file}")
            print("=" * 65)
            sys.exit(0)
        else:
            print("Error: MCP Hub failed to start within 10 seconds.")
            if log_file.is_file():
                try:
                    with open(log_file, "r", encoding="utf-8") as f:
                        lines = f.readlines()
                        if lines:
                            print("\nRecent log output:")
                            for l in lines[-15:]:
                                print("  " + l.rstrip())
                except Exception:
                    pass
            sys.exit(1)

    # Foreground mode or internal daemon process
    from mcp_win_stdio.core.hub.config_loader import load_hub_config

    try:
        loaded = load_hub_config(cli_path=config_path)
    except Exception as e:
        logger.error("Error loading Hub configuration: %s", e)
        print(f"Error loading Hub configuration: {e}", flush=True)
        sys.exit(1)

    pipe_name = loaded.config.control_socket or get_default_pipe_name()

    try:
        meta = instance_mgr.acquire(
            pid=os.getpid(),
            pipe_name=pipe_name,
            config_path=str(loaded.source_path) if loaded.source_path else None,
            config_source=loaded.source_tier,
            http_host=loaded.config.http_host,
            http_port=loaded.config.http_port,
        )
    except Exception as e:
        logger.error("Error acquiring hub instance lock: %s", e)
        print(f"Error acquiring hub instance lock: {e}", flush=True)
        sys.exit(1)

    orchestrator = HubOrchestrator(loaded_config=loaded)
    stop_event = threading.Event()

    def handle_stop_signal() -> None:
        logger.info("Stop requested via control IPC")
        stop_event.set()

    control_server = HubControlServer(
        orchestrator=orchestrator,
        pipe_name=pipe_name,
        authkey_hex=meta.authkey_hex,
        on_stop_requested=handle_stop_signal,
    )

    try:
        control_server.start()
        status_info = orchestrator.start()
    except Exception as e:
        logger.error("Error starting MCP Hub: %s", e)
        print(f"Error starting MCP Hub: {e}", flush=True)
        control_server.stop()
        instance_mgr.release()
        sys.exit(1)

    if not is_internal_daemon:
        print("=" * 65)
        print(f"   🚀 MCP Hub RUNNING in foreground (PID {os.getpid()})")
        print("=" * 65)
        print(f" • HTTP Bridge:   http://{loaded.config.http_host}:{loaded.config.http_port}")
        print(f" • Control Pipe:  {pipe_name}")
        print(f" • Config Source: {loaded.source_tier} ({loaded.source_path or 'default'})")
        print(f" • Servers:       {len(status_info.servers)} active")
        print("   Press Ctrl+C to stop.")
        print("=" * 65)

    import signal

    def sig_handler(sig: Any, frame: Any) -> None:
        logger.info("Signal %s received", sig)
        stop_event.set()

    try:
        signal.signal(signal.SIGINT, sig_handler)
        signal.signal(signal.SIGTERM, sig_handler)
    except Exception:
        pass

    # Launch uvicorn HTTP server in a worker thread
    uvicorn_server = None
    try:
        import uvicorn

        asgi_app = orchestrator.asgi_app
        uv_cfg = uvicorn.Config(
            app=asgi_app,
            host=loaded.config.http_host,
            port=loaded.config.http_port,
            log_level="warning",
            access_log=False,
        )
        uvicorn_server = uvicorn.Server(uv_cfg)
        uv_thread = threading.Thread(target=uvicorn_server.run, name="mws-uvicorn", daemon=True)
        uv_thread.start()
    except Exception as uve:
        logger.warning("Could not launch uvicorn HTTP listener: %s", uve)

    try:
        while not stop_event.is_set():
            time.sleep(0.5)
    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt caught in main loop")
    except Exception as exc:
        logger.exception("Unexpected exception in main loop: %s", exc)
    finally:
        logger.info("Entering Hub shutdown sequence (stop_event=%s)", stop_event.is_set())
        if not is_internal_daemon:
            print("\nShutting down MCP Hub...")
        if uvicorn_server:
            uvicorn_server.should_exit = True
        control_server.stop()
        orchestrator.stop()
        instance_mgr.release()
        if not is_internal_daemon:
            print("✅ MCP Hub stopped cleanly.")


def cmd_hub_status(args: argparse.Namespace) -> None:
    """Report whether the hub is running, its health, endpoint, uptime, and server states."""
    from mcp_win_stdio.core.hub.control import HubControlClient, HubInstanceManager
    from mcp_win_stdio.core.hub.secrets import redact_sensitive_data

    is_json = bool(getattr(args, "json", False))
    instance_mgr = HubInstanceManager()
    running, meta = instance_mgr.is_running()

    if is_json:
        if not meta:
            print(json.dumps({"running": False, "state": "stopped"}))
            sys.exit(0)

        if not running:
            print(
                json.dumps(
                    {
                        "running": False,
                        "state": "unresponsive",
                        "pid": meta.pid,
                        "pipe_name": meta.pipe_name,
                        "http_endpoint": f"http://{meta.http_host}:{meta.http_port}",
                        "warning": "Hub process is alive in OS kernel but control IPC is unresponsive.",
                    }
                )
            )
            sys.exit(0)

        status_data = HubControlClient.get_status(meta.pipe_name, meta.authkey_hex)
        out = {
            "running": True,
            "pid": meta.pid,
            "pipe_name": meta.pipe_name,
            "http_endpoint": f"http://{meta.http_host}:{meta.http_port}",
            "config_source": meta.config_source,
            "config_path": meta.config_path,
            "details": status_data or {},
        }
        print(json.dumps(redact_sensitive_data(out), indent=2))
        sys.exit(0)

    # Human-readable output
    if not meta:
        print("=" * 65)
        print("   MCP Hub Status: STOPPED")
        print("=" * 65)
        print("No active Hub instance found.")
        print("Run 'mws hub start' to launch the Hub orchestrator.\n")
        sys.exit(0)

    if not running:
        print("=" * 65)
        print(f"   MCP Hub Status: UNRESPONSIVE (PID {meta.pid})")
        print("=" * 65)
        print(f" • Process:       Alive in OS kernel (PID {meta.pid})")
        print(f" • HTTP Bridge:   http://{meta.http_host}:{meta.http_port}")
        print(f" • Control Pipe:  {meta.pipe_name}")
        print(" • Warning:       Control IPC did not respond. Process may be hung or initializing.")
        print(" • Action:        Run 'mws hub stop --force' to terminate or inspect logs.\n")
        sys.exit(0)

    status_data = HubControlClient.get_status(meta.pipe_name, meta.authkey_hex)
    state = status_data.get("state", "running") if status_data else "running"
    uptime = status_data.get("uptime_seconds", 0.0) if status_data else 0.0
    sessions = status_data.get("active_sessions", 0) if status_data else 0

    print("=" * 65)
    print(f"   MCP Hub Status: {state.upper()} (PID {meta.pid})")
    print("=" * 65)
    print(f" • HTTP Bridge:   http://{meta.http_host}:{meta.http_port}")
    print(f" • Control Pipe:  {meta.pipe_name}")
    print(f" • Config Source: {meta.config_source} ({meta.config_path or 'default'})")
    print(f" • Uptime:        {uptime:.1f}s")
    print(f" • Sessions:      {sessions} active")

    servers = status_data.get("servers", {}) if status_data else {}
    if servers:
        print("\n Supervised Servers:")
        print(f"   {'SERVER':<16} {'STATE':<12} {'PID':<8} {'RESTARTS':<8}")
        print("   " + "-" * 48)
        for sname, sinfo in sorted(servers.items()):
            st = sinfo.get("state", "unknown")
            spid = str(sinfo.get("pid") or "-")
            rc = str(sinfo.get("restart_count", 0))
            print(f"   {sname:<16} {st:<12} {spid:<8} {rc:<8}")
    print("=" * 65 + "\n")


def cmd_hub_stop(args: argparse.Namespace) -> None:
    """Request graceful shutdown of the running Hub instance via local control pipe."""
    import signal

    from mcp_win_stdio.core.hub.control import HubControlClient, HubInstanceManager, is_pid_alive

    timeout = float(getattr(args, "timeout", 10.0))
    force = bool(getattr(args, "force", False))
    if timeout <= 0:
        print("Error: --timeout must be a positive number.")
        sys.exit(1)

    instance_mgr = HubInstanceManager()
    running, meta = instance_mgr.is_running()
    if not meta:
        print("MCP Hub is not currently running.")
        sys.exit(0)

    def _force_kill(pid: int) -> None:
        print(f"Force-terminating MCP Hub process (PID {pid})...")
        if sys.platform == "win32":
            subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True)
        else:
            try:
                os.kill(pid, signal.SIGKILL)
            except OSError:
                pass
        deadline = time.time() + 5.0
        while time.time() < deadline:
            if not is_pid_alive(pid):
                break
            time.sleep(0.1)
        instance_mgr.release()

    if force:
        _force_kill(meta.pid)
        if is_pid_alive(meta.pid):
            print(f"Error: Failed to force-terminate MCP Hub (PID {meta.pid}).")
            sys.exit(1)
        print(f"✅ MCP Hub (PID {meta.pid}) force-terminated successfully.")
        sys.exit(0)

    if not running:
        # Process is alive in OS kernel, but control IPC is unresponsive
        print(f"⚠️  MCP Hub (PID {meta.pid}) is alive in kernel but control IPC is unresponsive.")
        print("👉 Use 'mws hub stop --force' to terminate the process.")
        sys.exit(1)

    print(f"Stopping MCP Hub (PID {meta.pid}) via control pipe...")
    HubControlClient.request_stop(meta.pipe_name, meta.authkey_hex, timeout=timeout)

    deadline = time.time() + timeout
    stopped = False
    while time.time() < deadline:
        time.sleep(0.2)
        if not is_pid_alive(meta.pid):
            stopped = True
            break

    if stopped:
        instance_mgr.release()
        print(f"✅ MCP Hub (PID {meta.pid}) stopped successfully.")
        sys.exit(0)
    else:
        print(f"⚠️  MCP Hub (PID {meta.pid}) did not stop within {timeout:.1f} seconds.")
        print("👉 Use 'mws hub stop --force' to force-stop.")
        sys.exit(1)


def cmd_hub_restart(args: argparse.Namespace) -> None:
    """Restart running MCP Hub orchestrator."""
    import signal

    from mcp_win_stdio.core.hub.control import HubControlClient, HubInstanceManager, is_pid_alive

    timeout = float(getattr(args, "timeout", 10.0))
    force = bool(getattr(args, "force", False))
    instance_mgr = HubInstanceManager()
    running, meta = instance_mgr.is_running()

    if meta:
        if running:
            print(f"Stopping MCP Hub (PID {meta.pid}) via control pipe...")
            HubControlClient.request_stop(meta.pipe_name, meta.authkey_hex, timeout=timeout)
            deadline = time.time() + timeout
            while time.time() < deadline:
                time.sleep(0.3)
                is_alive, _ = instance_mgr.is_running()
                if not is_alive:
                    break

        if is_pid_alive(meta.pid):
            if force:
                print(f"Force-terminating MCP Hub process (PID {meta.pid})...")
                if sys.platform == "win32":
                    subprocess.run(["taskkill", "/F", "/PID", str(meta.pid)], capture_output=True)
                else:
                    try:
                        os.kill(meta.pid, signal.SIGKILL)
                    except OSError:
                        pass
                deadline = time.time() + 5.0
                while time.time() < deadline:
                    if not is_pid_alive(meta.pid):
                        break
                    time.sleep(0.1)

                if is_pid_alive(meta.pid):
                    print(f"Error: Failed to terminate existing MCP Hub (PID {meta.pid}); aborting restart.")
                    sys.exit(1)
                instance_mgr.release()
            else:
                print(f"Error: MCP Hub (PID {meta.pid}) failed to stop within {timeout:.1f}s.")
                print("👉 Use 'mws hub restart --force' to force restart.")
                sys.exit(1)

    # Re-verify instance is dead before launching replacement
    still_running, remaining_meta = instance_mgr.is_running()
    if remaining_meta and is_pid_alive(remaining_meta.pid):
        print(f"Error: Existing MCP Hub (PID {remaining_meta.pid}) is still active; aborting restart.")
        sys.exit(1)

    print("Starting MCP Hub orchestrator...")
    cmd_hub_start(args)


def main() -> None:
    """CLI entry point."""
    cleanup_old_executables()
    parser = argparse.ArgumentParser(
        prog="mcp-win-stdio",
        description="Windows-optimized Model Context Protocol suite & setup orchestrator.",
    )
    parser.add_argument("--version", "-v", action="version", version=f"%(prog)s {__version__}")

    subparsers = parser.add_subparsers(dest="command", metavar="<command>", help="Command to execute")

    # 1. server: run mws as the unified on-demand MCP server
    sub_server = subparsers.add_parser(
        "server",
        help="Run mws unified on-demand MCP server (anti-tool-bloat gateway)",
    )
    sub_server.add_argument(
        "server_action",
        nargs="?",
        default="run",
        choices=["run", "list", "doctor", "guide", "stop"],
        help="Action to perform ('run', 'list', 'stop', 'doctor', 'guide')",
    )
    sub_server.add_argument("target_server", nargs="?", default=None, help="Target server name for stop")
    sub_server.add_argument("-v", "--verbose", action="store_true", help="Verbose output for list")
    sub_server.add_argument("-r", "--refresh", action="store_true", help="Force probe refresh for list")
    sub_server.set_defaults(func=cmd_server)

    # 2. guide: universal setup instructions, copy-paste config snippets, and tool specs for all agents
    sub_guide = subparsers.add_parser(
        "guide",
        help="Universal setup instructions, copy-paste config snippets, and tool specs for all agents",
    )
    sub_guide.add_argument(
        "target",
        nargs="?",
        default=None,
        help="Server ('server', 'tsc', 'excel', ...) or client ('gemini', 'claude', 'chatgpt', 'cursor', 'kiro', 'opencode', 'windsurf', 'copilot', 'codex', 'all')",
    )
    sub_guide.add_argument(
        "client",
        nargs="?",
        default=None,
        help="Optional client name to tailor config snippet ('gemini', 'claude', 'chatgpt', 'cursor', 'kiro', 'opencode', 'windsurf', 'copilot', 'codex')",
    )
    sub_guide.set_defaults(func=cmd_guide)

    # 3. run: launch an individual MCP server over stdio
    sub_run = subparsers.add_parser("run", help="Launch an MCP server over stdio")
    sub_run.add_argument("server", help="Server name to launch ('excel', 'word', 'explorer', 'tsc', or custom plugin)")
    sub_run.add_argument(
        "--env-file",
        default=".env",
        help="Optional dotenv file to load before starting the server (default: .env in the current directory)",
    )
    sub_run.set_defaults(func=cmd_run)

    # 4. config: interactive configuration hub
    sub_config = subparsers.add_parser(
        "config",
        aliases=["cfg", "configure"],
        help="Interactive configuration hub for DB, SSH, TSC, and Gateway (~/.mcp-win-stdio/)",
    )
    sub_config.add_argument(
        "domain",
        nargs="?",
        default=None,
        choices=["db", "database", "ssh", "tsc", "typescript", "server", "gateway", "list", "view", "status", "all"],
        help="Configuration domain to edit ('db', 'ssh', 'tsc', 'server', 'list')",
    )
    sub_config.set_defaults(func=cmd_config)

    # 5. doctor: health checks & PATH self-healing
    sub_doctor = subparsers.add_parser("doctor", help="Check system health, dependencies, COM readiness, & PATH")
    sub_doctor.add_argument(
        "--fix-path", action="store_true", help="Configure Python Scripts directory in Windows User PATH"
    )
    sub_doctor.add_argument(
        "--yes",
        "-y",
        action="store_true",
        help="Automatically accept adding missing directories to PATH without prompting",
    )
    sub_doctor.set_defaults(func=cmd_doctor)

    # 6. list: server inventory
    sub_list = subparsers.add_parser("list", help="Show built-in servers and custom plugins with install status")
    sub_list.set_defaults(func=cmd_list)

    # 7. status: project environment readiness
    sub_status = subparsers.add_parser("status", help="Show current environment readiness without modifying files")
    sub_status.set_defaults(func=cmd_status)

    # 8. update: upgrade suite or specific server
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

    # 9. install: pip install packages
    sub_install = subparsers.add_parser("install", help="Install standalone MCP server package(s) from PyPI")
    sub_install.add_argument(
        "server",
        nargs="?",
        default=None,
        help="Server package to install ('excel', 'word', 'explorer', 'tsc', 'db', 'git', 'ssh', 'rag', 'excel-db', 'all')",
    )
    sub_install.set_defaults(func=cmd_install)

    # 10. uninstall: uninstall packages
    sub_uninstall = subparsers.add_parser("uninstall", help="Uninstall MCP server package(s) from Python environment")
    sub_uninstall.add_argument(
        "server",
        nargs="?",
        default=None,
        help="Server to uninstall ('excel', 'word', 'tsc', 'db', 'all', or 'self' to completely remove all mws packages)",
    )
    sub_uninstall.set_defaults(func=cmd_uninstall)

    # 11. workflow: manage and run composite workflows
    sub_wf = subparsers.add_parser(
        "workflow",
        aliases=["wf"],
        help="List, inspect, and run custom multi-step composite workflows",
    )
    sub_wf.add_argument(
        "wf_action",
        nargs="?",
        default="list",
        choices=["list", "run", "view", "delete"],
        help="Action ('list', 'run', 'view', 'delete')",
    )
    sub_wf.add_argument("wf_name", nargs="?", default=None, help="Workflow name")
    sub_wf.add_argument("--params", default=None, help="JSON string of parameter key/value overrides for run")
    sub_wf.set_defaults(func=cmd_workflow)

    # 12. hub: background MCP hub orchestrator
    sub_hub = subparsers.add_parser("hub", help="Manage and operate the background MCP Hub orchestrator")
    sub_hub.set_defaults(func=cmd_hub_status)
    hub_subparsers = sub_hub.add_subparsers(dest="hub_action", metavar="<action>", help="Hub action")

    # mws hub start
    hub_start = hub_subparsers.add_parser("start", help="Start the MCP Hub orchestrator")
    hub_start_group = hub_start.add_mutually_exclusive_group()
    hub_start_group.add_argument(
        "--foreground",
        action="store_true",
        help="Run hub in foreground (default)",
    )
    hub_start_group.add_argument(
        "--daemon",
        action="store_true",
        help="Run hub as detached background process",
    )
    hub_start.add_argument(
        "--config",
        "-c",
        default=None,
        help="Path to hub.yaml configuration file",
    )
    hub_start.add_argument(
        "--internal-daemon",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    hub_start.set_defaults(func=cmd_hub_start)

    # mws hub status
    hub_status = hub_subparsers.add_parser("status", help="Show Hub operational status and server health")
    hub_status.add_argument(
        "--json",
        action="store_true",
        help="Output machine-readable JSON status only",
    )
    hub_status.add_argument(
        "--config",
        "-c",
        default=None,
        help="Optional path to hub.yaml configuration file",
    )
    hub_status.set_defaults(func=cmd_hub_status)

    # mws hub stop
    hub_stop = hub_subparsers.add_parser("stop", help="Stop running MCP Hub orchestrator")
    hub_stop.add_argument(
        "--timeout",
        type=float,
        default=10.0,
        help="Seconds to wait for graceful shutdown (default: 10.0)",
    )
    hub_stop.add_argument(
        "--force",
        "-f",
        action="store_true",
        help="Force-terminate hub process if graceful shutdown fails or IPC is hung",
    )
    hub_stop.set_defaults(func=cmd_hub_stop)

    # mws hub restart
    hub_restart = hub_subparsers.add_parser("restart", help="Restart running MCP Hub orchestrator")
    hub_restart_group = hub_restart.add_mutually_exclusive_group()
    hub_restart_group.add_argument(
        "--foreground",
        action="store_true",
        help="Run restarted hub in foreground",
    )
    hub_restart_group.add_argument(
        "--daemon",
        action="store_true",
        default=True,
        help="Run restarted hub as detached background process (default)",
    )
    hub_restart.add_argument(
        "--config",
        "-c",
        default=None,
        help="Path to hub.yaml configuration file",
    )
    hub_restart.add_argument(
        "--timeout",
        type=float,
        default=10.0,
        help="Seconds to wait for graceful stop (default: 10.0)",
    )
    hub_restart.add_argument(
        "--force",
        "-f",
        action="store_true",
        help="Force-terminate existing hub process if unresponsive",
    )
    hub_restart.set_defaults(func=cmd_hub_restart)

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
        "arch",
        "server",
        "gateway",
        "mws",
        "antigravity",
        "gemini",
        "codex",
        "claude",
        "claudecode",
        "chatgpt",
        "cursor",
        "kiro",
        "opencode",
        "windsurf",
        "copilot",
        "all",
    }
    known_cmds = {
        "hub",
        "server",
        "guide",
        "run",
        "doctor",
        "config",
        "configure",
        "cfg",
        "install",
        "update",
        "upgrade",
        "uninstall",
        "list",
        "status",
        "setup",
        "setup-project",
        "add",
        "add-project",
        "remove-project",
        "remove",
        "init",
        "init-project",
    }
    if len(sys.argv) >= 3 and sys.argv[1].lower() in known_srvs and sys.argv[2].lower() in known_cmds:
        srv_token = sys.argv[1].lower()
        cmd_token = sys.argv[2].lower()
        sys.argv = [sys.argv[0], cmd_token, srv_token] + sys.argv[3:]

    # Retired commands notice dispatcher: non-invasive, no file mutations
    retired_cmds = {
        "setup",
        "init",
        "remove",
        "add",
        "setup-project",
        "add-project",
        "remove-project",
        "init-project",
    }
    if len(sys.argv) >= 2:
        cmd_raw = sys.argv[1].lower()
        if cmd_raw in retired_cmds:
            cmd_retired(argparse.Namespace(command=cmd_raw))
            sys.exit(0)

    args = parser.parse_args()
    if not args.command:
        # Default action for mws CLI: show dashboard
        print_dashboard()
        sys.exit(0)

    args.func(args)


if __name__ == "__main__":
    main()
