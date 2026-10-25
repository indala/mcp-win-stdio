"""
Configuration constants and defaults for mws server.
"""

import json
from pathlib import Path
from typing import Any, Dict, Set

from mcp_win_stdio.core.config import (
    PLUGINS_DIR,
    SERVER_CACHE_FILE,
    SERVER_CUSTOM_FILE,
    USER_DIR,
    ensure_workspace_dirs,
)

DEFAULT_IDLE_TIMEOUT_SECONDS = 600  # 10 minutes idle before auto-reap
MAX_RESPONSE_CHARS = 120_000        # Safeguard agent context window


def _read_custom_file() -> Dict[str, Any]:
    ensure_workspace_dirs()
    if not SERVER_CUSTOM_FILE.exists():
        return {}
    try:
        with open(SERVER_CUSTOM_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _write_custom_file(data: Dict[str, Any]) -> None:
    ensure_workspace_dirs()
    try:
        with open(SERVER_CUSTOM_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass


def load_custom_servers_config() -> Dict[str, Any]:
    """Load external custom MCP server definitions from ~/.mcp-win-stdio/server_custom.json."""
    data = _read_custom_file()
    return data.get("external_servers", data.get("servers", {}))


def load_disabled_servers() -> Set[str]:
    """Load set of disabled server names from ~/.mcp-win-stdio/server_custom.json."""
    data = _read_custom_file()
    disabled = data.get("disabled_servers", [])
    if isinstance(disabled, list):
        return {str(s).lower().strip() for s in disabled if s}
    return set()


def save_disabled_servers(disabled: Set[str]) -> None:
    """Save disabled server names to ~/.mcp-win-stdio/server_custom.json."""
    data = _read_custom_file()
    data["disabled_servers"] = sorted(list(disabled))
    _write_custom_file(data)


def is_server_enabled(name: str) -> bool:
    """Check if a server is currently enabled."""
    disabled = load_disabled_servers()
    return name.lower().strip() not in disabled


def set_server_enabled(name: str, enabled: bool) -> bool:
    """Enable or disable a server. Returns True if changed."""
    clean_name = name.lower().strip()
    disabled = load_disabled_servers()
    if enabled:
        if clean_name in disabled:
            disabled.remove(clean_name)
            save_disabled_servers(disabled)
            return True
        return False
    else:
        if clean_name not in disabled:
            disabled.add(clean_name)
            save_disabled_servers(disabled)
            return True
        return False
