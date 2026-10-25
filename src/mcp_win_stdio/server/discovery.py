"""
100% Dynamic MCP Server Discovery for mws server.
Discovers available servers, plugins, and custom configurations without hardcoding.
"""

import importlib
import os
import pkgutil
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from mcp_win_stdio.core.config import PLUGINS_DIR, ensure_workspace_dirs

from .config import load_custom_servers_config


def _normalize_name(name: str) -> str:
    """Normalize server module names (e.g. excel_db -> excel-db)."""
    return name.replace("_", "-")


def _denormalize_name(name: str) -> str:
    """Denormalize server names to python identifiers (e.g. excel-db -> excel_db)."""
    return name.replace("-", "_")


def discover_available_servers() -> Dict[str, Dict[str, Any]]:
    """
    Dynamically discover all available MCP servers without any hardcoded lists.
    Discovers:
      1. All installed subpackages under mcp_win_stdio (except server, core, cli).
      2. User plugin scripts in ~/.mcp-win-stdio/plugins/*.py.
      3. Custom external servers defined in ~/.mcp-win-stdio/server_custom.json.
    """
    ensure_workspace_dirs()
    discovered: Dict[str, Dict[str, Any]] = {}

    # 1. Discover subpackages of mcp_win_stdio
    search_paths = []
    try:
        import mcp_win_stdio

        if hasattr(mcp_win_stdio, "__path__"):
            search_paths.extend(list(mcp_win_stdio.__path__))
    except Exception:
        pass

    # Include development workspace packages if running from source
    cwd = Path.cwd()
    repo_packages = cwd / "packages"
    if repo_packages.exists() and repo_packages.is_dir():
        for p in repo_packages.glob("*/src/mcp_win_stdio"):
            if p.is_dir():
                search_paths.append(str(p.resolve()))

    # Deduplicate paths
    unique_paths = []
    for sp in search_paths:
        if sp not in unique_paths and Path(sp).exists():
            unique_paths.append(sp)

    for finder, name, ispkg in pkgutil.iter_modules(unique_paths):
        # Exclude pip-temporary/uninstalled trash dirs, internal packages, and the gateway server itself
        if (
            name.startswith("~")
            or name.startswith("_")
            or not name.isidentifier()
            or name in ("core", "cli", "server", "hub", "__main__", "__pycache__")
        ):
            continue

        canonical_name = _normalize_name(name)
        cmd = [sys.executable, "-m", "mcp_win_stdio", "run", canonical_name]

        # Extract docstring dynamically if available
        description = f"Built-in {canonical_name} MCP server"
        try:
            mod_name = f"mcp_win_stdio.{_denormalize_name(name)}.server"
            spec = importlib.util.find_spec(mod_name)
            if spec and spec.origin:
                with open(spec.origin, "r", encoding="utf-8") as f:
                    first_lines = [f.readline() for _ in range(15)]
                    raw_header = "".join(first_lines).strip()
                    if raw_header.startswith('"""') or raw_header.startswith("'''"):
                        clean_doc = raw_header.strip('"\' \n').splitlines()[0]
                        if clean_doc:
                            description = clean_doc
        except Exception:
            pass

        discovered[canonical_name] = {
            "name": canonical_name,
            "type": "builtin",
            "module": f"mcp_win_stdio.{_denormalize_name(name)}",
            "command": cmd[0],
            "args": cmd[1:],
            "description": description,
        }

    # 2. Discover user plugins in ~/.mcp-win-stdio/plugins
    if PLUGINS_DIR.exists():
        for item in PLUGINS_DIR.glob("*.py"):
            if item.name.startswith("__"):
                continue
            plugin_name = item.stem
            doc = f"User plugin script: {item.name}"
            try:
                content = item.read_text(encoding="utf-8")
                if content.strip().startswith('"""') or content.strip().startswith("'''"):
                    first_line = content.strip()[3:].splitlines()[0].strip().strip('"\'')
                    if first_line:
                        doc = first_line
            except Exception:
                pass

            discovered[plugin_name] = {
                "name": plugin_name,
                "type": "plugin",
                "path": str(item),
                "command": sys.executable,
                "args": [str(item)],
                "description": doc,
            }

    # 3. Discover external servers from server_custom.json
    custom_servers = load_custom_servers_config()
    for name, srv_def in custom_servers.items():
        if isinstance(srv_def, dict) and "command" in srv_def:
            discovered[name] = {
                "name": name,
                "type": "custom",
                "command": srv_def.get("command"),
                "args": srv_def.get("args", []),
                "description": srv_def.get("description", f"Custom external MCP server: {name}"),
            }

    return discovered
