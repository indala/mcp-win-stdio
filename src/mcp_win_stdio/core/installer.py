"""
Installer and auto-configuration engine for Claude Desktop and Claude Code CLI.
"""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any, Dict, List, Optional, Tuple

from mcp_win_stdio.core.config import load_config, save_config
from mcp_win_stdio.core.discovery import BUILTIN_SERVERS, get_server_info, list_available_servers


def get_claude_desktop_config_path() -> Optional[Path]:
    """Find claude_desktop_config.json on Windows."""
    appdata = os.environ.get("APPDATA")
    if appdata:
        p = Path(appdata) / "Claude" / "claude_desktop_config.json"
        if p.exists():
            return p
    # Fallback to standard Windows location
    default_p = Path.home() / "AppData" / "Roaming" / "Claude" / "claude_desktop_config.json"
    return default_p if default_p.exists() else None


def get_claude_cli_config_path() -> Optional[Path]:
    """Find .claude.json on Windows."""
    p = Path.home() / ".claude.json"
    return p if p.exists() else None


def install_server_to_desktop(server_name: str) -> Tuple[bool, str]:
    """Install an MCP server into Claude Desktop config."""
    config_path = get_claude_desktop_config_path()
    if not config_path:
        return False, "Claude Desktop configuration file not found in %APPDATA%\\Claude."

    srv = get_server_info(server_name)
    if not srv:
        return False, f"Server '{server_name}' not found."

    # Backup before writing
    try:
        shutil.copy2(config_path, config_path.with_suffix(".json.bak"))
    except Exception:
        pass

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        if "mcpServers" not in data or not isinstance(data["mcpServers"], dict):
            data["mcpServers"] = {}

        python_exe = sys.executable.replace("\\", "/")

        if srv["is_builtin"]:
            args = ["-m", srv["module"]]
        else:
            args = [srv["path"].replace("\\", "/")]

        data["mcpServers"][server_name] = {
            "command": python_exe,
            "args": args,
        }

        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

        return True, f"Configured '{server_name}' in Claude Desktop ({config_path})"
    except Exception as e:
        return False, f"Failed to update Claude Desktop config: {str(e)}"


def install_server_to_cli(server_name: str) -> Tuple[bool, str]:
    """Install an MCP server into Claude Code CLI."""
    srv = get_server_info(server_name)
    if not srv:
        return False, f"Server '{server_name}' not found."

    python_exe = sys.executable.replace("\\", "/")
    if srv["is_builtin"]:
        cmd_args = ["-m", srv["module"]]
    else:
        cmd_args = [srv["path"].replace("\\", "/")]

    # First attempt using `claude mcp add` CLI command
    try:
        res = subprocess.run(
            ["claude", "mcp", "add", "-s", "user", server_name, "--", python_exe] + cmd_args,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if res.returncode == 0:
            return True, f"Registered '{server_name}' in Claude Code CLI via `claude mcp add`"
    except Exception:
        pass

    # Direct fallback: write to ~/.claude.json
    cli_path = get_claude_cli_config_path()
    if cli_path:
        try:
            with open(cli_path, "r", encoding="utf-8") as f:
                cli_data = json.load(f)
            if "mcpServers" not in cli_data:
                cli_data["mcpServers"] = {}
            cli_data["mcpServers"][server_name] = {
                "command": python_exe,
                "args": cmd_args,
            }
            with open(cli_path, "w", encoding="utf-8") as f:
                json.dump(cli_data, f, indent=2)
            return True, f"Configured '{server_name}' directly in {cli_path}"
        except Exception as e:
            return False, f"Failed to configure Claude CLI: {str(e)}"

    return False, "Could not locate or run Claude Code CLI."


def remove_server_from_desktop(server_name: str) -> Tuple[bool, str]:
    """Remove server from Claude Desktop config."""
    config_path = get_claude_desktop_config_path()
    if not config_path or not config_path.exists():
        return False, "Claude Desktop config not found."
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if "mcpServers" in data and server_name in data["mcpServers"]:
            del data["mcpServers"][server_name]
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            return True, f"Removed '{server_name}' from Claude Desktop config."
        return True, f"'{server_name}' was not present in Claude Desktop config."
    except Exception as e:
        return False, f"Error removing server: {str(e)}"


def remove_server_from_cli(server_name: str) -> Tuple[bool, str]:
    """Remove server from Claude CLI."""
    try:
        res = subprocess.run(
            ["claude", "mcp", "remove", "-s", "user", server_name],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if res.returncode == 0:
            return True, f"Removed '{server_name}' from Claude Code CLI."
    except Exception:
        pass
    return False, "Failed to remove from Claude CLI (or claude command not available)."
