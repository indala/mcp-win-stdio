"""
Dynamic Tool Catalog & In-Memory Search Engine for mws server.
Introspects tool schemas dynamically, caches them to server_cache.json, and provides relevance search.
"""

import importlib
import json
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from mcp_win_stdio.core.config import SERVER_CACHE_FILE, ensure_workspace_dirs

from .discovery import _denormalize_name, _normalize_name, discover_available_servers
from .process_pool import GLOBAL_POOL

# In-memory schema cache: {server_name: {"updated_at": float, "tools": [...]}}
_IN_MEMORY_CACHE: Dict[str, Dict[str, Any]] = {}

COMMON_ALIASES: Dict[str, List[str]] = {
    "sql": ["sql_query", "query", "sql"],
    "query": ["sql_query", "query", "sql"],
    "sqlquery": ["sql_query", "query"],
    "table": ["table_name", "tablename", "table"],
    "tablename": ["table_name", "tableName"],
    "file": ["file_path", "filepath", "path"],
    "path": ["file_path", "filepath", "path"],
    "filepath": ["file_path"],
    "sheet": ["sheet_name", "sheetname"],
    "sheetname": ["sheet_name"],
    "searchterm": ["search_term", "query", "searchTerm"],
    "term": ["search_term", "searchTerm"],
    "conn": ["connection", "connection_name"],
    "connectionname": ["connection_name", "connection"],
    "dir": ["project_path", "directory_path", "directory"],
    "directory": ["project_path", "directory_path"],
    "project": ["project_path", "project_name"],
    "repo": ["repo_path"],
    "url": ["db_url", "url", "connection_string"],
}


def _to_snake_case(name: str) -> str:
    """Convert camelCase or PascalCase identifier to snake_case."""
    s = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", name)
    return re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s).lower()


def generate_compact_signature(tool_name: str, parameters: Dict[str, Any]) -> str:
    """Generate a compact, readable TypeScript/Python style parameter signature."""
    if not isinstance(parameters, dict):
        return f"{tool_name}()"
    props = parameters.get("properties", {})
    required = set(parameters.get("required", []))
    parts = []
    for prop_name, prop_meta in props.items():
        is_req = prop_name in required
        type_str = prop_meta.get("type", "any") if isinstance(prop_meta, dict) else "any"
        if isinstance(prop_meta, dict) and "anyOf" in prop_meta:
            types = [t.get("type", "any") for t in prop_meta["anyOf"] if isinstance(t, dict)]
            type_str = "/".join(types) if types else "any"

        default_val = prop_meta.get("default") if isinstance(prop_meta, dict) else None
        if is_req:
            parts.append(f"{prop_name}: {type_str}")
        else:
            default_repr = f" = {repr(default_val)}" if isinstance(prop_meta, dict) and "default" in prop_meta else ""
            parts.append(f"{prop_name}?: {type_str}{default_repr}")
    return f"{tool_name}({', '.join(parts)})"


