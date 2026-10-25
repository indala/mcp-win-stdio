"""
Universal AI client and IDE registry for mcp-win-stdio.
Provides configuration paths, snippet generators, and setup instructions across all major AI tools.
"""

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def _get_py_exe() -> str:
    """Return clean path to current Python executable."""
    return sys.executable.replace("\\", "/")


SUPPORTED_CLIENTS: Dict[str, Dict[str, Any]] = {
    "gemini": {
        "id": "gemini",
        "name": "Gemini & Antigravity IDE",
        "aliases": ["gemini", "antigravity", "agy", "google"],
        "paths": [
            r"%USERPROFILE%\.gemini\config\mcp_config.json",
            r"<workspace>\.agents\mcp_config.json",
            r"<workspace>\.mcp.json",
        ],
        "format": "json",
        "instructions": (
            "1. Open or create %USERPROFILE%\\.gemini\\config\\mcp_config.json (global)\n"
            "   or .agents\\mcp_config.json / .mcp.json in your workspace root.\n"
            "2. Paste the JSON snippet inside the 'mcpServers' object.\n"
            "3. Restart Gemini / Antigravity or reload MCP servers."
        ),
    },
    "claude": {
        "id": "claude",
        "name": "Claude Desktop",
        "aliases": ["claude", "claude-desktop", "desktop"],
        "paths": [
            r"%APPDATA%\Claude\claude_desktop_config.json",
        ],
        "format": "json",
        "instructions": (
            "1. Open Claude Desktop, click Claude menu -> Settings -> Developer -> Edit Config.\n"
            "   (Or open %APPDATA%\\Claude\\claude_desktop_config.json directly).\n"
            "2. Paste the JSON snippet inside the 'mcpServers' object.\n"
            "3. Restart Claude Desktop."
        ),
    },
    "claudecode": {
        "id": "claudecode",
        "name": "Claude Code CLI",
        "aliases": ["claudecode", "claude-code", "cli"],
        "paths": [
            r"%USERPROFILE%\.claude.json",
        ],
        "format": "json",
        "instructions": (
            "1. Open %USERPROFILE%\\.claude.json in your editor.\n"
            "2. Paste the JSON snippet inside the 'mcpServers' object.\n"
            "   (Or run: claude mcp add <server-name> mws <args...>)"
        ),
    },
    "chatgpt": {
        "id": "chatgpt",
        "name": "ChatGPT Desktop",
        "aliases": ["chatgpt", "openai"],
        "paths": [
            r"%APPDATA%\OpenAI\ChatGPT\mcp.json",
            r"%LOCALAPPDATA%\Programs\ChatGPT\resources\mcp.json",
        ],
        "format": "json",
        "instructions": (
            "1. In ChatGPT Desktop, open Settings -> Advanced / Developer -> MCP Servers.\n"
            "   (Or paste into %APPDATA%\\OpenAI\\ChatGPT\\mcp.json).\n"
            "2. Paste the JSON snippet inside 'mcpServers' and save."
        ),
    },
    "cursor": {
        "id": "cursor",
        "name": "Cursor AI IDE",
        "aliases": ["cursor"],
        "paths": [
            r"%APPDATA%\Cursor\User\mcp.json",
            r"<workspace>\.cursor\mcp.json",
            r"<workspace>\.mcp.json",
        ],
        "format": "json",
        "instructions": (
            "1. Open Cursor Settings -> Features -> MCP, click 'Add new MCP server'.\n"
            "   Or paste into %APPDATA%\\Cursor\\User\\mcp.json (global) or <workspace>\\.mcp.json.\n"
            "2. Paste the JSON snippet inside 'mcpServers'."
        ),
    },
    "kiro": {
        "id": "kiro",
        "name": "Kiro IDE",
        "aliases": ["kiro"],
        "paths": [
            r"%APPDATA%\Kiro\mcp.json",
            r"<workspace>\.kiro\mcp.json",
            r"<workspace>\.mcp.json",
        ],
        "format": "json",
        "instructions": (
            "1. Open %APPDATA%\\Kiro\\mcp.json or your project's .kiro\\mcp.json.\n"
            "2. Paste the JSON snippet inside 'mcpServers' and restart Kiro."
        ),
    },
    "opencode": {
        "id": "opencode",
        "name": "OpenCode",
        "aliases": ["opencode"],
        "paths": [
            r"%USERPROFILE%\.opencode\mcp.json",
            r"<workspace>\.opencode\mcp.json",
        ],
        "format": "json",
        "instructions": (
            "1. Open %USERPROFILE%\\.opencode\\mcp.json or your project's .opencode\\mcp.json.\n"
            "2. Paste the JSON snippet inside 'mcpServers'."
        ),
    },
    "windsurf": {
        "id": "windsurf",
        "name": "Codeium Windsurf",
        "aliases": ["windsurf", "codeium"],
        "paths": [
            r"%USERPROFILE%\.codeium\windsurf\mcp_config.json",
            r"<workspace>\.mcp.json",
        ],
        "format": "json",
        "instructions": (
            "1. Open %USERPROFILE%\\.codeium\\windsurf\\mcp_config.json in your editor.\n"
            "2. Paste the JSON snippet inside the 'mcpServers' object and reload."
        ),
    },
    "copilot": {
        "id": "copilot",
        "name": "GitHub Copilot (VS Code)",
        "aliases": ["copilot", "vscode", "code"],
        "paths": [
            r"%APPDATA%\Code\User\mcp.json",
            r"<workspace>\.mcp.json",
        ],
        "format": "json",
        "instructions": (
            "1. In VS Code 1.106+, create or open .mcp.json in your project workspace root,\n"
            "   or open %APPDATA%\\Code\\User\\mcp.json for global access.\n"
            "2. Paste the JSON snippet inside 'mcpServers'."
        ),
    },
    "codex": {
        "id": "codex",
        "name": "OpenAI Codex CLI",
        "aliases": ["codex"],
        "paths": [
            r"%USERPROFILE%\.codex\config.toml",
            r"<workspace>\.codex\config.toml",
        ],
        "format": "toml",
        "instructions": (
            "1. Open %USERPROFILE%\\.codex\\config.toml or your workspace .codex\\config.toml.\n"
            "2. Paste the TOML configuration block at the bottom of the file."
        ),
    },
}


