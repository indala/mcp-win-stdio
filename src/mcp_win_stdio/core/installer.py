"""
Installer and transparent configuration engine for Claude Desktop and Claude Code CLI.
"""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any, Dict, List, Optional, Tuple

from mcp_win_stdio.core.config import load_config, save_config
from mcp_win_stdio.core.discovery import get_server_info, list_available_servers


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


def get_server_exec_args(server_name: str) -> Tuple[str, List[str]]:
    """Return the executable path and arguments for a given server."""
    srv = get_server_info(server_name)
    if not srv:
        raise ValueError(f"Server '{server_name}' not found.")

    python_exe = sys.executable.replace("\\", "/")

    if srv["is_builtin"]:
        # Execute via module runner
        args = ["-m", srv["module"].rsplit(".", 1)[0]]  # e.g. -m mcp_win_stdio.excel
    else:
        args = [srv["path"].replace("\\", "/")]

    return python_exe, args


def generate_claude_desktop_snippet(server_name: str, env_vars: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """Generate the JSON dictionary block for Claude Desktop."""
    python_exe, args = get_server_exec_args(server_name)
    block: Dict[str, Any] = {
        "command": python_exe,
        "args": args,
    }
    if env_vars:
        block["env"] = env_vars
    return block


def generate_claude_cli_command(server_name: str, env_vars: Optional[Dict[str, str]] = None) -> str:
    """Generate the exact `claude mcp add` terminal command."""
    python_exe, args = get_server_exec_args(server_name)
    env_flags = ""
    if env_vars:
        env_flags = " ".join([f'-e {k}="{v}"' for k, v in env_vars.items()]) + " "
    return f'claude mcp add -s user {env_flags}{server_name} -- "{python_exe}" {" ".join(args)}'


def install_pip_dependencies(packages: List[str]) -> Tuple[bool, str]:
    """Install required Python packages using pip."""
    if not packages:
        return True, "No extra packages required."

    print(f"\n==> 📦 Installing dependencies: {', '.join(packages)}...")
    cmd = [sys.executable, "-m", "pip", "install"] + packages

    try:
        res = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if res.returncode == 0:
            return True, "Dependencies installed successfully."
        else:
            return False, f"Pip error:\n{res.stderr or res.stdout}"
    except Exception as e:
        return False, f"Failed to run pip: {str(e)}"


def safe_apply_to_desktop(server_name: str, env_vars: Optional[Dict[str, str]] = None) -> Tuple[bool, str]:
    """Safely write configuration into Claude Desktop config with backup."""
    config_path = get_claude_desktop_config_path()
    if not config_path:
        # Create directory if missing
        appdata = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        target_dir = Path(appdata) / "Claude"
        target_dir.mkdir(parents=True, exist_ok=True)
        config_path = target_dir / "claude_desktop_config.json"
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump({"mcpServers": {}}, f, indent=2)

    # Backup existing configuration
    try:
        shutil.copy2(config_path, config_path.with_suffix(".json.bak"))
    except Exception:
        pass

    try:
        data = {}
        if config_path.exists():
            with open(config_path, "r", encoding="utf-8") as f:
                try:
                    data = json.load(f)
                except Exception:
                    data = {}

        if "mcpServers" not in data or not isinstance(data["mcpServers"], dict):
            data["mcpServers"] = {}

        data["mcpServers"][server_name] = generate_claude_desktop_snippet(server_name, env_vars)

        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

        return True, f"Successfully written to Claude Desktop config ({config_path})"
    except Exception as e:
        return False, f"Failed to update Claude Desktop config: {str(e)}"


def safe_apply_to_cli(server_name: str, env_vars: Optional[Dict[str, str]] = None) -> Tuple[bool, str]:
    """Safely register into Claude Code CLI."""
    python_exe, args = get_server_exec_args(server_name)
    
    # Try running `claude mcp add` CLI command
    cmd = ["claude", "mcp", "add", "-s", "user"]
    if env_vars:
        for k, v in env_vars.items():
            cmd.extend(["-e", f"{k}={v}"])
    cmd.extend([server_name, "--", python_exe] + args)

    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if res.returncode == 0:
            return True, f"Successfully registered '{server_name}' in Claude Code CLI via `claude mcp add`"
    except Exception:
        pass

    # Direct fallback to ~/.claude.json
    cli_path = get_claude_cli_config_path() or (Path.home() / ".claude.json")
    try:
        cli_data = {}
        if cli_path.exists():
            with open(cli_path, "r", encoding="utf-8") as f:
                try:
                    cli_data = json.load(f)
                except Exception:
                    cli_data = {}

        if "mcpServers" not in cli_data:
            cli_data["mcpServers"] = {}

        cli_data["mcpServers"][server_name] = generate_claude_desktop_snippet(server_name, env_vars)

        with open(cli_path, "w", encoding="utf-8") as f:
            json.dump(cli_data, f, indent=2)

        return True, f"Successfully written directly to {cli_path}"
    except Exception as e:
        return False, f"Failed to configure Claude CLI: {str(e)}"


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

    cli_path = get_claude_cli_config_path()
    if cli_path and cli_path.exists():
        try:
            with open(cli_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if "mcpServers" in data and server_name in data["mcpServers"]:
                del data["mcpServers"][server_name]
                with open(cli_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2)
                return True, f"Removed '{server_name}' from {cli_path}"
        except Exception:
            pass

    return False, "Failed to remove from Claude CLI (or claude command not available)."
