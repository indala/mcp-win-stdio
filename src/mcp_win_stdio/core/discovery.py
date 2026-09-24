"""
Discovery service for built-in MCP servers and user plugins in ~/.mcp-win-stdio/plugins.
"""

import importlib
import importlib.util
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional

from mcp_win_stdio.core.config import PLUGINS_DIR, ensure_workspace_dirs

BUILTIN_SERVERS = {
    "excel": {
        "name": "excel",
        "title": "Excel MCP (Windows Native + Pandas)",
        "module": "mcp_win_stdio.excel.server",
        "description": "20 tools: Pandas queries, RapidFuzz reconciliation, OpenPyXL editing, and native Excel COM automation (PDF exports, recalc, pivots, macros).",
        "tools_count": 20,
        "is_builtin": True,
        "required_pip": ["pandas>=2.0.0", "openpyxl>=3.1.0", "rapidfuzz>=3.0.0", "pywin32>=306"],
        "dependencies": ["pandas", "openpyxl", "rapidfuzz"],
        "optional_dependencies": ["win32com"],
    },
    "word": {
        "name": "word",
        "title": "Word MCP (Advanced Layout & Typography)",
        "module": "mcp_win_stdio.word.server",
        "description": "10 tools: multi-unit margins (in, cm, mm, pt), multi-column layout, paragraph spacing/indentation, typography (fonts, sizes, colors), images, tables.",
        "tools_count": 10,
        "is_builtin": True,
        "required_pip": ["python-docx>=1.1.0", "pywin32>=306"],
        "dependencies": ["docx"],
        "optional_dependencies": ["win32com"],
    },
    "explorer": {
        "name": "explorer",
        "title": "Workspace Explorer MCP (Smart Tree & Grep)",
        "module": "mcp_win_stdio.explorer.server",
        "description": "11 tools: token-safe collapsible directory trees, .gitignore resolution, in-file grep, RapidFuzz fuzzy search, and Python/TS AST outline.",
        "tools_count": 11,
        "is_builtin": True,
        "required_pip": ["pathspec>=0.12.0", "rapidfuzz>=3.0.0"],
        "dependencies": ["pathspec", "rapidfuzz"],
        "optional_dependencies": [],
    },
    "tsc": {
        "name": "tsc",
        "title": "TypeScript Watcher MCP (0ms Diagnostic Cache)",
        "module": "mcp_win_stdio.tsc.server",
        "description": "6 tools: background tsc compiler watchers, in-memory diagnostic cache, 0ms error checks, and dynamic project switching.",
        "tools_count": 6,
        "is_builtin": True,
        "required_pip": ["mcp>=1.2.0"],
        "dependencies": ["mcp"],
        "optional_dependencies": [],
    },
    "db": {
        "name": "db",
        "title": "Unified Database MCP (PostgreSQL & MySQL)",
        "module": "mcp_win_stdio.db.server",
        "description": "20 tools: polyglot multi-server pooling, cross-schema resolution, DBA management (create, drop, clone, dump), and 0ms connection caching.",
        "tools_count": 20,
        "is_builtin": True,
        "required_pip": ["psycopg2-binary>=2.9.0", "pymysql>=1.1.0"],
        "dependencies": ["psycopg2", "pymysql"],
        "optional_dependencies": [],
    },
}


def check_server_installed(server_info: Dict[str, Any]) -> bool:
    """Check if all mandatory dependencies for a server are importable."""
    if not server_info.get("is_builtin"):
        return Path(server_info.get("path", "")).exists()

    for dep in server_info.get("dependencies", []):
        try:
            if not importlib.util.find_spec(dep):
                return False
        except Exception:
            return False
    return True


def list_available_servers() -> Dict[str, Dict[str, Any]]:
    """Return dictionary of all available servers with live installation status."""
    ensure_workspace_dirs()
    servers = {}

    for name, srv in BUILTIN_SERVERS.items():
        data = dict(srv)
        data["is_installed"] = check_server_installed(data)
        servers[name] = data

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
                "is_installed": True,
                "required_pip": [],
                "dependencies": [],
                "optional_dependencies": [],
            }
    return servers


def get_server_info(name: str) -> Optional[Dict[str, Any]]:
    """Get metadata and live installation status for a specific server."""
    servers = list_available_servers()
    return servers.get(name.lower())