def normalize_arguments(server: str, tool_name: str, arguments: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Intelligently maps parameter aliases, camelCase -> snake_case, and shorthand names
    against the target tool's declared schema properties.
    """
    if not arguments or not isinstance(arguments, dict):
        return arguments or {}

    tool_meta = describe_tool(server, tool_name)
    if not tool_meta:
        return arguments

    params = tool_meta.get("parameters", {})
    props = params.get("properties", {}) if isinstance(params, dict) else {}
    if not props:
        return arguments

    normalized: Dict[str, Any] = {}
    valid_props_lower = {k.lower(): k for k in props.keys()}
    valid_props_clean = {k.lower().replace("_", ""): k for k in props.keys()}

    for k, v in arguments.items():
        # 1. Exact match
        if k in props:
            normalized[k] = v
            continue

        # 2. Convert camelCase to snake_case
        snake_k = _to_snake_case(k)
        if snake_k in props:
            normalized[snake_k] = v
            continue

        # 3. Lowercase match
        if k.lower() in valid_props_lower:
            normalized[valid_props_lower[k.lower()]] = v
            continue

        # 4. Clean match (ignoring underscores)
        clean_k = k.lower().replace("_", "")
        if clean_k in valid_props_clean:
            normalized[valid_props_clean[clean_k]] = v
            continue

        # 5. Semantic alias match
        mapped = False
        if clean_k in COMMON_ALIASES:
            for candidate in COMMON_ALIASES[clean_k]:
                if candidate in props:
                    normalized[candidate] = v
                    mapped = True
                    break
        if mapped:
            continue

        # Fallback: keep original argument
        normalized[k] = v

    return normalized


def _load_disk_cache() -> Dict[str, Any]:
    """Load cached server tool schemas from ~/.mcp-win-stdio/server_cache.json."""
    ensure_workspace_dirs()
    if not SERVER_CACHE_FILE.exists():
        return {}
    try:
        with open(SERVER_CACHE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_disk_cache(cache_data: Dict[str, Any]) -> None:
    """Save tool schemas cache to disk."""
    ensure_workspace_dirs()
    try:
        with open(SERVER_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache_data, f, indent=2)
    except Exception:
        pass


def _introspect_in_process(server_name: str) -> Optional[List[Dict[str, Any]]]:
    """Attempt 0ms in-process introspection if server module is importable."""
    norm = _denormalize_name(server_name)
    mod_name = f"mcp_win_stdio.{norm}.server"
    try:
        mod = importlib.import_module(mod_name)
        mcp_obj = getattr(mod, "mcp", None)
        if mcp_obj and hasattr(mcp_obj, "_tool_manager"):
            raw_tools = mcp_obj._tool_manager.list_tools()
            tools_list = []
            for t in raw_tools:
                params = {}
                if hasattr(t, "parameters"):
                    params = t.parameters if isinstance(t.parameters, dict) else getattr(t.parameters, "model_dump", lambda: {})()
                tools_list.append({
                    "name": getattr(t, "name", str(t)),
                    "description": getattr(t, "description", "") or "",
                    "parameters": params,
                })
            return tools_list
    except Exception:
        return None
    return None


def _introspect_from_schemas(server_name: str) -> Optional[List[Dict[str, Any]]]:
    """Scan schema JSON files if available on disk in Antigravity MCP directory."""
    schema_dir = Path.home() / ".gemini" / "antigravity" / "mcp" / server_name.lower()
    if not schema_dir.exists():
        schema_dir = Path.home() / ".gemini" / "antigravity" / "mcp" / _denormalize_name(server_name.lower())
    if schema_dir.exists() and schema_dir.is_dir():
        tools = []
        for f in sorted(schema_dir.glob("*.json")):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                tools.append({
                    "name": data.get("name", f.stem),
                    "description": data.get("description", ""),
                    "parameters": data.get("parameters", {}),
                })
            except Exception:
                continue
        if tools:
            return tools
    return None


def get_server_tools(server_name: str, force_refresh: bool = False) -> List[Dict[str, Any]]:
    """
    Get all tools and full schemas for a specific server dynamically.
    Checks:
      1. In-memory cache
      2. Disk cache (~/.mcp-win-stdio/server_cache.json)
      3. In-process FastMCP introspection
      4. Dynamic MCP stdio probe via process pool
      5. Schema directory fallback
    """
    canonical = _normalize_name(server_name.lower())

    if not force_refresh:
        # Check in-memory
        if canonical in _IN_MEMORY_CACHE:
            return _IN_MEMORY_CACHE[canonical].get("tools", [])

        # Check disk cache
        disk_cache = _load_disk_cache()
        if canonical in disk_cache and isinstance(disk_cache[canonical], dict):
            cached_tools = disk_cache[canonical].get("tools", [])
            _IN_MEMORY_CACHE[canonical] = {"tools": cached_tools, "updated_at": disk_cache[canonical].get("updated_at", 0)}
            return cached_tools

    # 1. Try fast in-process introspection
    tools = _introspect_in_process(canonical)

    # 2. If not importable, probe live server via MCP JSON-RPC
    if tools is None:
        try:
            proc = GLOBAL_POOL.get_or_spawn(canonical)
            raw_tools = proc.list_tools()
            tools = []
            for t in raw_tools:
                params = t.get("inputSchema") or t.get("parameters") or {}
                tools.append({
                    "name": t.get("name", ""),
                    "description": t.get("description", ""),
                    "parameters": params,
                })
        except Exception:
            tools = None

    # 3. Fallback: schema files directory
    if not tools:
        tools = _introspect_from_schemas(canonical)

    if tools is None:
        tools = []

    # Cache results
    _IN_MEMORY_CACHE[canonical] = {"tools": tools, "updated_at": time.time()}
    disk_cache = _load_disk_cache()
    disk_cache[canonical] = {"tools": tools, "updated_at": time.time()}
    _save_disk_cache(disk_cache)

    return tools


def get_server_catalog(
    server: Optional[str] = None,
    include_tools: bool = False,
    include_signatures: bool = False,
    refresh: bool = False,
) -> Dict[str, Any]:
    """
    Dynamically build catalog of all available MCP servers without hardcoded lists.
    Shows installed status, active/inactive execution status, and live tool counts.
    Optionally filters to a specific server.
    """
    available = discover_available_servers()
    if server:
        clean_target = server.lower().strip()
        available = {k: v for k, v in available.items() if k == clean_target or _normalize_name(k) == clean_target}

    active_sessions = {s["server"]: s for s in GLOBAL_POOL.get_active_sessions()}
    catalog: Dict[str, Any] = {}

    for name, srv_meta in sorted(available.items()):
        is_active = name in active_sessions
        is_installed = srv_meta.get("is_installed", True)
        tools = get_server_tools(name, force_refresh=refresh)

        status = "active" if is_active else ("inactive" if is_installed else "not_installed")

        entry = {
            "status": status,
            "installed": is_installed,
            "type": srv_meta.get("type", "builtin"),
            "tool_count": len(tools),
            "description": srv_meta.get("description", f"MCP server: {name}"),
        }
        if is_active:
            entry["pid"] = active_sessions[name]["pid"]
            entry["uptime_seconds"] = active_sessions[name]["uptime_seconds"]
            entry["call_count"] = active_sessions[name].get("call_count", 0)

        if include_tools:
            if include_signatures:
                entry["tools"] = [
                    {"name": t["name"], "signature": generate_compact_signature(t["name"], t.get("parameters", {}))}
                    for t in tools
                ]
            else:
                entry["tools"] = [t["name"] for t in tools]

        catalog[name] = entry

    return {
        "total_servers": len(catalog),
        "active_processes": len(active_sessions),
        "servers": catalog,
    }


def search_tools(
    query: str,
    server: Optional[str] = None,
    limit: int = 10,
    detail: bool = False,
) -> List[Dict[str, Any]]:
    """
    Dynamically search all tools across all servers or within a specific server.
    Matches tool names, descriptions, and parameter properties.
    Returns compact signatures by default (saving context tokens), or full schemas when detail=True.
    """
    available = discover_available_servers()
    targets = [server.lower()] if server and server.lower() in available else list(available.keys())

    query_tokens = [tok.lower() for tok in re.findall(r"\w+", query) if len(tok) > 1]
    results: List[Dict[str, Any]] = []

    for srv in targets:
        tools = get_server_tools(srv)
        for t in tools:
            name = t.get("name", "")
            desc = t.get("description", "")
            params = t.get("parameters", {})
            param_names = list(params.get("properties", {}).keys()) if isinstance(params, dict) else []

            # Scoring algorithm
            haystack = f"{name} {desc} {' '.join(param_names)} {srv}".lower()
            score = 0

            # Exact match boost
            if query.lower() in name.lower():
                score += 100
            if query.lower() in haystack:
                score += 50

            # Token overlap score
            for tok in query_tokens:
                if tok in name.lower():
                    score += 25
                elif tok in param_names:
                    score += 15
                elif tok in desc.lower():
                    score += 10

            if score > 0:
                item: Dict[str, Any] = {
                    "score": score,
                    "server": srv,
                    "tool": name,
                    "signature": generate_compact_signature(name, params),
                    "description": desc,
                }
                if detail:
                    item["parameters"] = params
                results.append(item)

    # Sort by relevance score descending
    results.sort(key=lambda x: x["score"], reverse=True)
    top_results = results[:limit]

    # Clean score from final output for cleaner token usage
    for r in top_results:
        r.pop("score", None)

    return top_results


def find_servers_for_tool(tool_name: str) -> List[str]:
    """Find all servers that implement a given tool name."""
    clean_name = tool_name.lower().strip()
    available = discover_available_servers()
    matches: List[str] = []
    for srv in available.keys():
        for t in get_server_tools(srv):
            if t.get("name", "").lower() == clean_name:
                matches.append(srv)
                break
    return matches


def describe_tool(server: str, tool_name: str) -> Optional[Dict[str, Any]]:
    """Get full schema and parameter definitions for a specific tool."""
    tools = get_server_tools(server)
    for t in tools:
        if t.get("name", "").lower() == tool_name.lower():
            return {
                "server": server.lower(),
                "tool": t.get("name"),
                "description": t.get("description", ""),
                "parameters": t.get("parameters", {}),
            }
    return None