def resolve_client(query: Optional[str]) -> Optional[Dict[str, Any]]:
    """Resolve a client by id or alias."""
    if not query:
        return None
    q = query.lower().strip()
    for client_id, data in SUPPORTED_CLIENTS.items():
        if q == client_id or q in data.get("aliases", []):
            return data
    return None


def get_all_clients() -> List[Dict[str, Any]]:
    """Return all supported clients."""
    return list(SUPPORTED_CLIENTS.values())


def get_actual_windows_paths(client_data: Dict[str, Any]) -> List[str]:
    """Expand environment variables to return actual Windows paths on the local machine."""
    userprofile = os.environ.get("USERPROFILE", str(Path.home()))
    appdata = os.environ.get("APPDATA", str(Path(userprofile) / "AppData" / "Roaming"))
    localappdata = os.environ.get("LOCALAPPDATA", str(Path(userprofile) / "AppData" / "Local"))

    expanded = []
    for p in client_data.get("paths", []):
        ep = p.replace("%USERPROFILE%", userprofile)
        ep = ep.replace("%APPDATA%", appdata)
        ep = ep.replace("%LOCALAPPDATA%", localappdata)
        expanded.append(ep)
    return expanded


def generate_snippet(
    server_name: str,
    client_id: Optional[str] = None,
    use_python_exe: bool = False,
    env_vars: Optional[Dict[str, str]] = None,
) -> str:
    """
    Generate ready-to-copy configuration snippet for a server and optional client.
    Handles 'server' (gateway) or standalone servers ('tsc', 'excel', etc.).
    """
    s_norm = server_name.lower().strip()
    is_gateway = s_norm in ("server", "gateway", "mws")
    server_key = "mws" if is_gateway else s_norm

    client = resolve_client(client_id)
    fmt = client.get("format", "json") if client else "json"

    py_exe = _get_py_exe()

    # Determine command and args
    if use_python_exe:
        command = py_exe
        if is_gateway:
            args = ["-m", "mcp_win_stdio.server"]
        else:
            args = ["-m", "mcp_win_stdio", "run", s_norm]
    else:
        command = "mws"
        if is_gateway:
            args = ["server"]
        else:
            args = ["run", s_norm]

    # Server-specific env defaults if needed
    env: Dict[str, str] = {}
    if s_norm == "db":
        env["DATABASE_URL"] = "postgresql://user:password@localhost:5432/dbname"
    elif s_norm == "explorer":
        env["EXPLORER_ROOT"] = "."
    if env_vars:
        env.update(env_vars)

    if fmt == "toml":
        # TOML for Codex
        lines = [f"[mcp_servers.{server_key}]", f'command = "{command}"', f"args = {json.dumps(args)}"]
        if env:
            lines.append(f"[mcp_servers.{server_key}.env]")
            for k, v in env.items():
                lines.append(f'{k} = "{v}"')
        return "\n".join(lines)

    # JSON format for all other clients
    entry: Dict[str, Any] = {
        "command": command,
        "args": args,
    }
    if env:
        entry["env"] = env

    full_dict = {
        "mcpServers": {
            server_key: entry
        }
    }
    return json.dumps(full_dict, indent=2)
