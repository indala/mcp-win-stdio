"""
Discovery service for built-in MCP servers and user plugins in ~/.mcp-win-stdio/plugins.
"""

import importlib
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional

from mcp_win_stdio.core.config import PLUGINS_DIR, ensure_workspace_dirs

BUILTIN_SERVERS = {
    "excel": {
        "name": "excel",
        "title": "Excel MCP (Windows Native + Pandas)",
        "module": "mcp_win_stdio.excel.server",
        "description": "20 tools: read/write/query/reconcile workbooks with RapidFuzz and native Windows Excel COM automation (PDF export, recalc, pivots, macros).",
        "tools_count": 20,
        "is_builtin": True,
        "dependencies": ["pandas", "openpyxl", "rapidfuzz", "win32com"],
    },
    "explorer": {
        "name": "explorer",
        "title": "Workspace Explorer MCP (Smart Tree & Grep)",
        "module": "mcp_win_stdio.explorer.server",
        "description": "11 tools: token-safe collapsible directory trees, .gitignore resolution, in-file grep, RapidFuzz fuzzy search, and Python/TS AST outline.",
        "tools_count": 11,
        "is_builtin": True,
        "dependencies": ["pathspec", "rapidfuzz"],
    },
}


def list_available_servers() -> Dict[str, Dict[str, Any]]:
    """Return dictionary of all available servers (built-in + user plugins)."""
    ensure_workspace_dirs()
    servers = dict(BUILTIN_SERVERS)

    # Discover custom user plugins in ~/.mcp-win-stdio/plugins
    if PLUGINS_DIR.exists():
        for item in PLUGINS_DIR.glob("*.py"):
            if item.name.startswith("__"):
                continue
            plugin_name = item.stem
            servers[plugin_name] = {
                "name": plugin_name,
                "title": f"User Plugin: {plugin_name}",
                "path": str(item),
                "module": None,
                "description": f"Custom user plugin script loaded from {item}",
                "tools_count": "dynamic",
                "is_builtin": False,
                "dependencies": [],
            }
    return servers


def get_server_info(name: str) -> Optional[Dict[str, Any]]:
    """Get metadata for a specific server."""
    servers = list_available_servers()
    return servers.get(name.lower())
