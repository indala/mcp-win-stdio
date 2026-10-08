#!/usr/bin/env python3
"""
Unified Database MCP Server for PostgreSQL and MySQL
Part of mcp-win-stdio.
"""

import csv
import decimal
import os
import sys
import json
import re
import subprocess
import uuid
from datetime import datetime, date, time
from pathlib import Path
from typing import Any, Optional, List, Dict, Union
from urllib.parse import urlparse, unquote

try:
    from mcp.server.mcpserver import MCPServer as FastMCP
except (ImportError, ModuleNotFoundError):
    from mcp.server.fastmcp import FastMCP

# Database drivers
import psycopg2
from psycopg2.extras import RealDictCursor
import pymysql
from pymysql.cursors import DictCursor

mcp = FastMCP("database-mcp")

# Global connection registry & cache
_RAW_CONFIG: Dict[str, Any] = {}
_CONNECTION_REGISTRY: Dict[str, Any] = {}
_ACTIVE_CONNECTION: Optional[str] = None


def _normalize_connection_param(conn: Any) -> Optional[str]:
    """Normalize connection argument, handling null, empty, None, or 'default' string representations from LLM tool calls."""
    if conn is None:
        return None
    s = str(conn).strip()
    if s.lower() in ("", "null", "none", "undefined", "default"):
        return None
    return s


def _is_db_url(url: Any) -> bool:
    """Check if value is a valid database URL string."""
    if not isinstance(url, str):
        return False
    s = url.strip()
    return any(s.startswith(p) for p in ("postgresql://", "postgres://", "mysql://"))


def _parse_url(url: Union[str, Dict[str, Any]]) -> Dict[str, Any]:
    """Parse connection URL or connection dictionary into structured connection info."""
    if isinstance(url, dict):
        if "url" in url and isinstance(url["url"], str):
            return _parse_url(url["url"])
        engine = url.get("engine", url.get("type", "postgres")).lower()
        return {
            "engine": "postgres" if "postgres" in engine else "mysql",
            "host": url.get("host", "localhost"),
            "port": int(url.get("port") or (5432 if "postgres" in engine else 3306)),
            "user": unquote(str(url.get("user", url.get("username", "postgres" if "postgres" in engine else "root")))),
            "password": unquote(str(url.get("password", ""))),
            "database": url.get("database", url.get("dbname", "")),
        }

    u = urlparse(url)
    engine = "postgres" if u.scheme in ("postgres", "postgresql") else "mysql"
    dbname = u.path.lstrip("/") if u.scheme else ""
    return {
        "engine": engine,
        "host": u.hostname or "localhost",
        "port": u.port or (5432 if engine == "postgres" else 3306),
        "user": unquote(u.username or ("postgres" if engine == "postgres" else "root")),
        "password": unquote(u.password or ""),
        "database": dbname or ("postgres" if engine == "postgres" else ""),
    }


def _save_connection(name: str, url: str) -> None:
    """Persist new or updated connection to connections.json."""
    default_config = Path.home() / ".gemini" / "config" / "mcp-servers" / "database-mcp" / "connections.json"
    config_file_env = os.environ.get("CONFIG_FILE")
    cfg_path = Path(config_file_env) if config_file_env else default_config

    try:
        cfg_path.parent.mkdir(parents=True, exist_ok=True)
        data = {}
        if cfg_path.exists():
            with open(cfg_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        if "connections" not in data or not isinstance(data["connections"], dict):
            flat_conns = {k: v for k, v in data.items() if k != "default" and (_is_db_url(v) or isinstance(v, dict))}
            data = {"default": data.get("default", name), "connections": flat_conns}
        data["connections"][name] = url
        with open(cfg_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass


def _save_active_connection(name: str) -> None:
    """Persist active connection choice to connections.json so state remains sticky across restarts."""
    default_config = Path.home() / ".gemini" / "config" / "mcp-servers" / "database-mcp" / "connections.json"
    config_file_env = os.environ.get("CONFIG_FILE")
    cfg_path = Path(config_file_env) if config_file_env else default_config

    try:
        cfg_path.parent.mkdir(parents=True, exist_ok=True)
        data = {}
        if cfg_path.exists():
            with open(cfg_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        data["default"] = name
        with open(cfg_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass


def _init_config() -> None:
    global _ACTIVE_CONNECTION

    # 1. Environment variable SERVERS
    servers_env = os.environ.get("SERVERS")
    if servers_env:
        try:
            parsed = json.loads(servers_env)
            s_map = parsed.get("SERVERS", parsed) if isinstance(parsed, dict) else {}
            for k, v in s_map.items():
                if _is_db_url(v) or isinstance(v, dict):
                    _RAW_CONFIG[k] = v
        except Exception as e:
            sys.stderr.write(f"Warning: Failed to parse SERVERS env: {e}\n")

    # 2. Config file
    default_config = Path.home() / ".gemini" / "config" / "mcp-servers" / "database-mcp" / "connections.json"
    config_file_env = os.environ.get("CONFIG_FILE")
    cfg_path = Path(config_file_env) if config_file_env else default_config

    if cfg_path.exists():
        try:
            with open(cfg_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            # Check if default specified
            default_pointer = data.get("default")
            if isinstance(default_pointer, str) and not _ACTIVE_CONNECTION:
                _ACTIVE_CONNECTION = default_pointer

            if "connections" in data and isinstance(data["connections"], dict):
                conns = data["connections"]
            elif "SERVERS" in data and isinstance(data["SERVERS"], dict):
                conns = data["SERVERS"]
            elif isinstance(data, dict):
                conns = {
                    k: v for k, v in data.items()
                    if k != "default" and (_is_db_url(v) or isinstance(v, dict))
                }
            else:
                conns = {}

            for k, v in conns.items():
                if k not in _RAW_CONFIG and (_is_db_url(v) or isinstance(v, dict)):
                    _RAW_CONFIG[k] = v
        except Exception as e:
            sys.stderr.write(f"Warning: Failed to load config file: {e}\n")

    # 3. Fallback DATABASE_URL
    db_url = os.environ.get("DATABASE_URL")
    if db_url and "default" not in _RAW_CONFIG:
        _RAW_CONFIG["default"] = db_url

    # Reconcile active connection
    if _ACTIVE_CONNECTION:
        matched = next((k for k in _RAW_CONFIG.keys() if k.lower() == _ACTIVE_CONNECTION.lower()), None)
        if matched:
            _ACTIVE_CONNECTION = matched
        elif _RAW_CONFIG:
            _ACTIVE_CONNECTION = next(iter(_RAW_CONFIG.keys()))
        else:
            _ACTIVE_CONNECTION = None
    elif _RAW_CONFIG:
        _ACTIVE_CONNECTION = next(iter(_RAW_CONFIG.keys()))

    # Pre-register all raw configs in connection registry
    for k, v in list(_RAW_CONFIG.items()):
        try:
            url = v if isinstance(v, str) else v.get("url", "")
            if url:
                info = _parse_url(url)
                info["name"] = k
                info["url"] = url
                _CONNECTION_REGISTRY[k] = info
        except Exception:
            pass


_init_config()


def _split_sql_statements(sql: str) -> List[str]:
    """
    Split SQL script into individual statements on semicolons,
    properly ignoring semicolons inside single quotes, double quotes,
    line comments (--), block comments (/* */), and PostgreSQL dollar quotes ($$ or $tag$).
    """
    statements = []
    current = []
    in_single_quote = False
    in_double_quote = False
    in_dollar_quote = False
    dollar_tag = ""
    in_line_comment = False
    in_block_comment = False
    i = 0
    n = len(sql)

    while i < n:
        c = sql[i]
        c2 = sql[i:i+2]

        if in_line_comment:
            if c == "\n":
                in_line_comment = False
            current.append(c)
            i += 1
            continue

        if in_block_comment:
            if c2 == "*/":
                in_block_comment = False
                current.append(c2)
                i += 2
                continue
            current.append(c)
            i += 1
            continue

        if in_single_quote:
            if c == "'":
                if i + 1 < n and sql[i+1] == "'":
                    current.append("''")
                    i += 2
                    continue
                in_single_quote = False
            current.append(c)
            i += 1
            continue

        if in_double_quote:
            if c == '"':
                in_double_quote = False
            current.append(c)
            i += 1
            continue

        if in_dollar_quote:
            if sql[i:i+len(dollar_tag)] == dollar_tag:
                in_dollar_quote = False
                current.append(dollar_tag)
                i += len(dollar_tag)
                continue
            current.append(c)
            i += 1
            continue

        # Check for comments
        if c2 == "--":
            in_line_comment = True
            current.append(c2)
            i += 2
            continue
        if c2 == "/*":
            in_block_comment = True
            current.append(c2)
            i += 2
            continue

        # Check for quotes
        if c == "'":
            in_single_quote = True
            current.append(c)
            i += 1
            continue
        if c == '"':
            in_double_quote = True
            current.append(c)
            i += 1
            continue

        # Check for postgres dollar quote ($$ or $tag$)
        if c == "$":
            m = re.match(r"^\$([a-zA-Z0-9_]*)\$", sql[i:])
            if m:
                dollar_tag = m.group(0)
                in_dollar_quote = True
                current.append(dollar_tag)
                i += len(dollar_tag)
                continue

        # Semicolon outside quotes/comments splits statement
        if c == ";":
            stmt = "".join(current).strip()
            if stmt:
                statements.append(stmt)
            current = []
            i += 1
            continue

        current.append(c)
        i += 1

    rem = "".join(current).strip()
    if rem:
        statements.append(rem)
    return statements


def _format_db_error(
    e: Exception,
    engine: str = "unknown",
    sql: Optional[str] = None,
    statement_idx: Optional[int] = None
) -> Dict[str, Any]:
    """
    Format PostgreSQL and MySQL database errors into rich, actionable diagnostic objects.
    Extracts native error codes, constraint names, details, hints, and statement locations.
    """
    error_payload: Dict[str, Any] = {
        "error": True,
        "engine": engine,
        "error_type": type(e).__name__,
        "message": str(e).strip(),
    }

    if statement_idx is not None:
        error_payload["failed_statement_index"] = statement_idx

    # 1. PostgreSQL error diagnostics
    if isinstance(e, psycopg2.Error):
        code = getattr(e, "pgcode", None)
        diag = getattr(e, "diag", None)
        error_payload["code"] = code

        if diag:
            if diag.message_primary:
                error_payload["message"] = diag.message_primary.strip()
            if diag.message_detail:
                error_payload["detail"] = diag.message_detail.strip()
            if diag.message_hint:
                error_payload["hint"] = diag.message_hint.strip()
            if diag.constraint_name:
                error_payload["constraint"] = diag.constraint_name
            if diag.table_name:
                error_payload["table"] = diag.table_name
            if diag.column_name:
                error_payload["column"] = diag.column_name
            if diag.statement_position:
                error_payload["statement_position"] = diag.statement_position
                if sql:
                    try:
                        pos = int(diag.statement_position) - 1
                        start_pos = max(0, pos - 40)
                        end_pos = min(len(sql), pos + 40)
                        error_payload["sql_context"] = f"... {sql[start_pos:pos]} >>> {sql[pos:pos+1]} <<< {sql[pos+1:end_pos]} ..."
                    except Exception:
                        pass
        if getattr(e, "pgerror", None):
            error_payload["raw_pgerror"] = e.pgerror.strip()

        # Actionable AI suggestions for common PostgreSQL codes
        suggestions = {
            "23503": "Foreign key violation: The referenced key does not exist in the parent table. Verify the parent row exists before inserting or updating.",
            "23505": "Unique key violation: A record with this unique value already exists. Check existing records or use ON CONFLICT DO UPDATE.",
            "23502": "Not null violation: A required NOT NULL column was left empty or missing in INSERT/UPDATE.",
            "42P01": "Undefined table: The relation does not exist in the current search_path. Check schema prefix (e.g. public.table_name) or spelling.",
            "42703": "Undefined column: Column does not exist in table. Use describe_table to inspect available columns.",
            "42601": "Syntax error in SQL statement. Check commas, quotes, and keyword order.",
            "25P02": "Current transaction is aborted: Previous statement failed in this transaction. Rollback before executing further commands.",
            "57014": "Query canceled due to statement timeout.",
        }
        if code and code in suggestions:
            error_payload["suggestion"] = suggestions[code]

    # 2. MySQL error diagnostics
    elif isinstance(e, pymysql.Error):
        code = e.args[0] if len(e.args) > 0 else None
        msg = e.args[1] if len(e.args) > 1 else str(e).strip()
        error_payload["code"] = code
        error_payload["message"] = msg

        mysql_suggestions = {
            1452: "Foreign key constraint failure: Parent row does not exist in referenced table.",
            1062: "Duplicate entry for key: Unique constraint violated.",
            1146: "Table doesn't exist. Check database name and table spelling with list_schemas.",
            1054: "Unknown column: Column does not exist in table. Use describe_table to check column names.",
            1064: "Syntax error in SQL query.",
        }
        if code and code in mysql_suggestions:
            error_payload["suggestion"] = mysql_suggestions[code]

    if sql:
        error_payload["sql_snippet"] = sql[:150] + ("..." if len(sql) > 150 else "")

    return error_payload


def _resolve_conn(connection: Optional[str] = None, server: Optional[str] = None) -> Optional[str]:
    """Helper to resolve connection or server parameter interchangeably."""
    return _normalize_connection_param(connection) or _normalize_connection_param(server)


def _get_connection(
    target_name: Optional[str] = None,
    fallback_server: Optional[str] = None,
    visited: Optional[set] = None
) -> Dict[str, Any]:
    global _ACTIVE_CONNECTION
    if visited is None:
        visited = set()

    # Exact key match in registry first (before normalization)
    if target_name and target_name in _CONNECTION_REGISTRY:
        return _CONNECTION_REGISTRY[target_name]
    if target_name and target_name in _RAW_CONFIG:
        entry = _RAW_CONFIG[target_name]
        url = entry if isinstance(entry, str) else entry.get("url", "")
        info = _parse_url(url)
        info["name"] = target_name
        info["url"] = url
        _CONNECTION_REGISTRY[target_name] = info
        return info

    norm_name = _normalize_connection_param(target_name) or _normalize_connection_param(fallback_server)
    name = norm_name or _ACTIVE_CONNECTION
    if not name:
        raise ValueError("No database connection specified and no active connection set.")

    if name in visited:
        raise ValueError(f"Circular connection reference detected for '{name}'. Available connections: {list(_RAW_CONFIG.keys())}")
    visited.add(name)

    # 0. Raw database URL
    if _is_db_url(name):
        info = _parse_url(name)
        info["name"] = info.get("database") or "custom"
        info["url"] = name
        return info

    # 1. Exact match in registry
    if name in _CONNECTION_REGISTRY:
        return _CONNECTION_REGISTRY[name]

    # 2. Exact match in raw config
    if name in _RAW_CONFIG:
        entry = _RAW_CONFIG[name]
        url = entry if isinstance(entry, str) else entry.get("url", "")
        info = _parse_url(url)
        info["name"] = name
        info["url"] = url
        _CONNECTION_REGISTRY[name] = info
        return info

    # 3. Case-insensitive match in raw config
    for k in _RAW_CONFIG.keys():
        if k.lower() == name.lower() and k not in visited:
            return _get_connection(k, visited=visited)

    # 4. Check if 'name' is the target database name inside any configured server
    for k, v in _RAW_CONFIG.items():
        if k in visited:
            continue
        try:
            url = v if isinstance(v, str) else v.get("url", "")
            if _is_db_url(url):
                p_info = _parse_url(url)
                if p_info.get("database", "").lower() == name.lower():
                    return _get_connection(k, visited=visited)
        except Exception:
            pass

    # 5. Try to derive sibling DB on active server or fallback server
    base_target = _normalize_connection_param(fallback_server) or _ACTIVE_CONNECTION
    if base_target and (base_target in _CONNECTION_REGISTRY or base_target in _RAW_CONFIG):
        curr = _get_connection(base_target, visited=visited)
        u = urlparse(curr["url"])
        new_url = f"{u.scheme}://{u.netloc}/{name}"
        info = _parse_url(new_url)
        info["name"] = name
        info["url"] = new_url

        # Test connect with strict 2-second timeout
        if info["engine"] == "postgres":
            conn = psycopg2.connect(new_url, connect_timeout=2)
            conn.close()
        else:
            conn = pymysql.connect(
                host=info["host"], port=info["port"], user=info["user"],
                password=info["password"], database=info["database"],
                connect_timeout=2
            )
            conn.close()

        _CONNECTION_REGISTRY[name] = info
        _RAW_CONFIG[name] = new_url
        return info

    # 6. Fallback: try connecting to local postgresql://postgres:postgres@localhost:5432/{name}
    try:
        candidate_url = f"postgresql://postgres:postgres@localhost:5432/{name}"
        conn = psycopg2.connect(candidate_url, connect_timeout=2)
        conn.close()
        info = _parse_url(candidate_url)
        info["name"] = name
        info["url"] = candidate_url
        _CONNECTION_REGISTRY[name] = info
        return info
    except Exception:
        pass

    raise ValueError(f"Connection or database '{name}' not found. Available connections: {list(_RAW_CONFIG.keys())}")


def _get_pg_client(info: Dict[str, Any], dbname: Optional[str] = None):
    url = info["url"]
    if dbname:
        u = urlparse(url)
        url = f"{u.scheme}://{u.netloc}/{dbname}"
    return psycopg2.connect(url, cursor_factory=RealDictCursor)


def _get_mysql_client(info: Dict[str, Any], dbname: Optional[str] = None):
    return pymysql.connect(
        host=info["host"],
        port=info["port"],
        user=info["user"],
        password=info["password"],
        database=dbname or info["database"],
        cursorclass=DictCursor,
        autocommit=True
    )


def _resolve_pg_table(cur, table_name: str, schema: Optional[str] = None) -> Dict[str, Any]:
    t = table_name.strip()
    s = schema.strip() if schema else None

    if "." in t:
        parts = t.split(".", 1)
        s = parts[0].strip('"`\'')
        t = parts[1].strip('"`\'')

    if s and s.lower() != "public":
        cur.execute(
            "SELECT table_schema, table_name FROM information_schema.tables WHERE (table_schema = %s OR table_schema ILIKE %s) AND (table_name = %s OR table_name ILIKE %s) LIMIT 1",
            (s, s, t, t)
        )
        row = cur.fetchone()
        if row:
            return {"schema": row["table_schema"], "table": row["table_name"]}
        return {"schema": s, "table": t, "notFound": True}

    # Try public
    cur.execute(
        "SELECT table_schema, table_name FROM information_schema.tables WHERE table_schema = 'public' AND (table_name = %s OR table_name ILIKE %s) LIMIT 1",
        (t, t)
    )
    row = cur.fetchone()
    if row:
        return {"schema": "public", "table": row["table_name"]}

    # Search all non-system
    cur.execute(
        "SELECT table_schema, table_name FROM information_schema.tables WHERE table_schema NOT IN ('pg_catalog', 'information_schema', 'pg_toast') AND (table_name = %s OR table_name ILIKE %s) ORDER BY (table_name = %s) DESC",
        (t, t, t)
    )
    rows = cur.fetchall()
    if rows:
        return {
            "schema": rows[0]["table_schema"],
            "table": rows[0]["table_name"],
            "note": f"Auto-resolved '{t}' to schema '{rows[0]['table_schema']}'."
        }

    return {"schema": s or "public", "table": t, "notFound": True}


PII_COLUMN_PATTERN = re.compile(
    r"^(.*_)?(password|passwd|secret|hash|salt|token|auth|api_key|private_key|card_number|credit_card|cvv|cvc|ssn|pin|access_token)(_.*)?$",
    re.IGNORECASE
)


def _truncate_cell(val: Any, max_chars: int = 500, is_sensitive: bool = False) -> Any:
    """Truncate massive strings or raw binary data and serialize rich DB types (Decimal, UUID, datetime). Masks PII if flagged."""
    if is_sensitive and val is not None:
        return "[REDACTED_SENSITIVE]"
    if val is None:
        return None
    if isinstance(val, (bytes, bytearray, memoryview)):
        return f"<binary data: {len(val)} bytes>"
    if isinstance(val, decimal.Decimal):
        return float(val) if val.is_finite() else str(val)
    if isinstance(val, (datetime, date, time)):
        return val.isoformat()
    if isinstance(val, uuid.UUID):
        return str(val)
    if isinstance(val, (set, tuple)):
        return [_truncate_cell(x, max_chars, is_sensitive) for x in val]
    if isinstance(val, dict):
        return {k: _truncate_cell(v, max_chars, is_sensitive) for k, v in val.items()}
    if isinstance(val, str):
        if len(val) > max_chars:
            return val[:max_chars] + f"... [truncated {len(val) - max_chars} chars]"
        return val
    return val


def _truncate_row(row: Dict[str, Any], max_chars: int = 500, mask_sensitive: bool = False) -> Dict[str, Any]:
    """Truncate all values in a single row dictionary, optionally masking PII / sensitive credentials."""
    res = {}
    for k, v in row.items():
        is_sens = mask_sensitive and bool(PII_COLUMN_PATTERN.match(k))
        res[k] = _truncate_cell(v, max_chars, is_sensitive=is_sens)
    return res


# ==========================================
# MCP TOOLS
# ==========================================


@mcp.tool()
def list_connections() -> Dict[str, Any]:
    """List all configured database connections (PostgreSQL & MySQL) and indicate the active connection."""
    conns = []
    for k, v in _RAW_CONFIG.items():
        try:
            if k in _CONNECTION_REGISTRY:
                info = _CONNECTION_REGISTRY[k]
            else:
                url = v if isinstance(v, str) else v.get("url", "")
                info = _parse_url(url)
                info["name"] = k
                info["url"] = url
                _CONNECTION_REGISTRY[k] = info

            conns.append({
                "name": k,
                "engine": info.get("engine", "unknown"),
                "host": info.get("host", ""),
                "port": info.get("port", ""),
                "database": info.get("database", ""),
                "isActive": k == _ACTIVE_CONNECTION,
                "status": "connected"
            })
        except Exception as e:
            conns.append({
                "name": k,
                "isActive": k == _ACTIVE_CONNECTION,
                "status": "unreachable",
                "error": str(e)
            })
    return {
        "activeConnection": _ACTIVE_CONNECTION,
        "totalConnections": len(conns),
        "connections": conns
    }


@mcp.tool()
def test_connection(
    connection: Optional[str] = None,
    server: Optional[str] = None,
    timeout: int = 3
) -> Dict[str, Any]:
    """
    Test live connectivity and latency to a configured database connection or server.
    
    Args:
        connection: Optional database connection alias or URL to test. Defaults to active connection.
        server: Optional server alias.
        timeout: Socket connection timeout in seconds (default: 3).
    """
    import time
    target = _resolve_conn(connection, server)
    try:
        info = _get_connection(target)
    except Exception as e:
        return {
            "success": False,
            "connected": False,
            "error": str(e),
            "message": f"Connection '{target}' could not be resolved."
        }

    t0 = time.time()
    try:
        if info["engine"] == "postgres":
            conn = psycopg2.connect(info["url"], connect_timeout=timeout)
            with conn.cursor() as cur:
                cur.execute("SELECT version();")
                ver = cur.fetchone()[0]
            conn.close()
        else:
            conn = pymysql.connect(
                host=info["host"],
                port=info["port"],
                user=info["user"],
                password=info["password"],
                database=info["database"] or None,
                connect_timeout=timeout
            )
            with conn.cursor() as cur:
                cur.execute("SELECT version();")
                ver = cur.fetchone()[0]
            conn.close()

        latency_ms = round((time.time() - t0) * 1000, 2)
        return {
            "success": True,
            "connected": True,
            "name": info.get("name"),
            "engine": info["engine"],
            "host": info["host"],
            "port": info["port"],
            "database": info["database"],
            "latencyMs": latency_ms,
            "serverVersion": ver,
            "message": f"Successfully connected to {info['engine']} database '{info['database']}' on {info['host']}:{info['port']} ({latency_ms}ms)."
        }
    except Exception as e:
        latency_ms = round((time.time() - t0) * 1000, 2)
        return {
            "success": False,
            "connected": False,
            "name": info.get("name"),
            "engine": info["engine"],
            "host": info["host"],
            "port": info["port"],
            "latencyMs": latency_ms,
            "error": str(e),
            "message": f"Failed to connect to {info['engine']} on {info['host']}:{info['port']} after {latency_ms}ms: {e}"
        }


@mcp.tool()
def remove_connection(name: str) -> Dict[str, Any]:
    """Remove a configured database connection alias."""
    global _ACTIVE_CONNECTION
    norm_name = _normalize_connection_param(name)
    if not norm_name:
        return {"error": True, "message": "Please specify a connection name to remove."}

    matched_key = None
    for k in list(_RAW_CONFIG.keys()):
        if k.lower() == norm_name.lower():
            matched_key = k
            break

    if not matched_key:
        return {"error": True, "message": f"Connection '{name}' not found. Configured: {list(_RAW_CONFIG.keys())}"}

    _RAW_CONFIG.pop(matched_key, None)
    _CONNECTION_REGISTRY.pop(matched_key, None)

    # Clean up from connections.json if present
    default_config = Path.home() / ".gemini" / "config" / "mcp-servers" / "database-mcp" / "connections.json"
    config_file_env = os.environ.get("CONFIG_FILE")
    cfg_path = Path(config_file_env) if config_file_env else default_config
    try:
        if cfg_path.exists():
            with open(cfg_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if "connections" in data and isinstance(data["connections"], dict):
                data["connections"].pop(matched_key, None)
            else:
                data.pop(matched_key, None)
            if data.get("default") == matched_key:
                data["default"] = next(iter(_RAW_CONFIG.keys()), None)
            with open(cfg_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
    except Exception:
        pass

    if _ACTIVE_CONNECTION == matched_key:
        _ACTIVE_CONNECTION = next(iter(_RAW_CONFIG.keys()), None)
        if _ACTIVE_CONNECTION:
            _save_active_connection(_ACTIVE_CONNECTION)

    return {
        "success": True,
        "message": f"Connection '{matched_key}' removed successfully.",
        "activeConnection": _ACTIVE_CONNECTION,
        "remainingConnections": list(_RAW_CONFIG.keys())
    }


@mcp.tool()
def use_database(
    database: Optional[str] = None,
    server: Optional[str] = None,
    connection: Optional[str] = None,
    name: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Switch active database connection. Supports connection aliases (e.g. 'showreel', 'production'),
    database names, or sibling databases on the active/specified server.
    Sticky connection state is guaranteed for all subsequent tool calls when connection/server is omitted.
    
    Args:
        database: Database name to connect to, or registered connection/server alias.
        server: Optional server or connection alias (e.g. 'showreel', 'localhost') to locate sibling database on.
        connection: Optional alias for server/connection name.
        name: Optional alias for database or connection name.
    """
    global _ACTIVE_CONNECTION
    target = _normalize_connection_param(database) or _normalize_connection_param(connection) or _normalize_connection_param(name) or _normalize_connection_param(server)
    base_server = _normalize_connection_param(server) or _normalize_connection_param(connection)

    if not target and not base_server:
        return {
            "error": True,
            "message": f"Please specify a database name or connection alias. Available connections: {list(_RAW_CONFIG.keys())}"
        }

    if not target:
        target = base_server

    # 1. Check if target directly matches a registered connection name (case-insensitive)
    for k in list(_RAW_CONFIG.keys()):
        if k.lower() == target.lower():
            try:
                info = _get_connection(k)
                _ACTIVE_CONNECTION = info["name"]
                _save_active_connection(_ACTIVE_CONNECTION)
                return {
                    "success": True,
                    "message": f"Active connection switched to '{_ACTIVE_CONNECTION}' ({info['engine']} on {info['host']}:{info['port']}/{info['database']}). Connection alias: '{_ACTIVE_CONNECTION}', Database: '{info['database']}'.",
                    "activeConnection": _ACTIVE_CONNECTION,
                    "engine": info["engine"],
                    "database": info["database"],
                    "host": info["host"],
                    "port": info["port"]
                }
            except Exception as e:
                return _format_db_error(e)

    # 2. Check if target matches a database name inside one of the registered connections
    for k, v in list(_RAW_CONFIG.items()):
        try:
            url = v if isinstance(v, str) else v.get("url", "")
            p_info = _parse_url(url)
            if p_info.get("database", "").lower() == target.lower():
                info = _get_connection(k)
                _ACTIVE_CONNECTION = info["name"]
                _save_active_connection(_ACTIVE_CONNECTION)
                return {
                    "success": True,
                    "message": f"Active connection switched to '{_ACTIVE_CONNECTION}' ({info['engine']} on {info['host']}:{info['port']}/{info['database']}). Connection alias: '{_ACTIVE_CONNECTION}', Database: '{info['database']}'.",
                    "activeConnection": _ACTIVE_CONNECTION,
                    "engine": info["engine"],
                    "database": info["database"],
                    "host": info["host"],
                    "port": info["port"]
                }
        except Exception:
            pass

    # 3. Derive sibling database on specified server or active connection
    base_name = base_server or _ACTIVE_CONNECTION
    if not base_name:
        return {
            "error": True,
            "message": f"No active connection available to derive sibling database '{target}' from. Please specify server/connection parameter. Available: {list(_RAW_CONFIG.keys())}"
        }

    try:
        base_info = _get_connection(base_name)
    except Exception as e:
        return _format_db_error(e)

    u = urlparse(base_info["url"])
    new_url = f"{u.scheme}://{u.netloc}/{target}"
    info = _parse_url(new_url)
    info["name"] = target
    info["url"] = new_url

    # Verify connectivity before registering
    try:
        if info["engine"] == "postgres":
            conn = psycopg2.connect(new_url, connect_timeout=3)
            conn.close()
        else:
            conn = pymysql.connect(
                host=info["host"], port=info["port"], user=info["user"],
                password=info["password"], database=info["database"],
                connect_timeout=3
            )
            conn.close()
    except Exception as e:
        return _format_db_error(e, info["engine"])

    _CONNECTION_REGISTRY[target] = info
    _RAW_CONFIG[target] = new_url
    _ACTIVE_CONNECTION = target
    _save_active_connection(_ACTIVE_CONNECTION)

    return {
        "success": True,
        "message": f"Active connection switched to '{_ACTIVE_CONNECTION}' ({info['engine']} on {info['host']}:{info['port']}/{info['database']}). Connection alias: '{_ACTIVE_CONNECTION}', Database: '{info['database']}'.",
        "activeConnection": _ACTIVE_CONNECTION,
        "engine": info["engine"],
        "database": info["database"],
        "host": info["host"],
        "port": info["port"]
    }


@mcp.tool()
def list_databases(connection: Optional[str] = None, server: Optional[str] = None) -> Dict[str, Any]:
    """List all databases available on the active (or specified) server instance."""
    try:
        info = _get_connection(_resolve_conn(connection, server))
        if info["engine"] == "postgres":
            conn = _get_pg_client(info)
            try:
                with conn.cursor() as cur:
                    cur.execute("SELECT datname, pg_size_pretty(pg_database_size(datname)) AS size FROM pg_database WHERE datistemplate = false AND datname NOT IN ('cloudsqladmin') ORDER BY datname;")
                    rows = cur.fetchall()
                    return {
                        "server": f"{info['host']}:{info['port']}",
                        "engine": "postgres",
                        "currentDatabase": info["database"],
                        "databasesCount": len(rows),
                        "databases": rows
                    }
            finally:
                conn.close()
        else:
            conn = _get_mysql_client(info)
            try:
                with conn.cursor() as cur:
                    cur.execute("SHOW DATABASES;")
                    rows = [r.get("Database", next(iter(r.values()))) for r in cur.fetchall()]
                    return {
                        "server": f"{info['host']}:{info['port']}",
                        "engine": "mysql",
                        "currentDatabase": info["database"],
                        "databasesCount": len(rows),
                        "databases": rows
                    }
            finally:
                conn.close()
    except Exception as e:
        engine = info.get("engine", "unknown") if "info" in locals() else "unknown"
        return _format_db_error(e, engine)


@mcp.tool()
def list_schemas(connection: Optional[str] = None, server: Optional[str] = None) -> Dict[str, Any]:
    """List all user schemas with table count and disk size (PostgreSQL) or current database table summary (MySQL)."""
    try:
        info = _get_connection(_resolve_conn(connection, server))
        if info["engine"] == "postgres":
            conn = _get_pg_client(info)
            try:
                with conn.cursor() as cur:
                    sql = """
                    SELECT
                        n.nspname AS schema_name,
                        count(CASE WHEN c.relkind IN ('r', 'p') THEN 1 END)::int AS table_count,
                        count(CASE WHEN c.relkind IN ('v', 'm') THEN 1 END)::int AS view_count,
                        pg_size_pretty(COALESCE(sum(pg_total_relation_size(c.oid)), 0)) AS total_size
                    FROM pg_namespace n
                    LEFT JOIN pg_class c ON c.relnamespace = n.oid AND c.relkind IN ('r', 'p', 'v', 'm')
                    WHERE n.nspname NOT IN ('pg_catalog', 'information_schema', 'pg_toast')
                      AND n.nspname NOT LIKE 'pg_temp_%'
                    GROUP BY n.nspname
                    ORDER BY n.nspname;
                    """
                    cur.execute(sql)
                    rows = cur.fetchall()
                    return {
                        "connection": info["name"],
                        "database": info["database"],
                        "schemaCount": len(rows),
                        "schemas": rows
                    }
            finally:
                conn.close()
        else:
            conn = _get_mysql_client(info)
            try:
                with conn.cursor() as cur:
                    cur.execute("SELECT table_schema AS schema_name, count(*) AS table_count, ROUND(SUM(data_length + index_length)/1024/1024, 2) AS total_size_mb FROM information_schema.tables WHERE table_schema = DATABASE() GROUP BY table_schema;")
                    rows = cur.fetchall()
                    return {
                        "connection": info["name"],
                        "database": info["database"],
                        "schemas": rows
                    }
            finally:
                conn.close()
    except Exception as e:
        engine = info.get("engine", "unknown") if "info" in locals() else "unknown"
        return _format_db_error(e, engine)


@mcp.tool()
def describe_table(tableName: str, schema: Optional[str] = None, connection: Optional[str] = None, server: Optional[str] = None) -> Dict[str, Any]:
    """Deep inspection of a table: column types, defaults, nullability, PKs, FKs, indexes, and sizes."""
    try:
        info = _get_connection(_resolve_conn(connection, server))
        if info["engine"] == "postgres":
            conn = _get_pg_client(info)
            try:
                with conn.cursor() as cur:
                    resolved = _resolve_pg_table(cur, tableName, schema)
                    if resolved.get("notFound"):
                        return {
                            "error": True,
                            "code": "42P01",
                            "message": f"Table '{tableName}' not found in schema '{resolved['schema']}' or any user schema.",
                            "suggestion": f"Use list_schemas or search_schema(searchTerm='{tableName}') to verify table and schema names."
                        }

                    s = resolved["schema"]
                    t = resolved["table"]

                    cur.execute("SELECT column_name, data_type, character_maximum_length, is_nullable, column_default FROM information_schema.columns WHERE table_schema = %s AND table_name = %s ORDER BY ordinal_position", (s, t))
                    cols = cur.fetchall()

                    cur.execute("SELECT kcu.column_name FROM information_schema.table_constraints tc JOIN information_schema.key_column_usage kcu ON tc.constraint_name = kcu.constraint_name AND tc.table_schema = kcu.table_schema WHERE tc.constraint_type = 'PRIMARY KEY' AND tc.table_schema = %s AND tc.table_name = %s", (s, t))
                    pks = [r["column_name"] for r in cur.fetchall()]

                    cur.execute("""
                    SELECT kcu.column_name, ccu.table_schema AS referenced_schema, ccu.table_name AS referenced_table, ccu.column_name AS referenced_column, rc.update_rule, rc.delete_rule, tc.constraint_name
                    FROM information_schema.table_constraints tc
                    JOIN information_schema.key_column_usage kcu ON tc.constraint_name = kcu.constraint_name AND tc.table_schema = kcu.table_schema
                    JOIN information_schema.constraint_column_usage ccu ON ccu.constraint_name = tc.constraint_name AND ccu.table_schema = tc.table_schema
                    JOIN information_schema.referential_constraints rc ON rc.constraint_name = tc.constraint_name
                    WHERE tc.constraint_type = 'FOREIGN KEY' AND tc.table_schema = %s AND tc.table_name = %s
                    """, (s, t))
                    out_fks = cur.fetchall()

                    cur.execute("""
                    SELECT i.indexname AS index_name, i.indexdef AS definition, pg_size_pretty(pg_relation_size(to_regclass(quote_ident(i.schemaname) || '.' || quote_ident(i.indexname)))) AS index_size, s.idx_scan AS index_scans
                    FROM pg_indexes i
                    LEFT JOIN pg_stat_user_indexes s ON s.schemaname = i.schemaname AND s.relname = i.tablename AND s.indexrelname = i.indexname
                    WHERE i.schemaname = %s AND i.tablename = %s
                    ORDER BY i.indexname
                    """, (s, t))
                    indexes = cur.fetchall()

                    cur.execute("SELECT c.reltuples::bigint AS estimated_rows, pg_size_pretty(pg_total_relation_size(c.oid)) AS total_size FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace WHERE n.nspname = %s AND c.relname = %s", (s, t))
                    stats = cur.fetchone() or {}

                    return {
                        "connection": info["name"],
                        "database": info["database"],
                        "table": t,
                        "schema": s,
                        "resolutionNote": resolved.get("note"),
                        "estimatedRows": stats.get("estimated_rows", 0),
                        "totalSize": stats.get("total_size", "unknown"),
                        "columns": cols,
                        "primaryKeys": pks,
                        "foreignKeys": out_fks,
                        "indexes": indexes
                    }
            finally:
                conn.close()
        else:
            conn = _get_mysql_client(info)
            try:
                with conn.cursor() as cur:
                    cur.execute(f"SHOW FULL COLUMNS FROM `{tableName}`;")
                    cols = cur.fetchall()
                    cur.execute(f"SHOW INDEX FROM `{tableName}`;")
                    indexes = cur.fetchall()
                    cur.execute("SELECT table_rows AS estimated_rows, ROUND((data_length + index_length) / 1024, 2) AS total_size_kb FROM information_schema.tables WHERE table_schema = DATABASE() AND table_name = %s", (tableName,))
                    t_info = cur.fetchone() or {}
                    return {
                        "connection": info["name"],
                        "database": info["database"],
                        "table": tableName,
                        "estimatedRows": t_info.get("estimated_rows", 0),
                        "totalSizeKb": t_info.get("total_size_kb", 0),
                        "columns": cols,
                        "indexes": indexes
                    }
            finally:
                conn.close()
    except Exception as e:
        engine = info.get("engine", "unknown") if "info" in locals() else "unknown"
        return _format_db_error(e, engine)


@mcp.tool()
def get_table_ddl(
    tableName: str,
    schema: Optional[str] = None,
    connection: Optional[str] = None,
    server: Optional[str] = None
) -> Dict[str, Any]:
    """
    Reconstruct and return the complete, ground-truth CREATE TABLE DDL statement for a table.
    Includes all column types, defaults, nullability, primary keys, foreign keys (with ON DELETE/ON UPDATE actions),
    unique/check constraints, and separate table indexes.
    
    Args:
        tableName: Name of the table.
        schema: Optional schema name (defaults to 'public' or auto-resolves in PostgreSQL).
        connection: Optional connection or server name (defaults to active connection).
        server: Optional server or connection alias.
    """
    try:
        info = _get_connection(_resolve_conn(connection, server))
        if info["engine"] == "postgres":
            conn = _get_pg_client(info)
            try:
                with conn.cursor() as cur:
                    resolved = _resolve_pg_table(cur, tableName, schema)
                    if resolved.get("notFound"):
                        return {
                            "error": True,
                            "code": "42P01",
                            "message": f"Table '{tableName}' not found in schema '{resolved['schema']}' or any user schema."
                        }
                    s = resolved["schema"]
                    t = resolved["table"]

                    # Columns
                    cur.execute("""
                    SELECT
                        column_name,
                        data_type,
                        udt_name,
                        character_maximum_length,
                        numeric_precision,
                        numeric_scale,
                        is_nullable,
                        column_default
                    FROM information_schema.columns
                    WHERE table_schema = %s AND table_name = %s
                    ORDER BY ordinal_position;
                    """, (s, t))
                    cols = cur.fetchall()
                    if not cols:
                        return {"error": True, "message": f"Table '{s}.{t}' has no columns."}

                    col_defs = []
                    for c in cols:
                        c_name = c["column_name"]
                        d_type = c["data_type"]
                        udt = c["udt_name"]
                        char_len = c["character_maximum_length"]
                        num_prec = c["numeric_precision"]
                        num_scale = c["numeric_scale"]
                        nullable = c["is_nullable"] == "YES"
                        default = c["column_default"]

                        if d_type == "character varying":
                            type_str = f"varchar({char_len})" if char_len else "varchar"
                        elif d_type == "character":
                            type_str = f"char({char_len})" if char_len else "char"
                        elif d_type == "numeric":
                            if num_prec and num_scale:
                                type_str = f"numeric({num_prec},{num_scale})"
                            elif num_prec:
                                type_str = f"numeric({num_prec})"
                            else:
                                type_str = "numeric"
                        elif d_type == "USER-DEFINED":
                            type_str = udt
                        elif d_type == "ARRAY":
                            type_str = f"{udt.lstrip('_')}[]"
                        else:
                            type_str = d_type

                        parts = [f'"{c_name}" {type_str}']
                        if not nullable:
                            parts.append("NOT NULL")
                        if default:
                            parts.append(f"DEFAULT {default}")
                        col_defs.append("    " + " ".join(parts))

                    # Constraints (PK, Unique, Check, FK)
                    cur.execute("""
                    SELECT
                        con.conname AS constraint_name,
                        con.contype AS constraint_type,
                        pg_get_constraintdef(con.oid, true) AS definition
                    FROM pg_constraint con
                    JOIN pg_class rel ON rel.oid = con.conrelid
                    JOIN pg_namespace nsp ON nsp.oid = rel.relnamespace
                    WHERE nsp.nspname = %s AND rel.relname = %s
                    ORDER BY con.contype, con.conname;
                    """, (s, t))
                    constraints = cur.fetchall()

                    for con in constraints:
                        con_name = con["constraint_name"]
                        con_def = con["definition"]
                        col_defs.append(f'    CONSTRAINT "{con_name}" {con_def}')

                    body = ",\n".join(col_defs)
                    ddl = f'CREATE TABLE "{s}"."{t}" (\n{body}\n);'

                    # Indexes (excluding those already generated by PK/UQ constraints)
                    cur.execute("""
                    SELECT indexname, indexdef
                    FROM pg_indexes
                    WHERE schemaname = %s AND tablename = %s
                      AND indexname NOT IN (
                          SELECT conname FROM pg_constraint con
                          JOIN pg_class rel ON rel.oid = con.conrelid
                          JOIN pg_namespace nsp ON nsp.oid = rel.relnamespace
                          WHERE nsp.nspname = %s AND rel.relname = %s AND con.contype IN ('p', 'u')
                      )
                    ORDER BY indexname;
                    """, (s, t, s, t))
                    idx_rows = cur.fetchall()
                    indexes = [r["indexdef"] + ";" for r in idx_rows]
                    if indexes:
                        full_ddl = ddl + "\n\n-- Indexes\n" + "\n".join(indexes)
                    else:
                        full_ddl = ddl

                    return {
                        "connection": info["name"],
                        "database": info["database"],
                        "schema": s,
                        "table": t,
                        "engine": "postgres",
                        "ddl": full_ddl,
                        "indexesCount": len(indexes),
                        "constraintsCount": len(constraints)
                    }
            finally:
                conn.close()
        else:
            conn = _get_mysql_client(info)
            try:
                with conn.cursor() as cur:
                    cur.execute(f"SHOW CREATE TABLE `{tableName}`;")
                    row = cur.fetchone()
                    ddl = row.get("Create Table") or row.get("CREATE TABLE") or str(row)
                    return {
                        "connection": info["name"],
                        "database": info["database"],
                        "table": tableName,
                        "engine": "mysql",
                        "ddl": ddl + ";"
                    }
            finally:
                conn.close()
    except Exception as e:
        engine = info.get("engine", "unknown") if "info" in locals() else "unknown"
        return _format_db_error(e, engine)


@mcp.tool()
def schema_overview(
    schema: Optional[str] = "public",
    connection: Optional[str] = None,
    server: Optional[str] = None,
    max_tables: int = 60,
) -> Dict[str, Any]:
    """
    High-level architecture map of tables, column summaries, estimated row counts, and disk sizes.
    Capped to prevent context window bloat in large enterprise databases.
    
    Args:
        schema: Target schema name or 'all' (PostgreSQL). Default 'public'.
        connection: Optional connection or server name to query.
        server: Optional server or connection alias.
        max_tables: Maximum number of tables to detail (default 60, max 150).
    """
    safe_max = min(max(1, max_tables), 150)
    try:
        info = _get_connection(_resolve_conn(connection, server))
        if info["engine"] == "postgres":
            conn = _get_pg_client(info)
            try:
                with conn.cursor() as cur:
                    is_all = (schema or "public").lower() == "all"
                    sql = """
                    SELECT n.nspname AS schema, c.relname AS table_name, c.reltuples::bigint AS estimated_rows, pg_size_pretty(pg_total_relation_size(c.oid)) AS total_size
                    FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
                    WHERE c.relkind IN ('r', 'p')
                    """
                    params = []
                    if is_all:
                        sql += " AND n.nspname NOT IN ('pg_catalog', 'information_schema', 'pg_toast') AND n.nspname NOT LIKE 'pg_temp_%'"
                    else:
                        sql += " AND n.nspname = %s"
                        params.append(schema or "public")
                    sql += " ORDER BY n.nspname, c.relname;"
                    if params:
                        cur.execute(sql, tuple(params))
                    else:
                        cur.execute(sql)
                    rows = cur.fetchall()

                    has_more = len(rows) > safe_max
                    display_rows = rows[:safe_max]

                    res: Dict[str, Any] = {
                        "connection": info["name"],
                        "database": info["database"],
                        "totalTableCount": len(rows),
                        "returnedTableCount": len(display_rows),
                        "limitReached": has_more,
                        "tables": display_rows
                    }
                    if has_more:
                        res["notice"] = (
                            f"... [TRUNCATED: Showing first {safe_max} of {len(rows)} tables. "
                            f"Specify a specific schema, or use search_schema/describe_table for targeted inspection] ..."
                        )
                    return res
            finally:
                conn.close()
        else:
            conn = _get_mysql_client(info)
            try:
                with conn.cursor() as cur:
                    cur.execute("SELECT table_name, table_rows AS estimated_rows, ROUND((data_length + index_length) / 1024, 2) AS total_size_kb FROM information_schema.tables WHERE table_schema = DATABASE() ORDER BY table_name;")
                    rows = cur.fetchall()

                    has_more = len(rows) > safe_max
                    display_rows = rows[:safe_max]

                    res: Dict[str, Any] = {
                        "connection": info["name"],
                        "database": info["database"],
                        "totalTableCount": len(rows),
                        "returnedTableCount": len(display_rows),
                        "limitReached": has_more,
                        "tables": display_rows
                    }
                    if has_more:
                        res["notice"] = (
                            f"... [TRUNCATED: Showing first {safe_max} of {len(rows)} tables. "
                            f"Use search_schema or describe_table for targeted inspection] ..."
                        )
                    return res
            finally:
                conn.close()
    except Exception as e:
        engine = info.get("engine", "unknown") if "info" in locals() else "unknown"
        return _format_db_error(e, engine)


@mcp.tool()
def compact_schema_overview(
    schema: Optional[str] = "public",
    connection: Optional[str] = None,
    server: Optional[str] = None,
    max_tables: int = 80
) -> Dict[str, Any]:
    """
    Token-optimized compact schema overview returning ultra-concise 1-line table definitions.
    Example: '• props_management.materials (id: uuid PK, material_number: varchar UQ, department_id: uuid FK->departments)'
    Condenses 50+ enterprise tables into <1000 tokens to protect context windows.
    
    Args:
        schema: Target schema name or 'all' (PostgreSQL, default: 'public').
        connection: Optional target database connection or server alias.
        server: Optional server or connection alias.
        max_tables: Maximum number of tables to include (default: 80, max 150).
    """
    safe_max = min(max(1, max_tables), 150)
    try:
        info = _get_connection(_resolve_conn(connection, server))
        if info["engine"] == "postgres":
            conn = _get_pg_client(info)
            try:
                with conn.cursor() as cur:
                    is_all = (schema or "public").lower() == "all"
                    sql = """
                    SELECT n.nspname AS schema, c.relname AS table_name
                    FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
                    WHERE c.relkind IN ('r', 'p')
                    """
                    params = []
                    if is_all:
                        sql += " AND n.nspname NOT IN ('pg_catalog', 'information_schema', 'pg_toast') AND n.nspname NOT LIKE 'pg_temp_%'"
                    else:
                        sql += " AND n.nspname = %s"
                        params.append(schema or "public")
                    sql += " ORDER BY n.nspname, c.relname;"
                    if params:
                        cur.execute(sql, tuple(params))
                    else:
                        cur.execute(sql)
                    tables = cur.fetchall()

                    display_tables = tables[:safe_max]
                    compact_lines = []

                    for tbl in display_tables:
                        s_name = tbl["schema"]
                        t_name = tbl["table_name"]
                        cur.execute("""
                        SELECT
                            c.column_name,
                            c.data_type,
                            c.udt_name,
                            (SELECT con.contype
                             FROM pg_constraint con
                             JOIN pg_class rel ON rel.oid = con.conrelid
                             JOIN pg_attribute att ON att.attrelid = rel.oid AND att.attnum = ANY(con.conkey)
                             JOIN pg_namespace nsp ON nsp.oid = rel.relnamespace
                             WHERE nsp.nspname = %s AND rel.relname = %s AND att.attname = c.column_name
                             LIMIT 1) AS constraint_type,
                            (SELECT pg_get_constraintdef(con.oid)
                             FROM pg_constraint con
                             JOIN pg_class rel ON rel.oid = con.conrelid
                             JOIN pg_attribute att ON att.attrelid = rel.oid AND att.attnum = ANY(con.conkey)
                             JOIN pg_namespace nsp ON nsp.oid = rel.relnamespace
                             WHERE nsp.nspname = %s AND rel.relname = %s AND att.attname = c.column_name AND con.contype = 'f'
                             LIMIT 1) AS fk_def
                        FROM information_schema.columns c
                        WHERE c.table_schema = %s AND c.table_name = %s
                        ORDER BY c.ordinal_position;
                        """, (s_name, t_name, s_name, t_name, s_name, t_name))
                        cols = cur.fetchall()

                        parts = []
                        for col in cols:
                            c_name = col["column_name"]
                            c_type = col["udt_name"] if col["data_type"] == "USER-DEFINED" else col["data_type"]
                            ctype = col.get("constraint_type")
                            tag = ""
                            if ctype == "p":
                                tag = " PK"
                            elif ctype == "u":
                                tag = " UQ"
                            elif ctype == "f":
                                fk = col.get("fk_def") or ""
                                m = re.search(r"REFERENCES\s+([^\s\(]+)", fk, re.IGNORECASE)
                                ref_target = m.group(1).replace('"', '') if m else "FK"
                                tag = f" FK->{ref_target}"
                            parts.append(f"{c_name}: {c_type}{tag}")

                        compact_lines.append(f"• {s_name}.{t_name} (" + ", ".join(parts) + ")")

                    has_more = len(tables) > safe_max
                    return {
                        "connection": info["name"],
                        "database": info["database"],
                        "totalTables": len(tables),
                        "returnedTables": len(compact_lines),
                        "truncated": has_more,
                        "compactSummary": compact_lines
                    }
            finally:
                conn.close()
        else:
            conn = _get_mysql_client(info)
            try:
                with conn.cursor() as cur:
                    cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = DATABASE() ORDER BY table_name;")
                    tables = [r.get("table_name") or r.get("TABLE_NAME") for r in cur.fetchall()]

                    display_tables = tables[:safe_max]
                    compact_lines = []

                    for t_name in display_tables:
                        cur.execute(f"DESCRIBE `{t_name}`;")
                        cols = cur.fetchall()
                        parts = []
                        for col in cols:
                            f = col.get("Field") or col.get("field")
                            t = col.get("Type") or col.get("type")
                            k = col.get("Key") or col.get("key")
                            tag = ""
                            if k == "PRI":
                                tag = " PK"
                            elif k == "UNI":
                                tag = " UQ"
                            elif k == "MUL":
                                tag = " IDX"
                            parts.append(f"{f}: {t}{tag}")
                        compact_lines.append(f"• {t_name} (" + ", ".join(parts) + ")")

                    return {
                        "connection": info["name"],
                        "database": info["database"],
                        "totalTables": len(tables),
                        "returnedTables": len(compact_lines),
                        "truncated": len(tables) > safe_max,
                        "compactSummary": compact_lines
                    }
            finally:
                conn.close()
    except Exception as e:
        engine = info.get("engine", "unknown") if "info" in locals() else "unknown"
        return _format_db_error(e, engine)


@mcp.tool()
def get_table_sample(
    tableName: str,
    limit: int = 5,
    schema: Optional[str] = None,
    mask_sensitive: bool = True,
    connection: Optional[str] = None,
    server: Optional[str] = None
) -> Dict[str, Any]:
    """
    Fetch sample rows from a table along with column metadata and row count estimate.
    Automatically masks PII and credentials (passwords, tokens, keys) unless mask_sensitive=False.
    
    Args:
        tableName: Name of the table to sample.
        limit: Number of sample rows to retrieve (default 5, max 100).
        schema: Optional schema name (PostgreSQL).
        mask_sensitive: Whether to redact sensitive columns like passwords, secrets, and tokens (default True).
        connection: Optional target database connection or server alias.
        server: Optional server or connection alias.
    """
    lim = min(max(limit, 1), 100)
    try:
        info = _get_connection(_resolve_conn(connection, server))
        if info["engine"] == "postgres":
            conn = _get_pg_client(info)
            try:
                with conn.cursor() as cur:
                    resolved = _resolve_pg_table(cur, tableName, schema)
                    s = resolved["schema"]
                    t = resolved["table"]
                    cur.execute(f'SELECT * FROM "{s}"."{t}" LIMIT %s;', (lim,))
                    rows = cur.fetchall()
                    cleaned_rows = [_truncate_row(r, mask_sensitive=mask_sensitive) for r in rows]
                    return {
                        "connection": info["name"],
                        "database": info["database"],
                        "table": t,
                        "schema": s,
                        "maskedSensitiveData": mask_sensitive,
                        "sampleCount": len(cleaned_rows),
                        "sampleRows": cleaned_rows
                    }
            finally:
                conn.close()
        else:
            conn = _get_mysql_client(info)
            try:
                with conn.cursor() as cur:
                    cur.execute(f"SELECT * FROM `{tableName}` LIMIT %s;", (lim,))
                    rows = cur.fetchall()
                    cleaned_rows = [_truncate_row(r, mask_sensitive=mask_sensitive) for r in rows]
                    return {
                        "connection": info["name"],
                        "database": info["database"],
                        "table": tableName,
                        "maskedSensitiveData": mask_sensitive,
                        "sampleCount": len(cleaned_rows),
                        "sampleRows": cleaned_rows
                    }
            finally:
                conn.close()
    except Exception as e:
        engine = info.get("engine", "unknown") if "info" in locals() else "unknown"
        return _format_db_error(e, engine)


@mcp.tool()
def search_schema(
    searchTerm: str,
    schema: Optional[str] = "all",
    max_results: int = 50,
    connection: Optional[str] = None,
    server: Optional[str] = None
) -> Dict[str, Any]:
    """Search across tables and column names for a keyword with safety limits to protect context window."""
    safe_max = min(max(1, max_results), 100)
    pat = f"%{searchTerm}%"
    try:
        info = _get_connection(_resolve_conn(connection, server))
        if info["engine"] == "postgres":
            conn = _get_pg_client(info)
            try:
                with conn.cursor() as cur:
                    is_all = (schema or "all").lower() == "all"
                    cond = "table_schema NOT IN ('pg_catalog', 'information_schema', 'pg_toast')" if is_all else "table_schema = %s"
                    sql = f"""
                    SELECT 'column' AS match_type, table_schema, table_name, column_name AS match_name, data_type AS details
                    FROM information_schema.columns WHERE {cond} AND (column_name ILIKE %s OR table_name ILIKE %s)
                    UNION ALL
                    SELECT 'table' AS match_type, table_schema, table_name, table_name AS match_name, table_type AS details
                    FROM information_schema.tables WHERE {cond} AND table_name ILIKE %s
                    ORDER BY table_schema, table_name
                    LIMIT {safe_max + 1};
                    """
                    params = [pat, pat, pat] if is_all else [schema, pat, pat, schema, pat]
                    cur.execute(sql, tuple(params))
                    rows = cur.fetchall()
                    has_more = len(rows) > safe_max
                    display_rows = rows[:safe_max]
                    res: Dict[str, Any] = {
                        "connection": info["name"],
                        "matchesCount": len(display_rows),
                        "has_more": has_more,
                        "matches": display_rows
                    }
                    if has_more:
                        res["notice"] = (
                            f"... [TRUNCATED: Showing first {safe_max} schema matches. "
                            f"Narrow your search term to see more specific results] ..."
                        )
                    return res
            finally:
                conn.close()
        else:
            conn = _get_mysql_client(info)
            try:
                with conn.cursor() as cur:
                    sql = f"""
                    SELECT 'column' AS match_type, table_schema, table_name, column_name AS match_name, data_type AS details
                    FROM information_schema.columns WHERE table_schema = DATABASE() AND (column_name LIKE %s OR table_name LIKE %s)
                    UNION ALL
                    SELECT 'table' AS match_type, table_schema, table_name, table_name AS match_name, table_type AS details
                    FROM information_schema.tables WHERE table_schema = DATABASE() AND table_name LIKE %s
                    ORDER BY table_name
                    LIMIT {safe_max + 1};
                    """
                    cur.execute(sql, (pat, pat, pat))
                    rows = cur.fetchall()
                    has_more = len(rows) > safe_max
                    display_rows = rows[:safe_max]
                    res: Dict[str, Any] = {
                        "connection": info["name"],
                        "matchesCount": len(display_rows),
                        "has_more": has_more,
                        "matches": display_rows
                    }
                    if has_more:
                        res["notice"] = (
                            f"... [TRUNCATED: Showing first {safe_max} schema matches. "
                            f"Narrow your search term to see more specific results] ..."
                        )
                    return res
            finally:
                conn.close()
    except Exception as e:
        engine = info.get("engine", "unknown") if "info" in locals() else "unknown"
        return _format_db_error(e, engine)


@mcp.tool()
def read_query(
    sql: str,
    params: Optional[List[Any]] = None,
    limit: int = 50,
    max_cell_chars: int = 500,
    connection: Optional[str] = None,
    server: Optional[str] = None
) -> Dict[str, Any]:
    """
    Safely execute a read-only SELECT query inside a read-only transaction with automatic rollback and token-safe pagination.
    Forwards native PostgreSQL / MySQL error diagnostics directly upon error.
    
    Args:
        sql: SELECT SQL query.
        params: Optional query parameters.
        limit: Max rows to return (default 50, max 200).
        max_cell_chars: Max characters per cell (default 500).
        connection: Optional target database connection or server alias.
        server: Optional server or connection alias.
    """
    try:
        info = _get_connection(_resolve_conn(connection, server))
    except Exception as e:
        return _format_db_error(e, "unknown", sql)

    safe_limit = min(max(1, limit), 200)

    if info["engine"] == "postgres":
        try:
            conn = _get_pg_client(info)
        except Exception as e:
            return _format_db_error(e, "postgres", sql)

        try:
            conn.set_session(readonly=True, autocommit=False)
            with conn.cursor() as cur:
                # Issue #4 fix: NEVER pass empty tuple () to avoid psycopg2 parsing % in LIKE '%...' as %s placeholder
                if params:
                    cur.execute(sql, tuple(params))
                else:
                    cur.execute(sql)

                fetched = cur.fetchmany(safe_limit + 1)
                has_more = len(fetched) > safe_limit
                display_rows = fetched[:safe_limit]
                cleaned_rows = [_truncate_row(r, max_cell_chars) for r in display_rows]

                result: Dict[str, Any] = {
                    "connection": info["name"],
                    "database": info["database"],
                    "returned_rows": len(cleaned_rows),
                    "has_more": has_more,
                    "rows": cleaned_rows,
                }
                if has_more:
                    result["notice"] = (
                        f"... [TRUNCATED: Showing first {safe_limit} rows. Additional rows omitted to protect "
                        f"context window. Use SQL LIMIT / OFFSET or WHERE clauses to query specific subsets] ..."
                    )
                return result
        except (psycopg2.Error, Exception) as e:
            return _format_db_error(e, "postgres", sql)
        finally:
            try:
                conn.rollback()
            except Exception:
                pass
            conn.close()
    else:
        try:
            conn = _get_mysql_client(info)
        except Exception as e:
            return _format_db_error(e, "mysql", sql)

        try:
            with conn.cursor() as cur:
                if params:
                    cur.execute(sql, tuple(params))
                else:
                    cur.execute(sql)

                fetched = cur.fetchmany(safe_limit + 1)
                has_more = len(fetched) > safe_limit
                display_rows = fetched[:safe_limit]
                cleaned_rows = [_truncate_row(r, max_cell_chars) for r in display_rows]

                result: Dict[str, Any] = {
                    "connection": info["name"],
                    "database": info["database"],
                    "returned_rows": len(cleaned_rows),
                    "has_more": has_more,
                    "rows": cleaned_rows,
                }
                if has_more:
                    result["notice"] = (
                        f"... [TRUNCATED: Showing first {safe_limit} rows. Additional rows omitted to protect "
                        f"context window. Use SQL LIMIT / OFFSET or WHERE clauses to query specific subsets] ..."
                    )
                return result
        except (pymysql.Error, Exception) as e:
            return _format_db_error(e, "mysql", sql)
        finally:
            conn.close()


@mcp.tool()
def execute_query(
    sql: str,
    params: Optional[List[Any]] = None,
    dry_run: bool = False,
    connection: Optional[str] = None,
    server: Optional[str] = None
) -> Dict[str, Any]:
    """
    Execute INSERT, UPDATE, DELETE, or DDL statement(s).
    Supports transactional multi-statement batch execution with statement-by-statement progress,
    exact line/statement failure diagnostics, and dry_run rollback support.
    
    Args:
        sql: SQL statement or semicolon-separated batch (e.g. CREATE TABLE ...; ALTER TABLE ...;).
        params: Optional parameter list for single statements (e.g. [123, "active"]).
        dry_run: If True, executes inside a transaction and rolls back (default False).
        connection: Connection name to target (defaults to active connection).
        server: Optional server or connection alias.
    """
    try:
        info = _get_connection(_resolve_conn(connection, server))
    except Exception as e:
        return _format_db_error(e, "unknown", sql)

    statements = _split_sql_statements(sql)
    if not statements:
        return {"error": True, "message": "SQL statement string is empty."}

    # =========================================================================
    # SINGLE STATEMENT EXECUTION
    # =========================================================================
    if len(statements) == 1:
        single_sql = statements[0]
        if info["engine"] == "postgres":
            try:
                conn = _get_pg_client(info)
            except Exception as e:
                return _format_db_error(e, "postgres", single_sql)

            try:
                with conn.cursor() as cur:
                    if params:
                        cur.execute(single_sql, tuple(params))
                    else:
                        cur.execute(single_sql)

                    rowcount = cur.rowcount
                    status = cur.statusmessage or "SUCCESS"
                    if dry_run:
                        conn.rollback()
                        return {
                            "connection": info["name"],
                            "dryRun": True,
                            "status": "SUCCESS (ROLLED BACK)",
                            "rowCount": rowcount,
                            "statusMessage": status
                        }
                    else:
                        conn.commit()
                        return {
                            "connection": info["name"],
                            "status": status,
                            "rowCount": rowcount
                        }
            except (psycopg2.Error, Exception) as e:
                try:
                    conn.rollback()
                except Exception:
                    pass
                return _format_db_error(e, "postgres", single_sql)
            finally:
                conn.close()
        else:
            try:
                conn = _get_mysql_client(info)
            except Exception as e:
                return _format_db_error(e, "mysql", single_sql)

            try:
                with conn.cursor() as cur:
                    cur.execute("START TRANSACTION;")
                    if params:
                        cur.execute(single_sql, tuple(params))
                    else:
                        cur.execute(single_sql)

                    rowcount = cur.rowcount
                    if dry_run:
                        cur.execute("ROLLBACK;")
                        return {
                            "connection": info["name"],
                            "dryRun": True,
                            "status": "SUCCESS (ROLLED BACK)",
                            "rowCount": rowcount
                        }
                    else:
                        cur.execute("COMMIT;")
                        return {
                            "connection": info["name"],
                            "status": "SUCCESS",
                            "rowCount": rowcount
                        }
            except (pymysql.Error, Exception) as e:
                try:
                    conn.rollback()
                except Exception:
                    pass
                return _format_db_error(e, "mysql", single_sql)
            finally:
                conn.close()

    # =========================================================================
    # MULTI-STATEMENT BATCH EXECUTION (Transactional with progress reporting)
    # =========================================================================
    if info["engine"] == "postgres":
        try:
            conn = _get_pg_client(info)
        except Exception as e:
            return _format_db_error(e, "postgres", sql)

        executed_statements = []
        total_rows_affected = 0
        try:
            with conn.cursor() as cur:
                for idx, stmt in enumerate(statements):
                    try:
                        cur.execute(stmt)
                        rc = cur.rowcount if cur.rowcount != -1 else 0
                        total_rows_affected += rc
                        executed_statements.append({
                            "statement_index": idx + 1,
                            "snippet": stmt[:80] + ("..." if len(stmt) > 80 else ""),
                            "status": cur.statusmessage or "OK",
                            "rows_affected": rc
                        })
                    except (psycopg2.Error, Exception) as stmt_err:
                        conn.rollback()
                        err_res = _format_db_error(stmt_err, "postgres", stmt, statement_idx=idx + 1)
                        err_res["batch_execution_failed"] = True
                        err_res["total_statements"] = len(statements)
                        err_res["successful_statements_count"] = idx
                        err_res["executed_statements"] = executed_statements
                        err_res["failed_statement"] = stmt
                        return err_res

                if dry_run:
                    conn.rollback()
                    return {
                        "connection": info["name"],
                        "dryRun": True,
                        "status": "BATCH SUCCESS (ROLLED BACK)",
                        "total_statements": len(statements),
                        "total_rows_affected": total_rows_affected,
                        "executed_statements": executed_statements
                    }
                else:
                    conn.commit()
                    return {
                        "connection": info["name"],
                        "dryRun": False,
                        "status": "BATCH SUCCESS",
                        "total_statements": len(statements),
                        "total_rows_affected": total_rows_affected,
                        "executed_statements": executed_statements
                    }
        finally:
            conn.close()
    else:
        try:
            conn = _get_mysql_client(info)
        except Exception as e:
            return _format_db_error(e, "mysql", sql)

        executed_statements = []
        total_rows_affected = 0
        try:
            with conn.cursor() as cur:
                cur.execute("START TRANSACTION;")
                for idx, stmt in enumerate(statements):
                    try:
                        cur.execute(stmt)
                        rc = cur.rowcount if cur.rowcount != -1 else 0
                        total_rows_affected += rc
                        executed_statements.append({
                            "statement_index": idx + 1,
                            "snippet": stmt[:80] + ("..." if len(stmt) > 80 else ""),
                            "status": "OK",
                            "rows_affected": rc
                        })
                    except (pymysql.Error, Exception) as stmt_err:
                        cur.execute("ROLLBACK;")
                        err_res = _format_db_error(stmt_err, "mysql", stmt, statement_idx=idx + 1)
                        err_res["batch_execution_failed"] = True
                        err_res["total_statements"] = len(statements)
                        err_res["successful_statements_count"] = idx
                        err_res["executed_statements"] = executed_statements
                        err_res["failed_statement"] = stmt
                        return err_res

                if dry_run:
                    cur.execute("ROLLBACK;")
                    return {
                        "connection": info["name"],
                        "dryRun": True,
                        "status": "BATCH SUCCESS (ROLLED BACK)",
                        "total_statements": len(statements),
                        "total_rows_affected": total_rows_affected,
                        "executed_statements": executed_statements
                    }
                else:
                    cur.execute("COMMIT;")
                    return {
                        "connection": info["name"],
                        "dryRun": False,
                        "status": "BATCH SUCCESS",
                        "total_statements": len(statements),
                        "total_rows_affected": total_rows_affected,
                        "executed_statements": executed_statements
                    }
        finally:
            conn.close()


@mcp.tool()
def explain_query(sql: str, analyze: bool = True, connection: Optional[str] = None, server: Optional[str] = None) -> Dict[str, Any]:
    """Run EXPLAIN on a SQL statement to inspect execution plan and costs."""
    try:
        info = _get_connection(_resolve_conn(connection, server))
    except Exception as e:
        return _format_db_error(e, "unknown", sql)

    if info["engine"] == "postgres":
        try:
            conn = _get_pg_client(info)
        except Exception as e:
            return _format_db_error(e, "postgres", sql)

        try:
            with conn.cursor() as cur:
                exp = f"EXPLAIN (ANALYZE, BUFFERS, COSTS, VERBOSE, FORMAT JSON) {sql}" if analyze else f"EXPLAIN (COSTS, VERBOSE, FORMAT JSON) {sql}"
                cur.execute(exp)
                res = cur.fetchone()
                return {"connection": info["name"], "plan": res[list(res.keys())[0]]}
        except (psycopg2.Error, Exception) as e:
            return _format_db_error(e, "postgres", sql)
        finally:
            conn.close()
    else:
        try:
            conn = _get_mysql_client(info)
        except Exception as e:
            return _format_db_error(e, "mysql", sql)

        try:
            with conn.cursor() as cur:
                cur.execute(f"EXPLAIN FORMAT=JSON {sql}")
                res = cur.fetchone()
                return {"connection": info["name"], "plan": res}
        except (pymysql.Error, Exception) as e:
            return _format_db_error(e, "mysql", sql)
        finally:
            conn.close()


@mcp.tool()
def get_database_stats(connection: Optional[str] = None, server: Optional[str] = None) -> Dict[str, Any]:
    """Get database metrics: database size, active connections, cache hit ratio, engine version."""
    try:
        info = _get_connection(_resolve_conn(connection, server))
        if info["engine"] == "postgres":
            conn = _get_pg_client(info)
            try:
                with conn.cursor() as cur:
                    sql = """
                    SELECT
                        current_database() AS database_name,
                        pg_size_pretty(pg_database_size(current_database())) AS database_size,
                        (SELECT count(*) FROM pg_stat_activity WHERE datname = current_database()) AS active_connections,
                        (SELECT round(100.0 * sum(blks_hit) / nullif(sum(blks_hit + blks_read), 0), 2) FROM pg_stat_database WHERE datname = current_database()) AS cache_hit_ratio_percent,
                        version() AS postgres_version;
                    """
                    cur.execute(sql)
                    stats = cur.fetchone()
                    return {"connection": info["name"], "stats": stats}
            finally:
                conn.close()
        else:
            conn = _get_mysql_client(info)
            try:
                with conn.cursor() as cur:
                    cur.execute("SELECT ROUND(SUM(data_length + index_length) / 1024 / 1024, 2) AS db_size_mb FROM information_schema.tables WHERE table_schema = DATABASE();")
                    size_res = cur.fetchone() or {}
                    cur.execute("SELECT VERSION() as version;")
                    ver_res = cur.fetchone() or {}
                    return {
                        "connection": info["name"],
                        "stats": {
                            "database": info["database"],
                            "sizeMb": size_res.get("db_size_mb", 0),
                            "version": ver_res.get("version")
                        }
                    }
            finally:
                conn.close()
    except Exception as e:
        engine = info.get("engine", "unknown") if "info" in locals() else "unknown"
        return _format_db_error(e, engine)


@mcp.tool()
def add_connection(name: str, url: str, type: Optional[str] = None, setActive: bool = True) -> Dict[str, Any]:
    """Dynamically add a new PostgreSQL or MySQL connection at runtime."""
    global _ACTIVE_CONNECTION
    try:
        info = _parse_url(url)
        if type:
            info["engine"] = type.lower()
        info["name"] = name
        info["url"] = url

        # Test connect
        if info["engine"] == "postgres":
            conn = psycopg2.connect(url, connect_timeout=3)
            conn.close()
        else:
            conn = pymysql.connect(
                host=info["host"], port=info["port"], user=info["user"],
                password=info["password"], database=info["database"],
                connect_timeout=3
            )
            conn.close()

        _CONNECTION_REGISTRY[name] = info
        _RAW_CONFIG[name] = url
        _save_connection(name, url)
        if setActive:
            _ACTIVE_CONNECTION = name
            _save_active_connection(_ACTIVE_CONNECTION)

        return {
            "success": True,
            "message": f"Connection '{name}' ({info['engine']}) successfully connected and registered.",
            "isActive": _ACTIVE_CONNECTION == name
        }
    except Exception as e:
        return _format_db_error(e)


# ==========================================
# DBA & DATABASE MANAGEMENT TOOLS
# ==========================================

@mcp.tool()
def create_database(database: str, server: Optional[str] = None, connection: Optional[str] = None, encoding: Optional[str] = None, template: Optional[str] = None) -> Dict[str, Any]:
    """Create a new database on the active (or specified) PostgreSQL or MySQL server instance."""
    try:
        info = _get_connection(_resolve_conn(connection, server))
        if info["engine"] == "postgres":
            admin_conn = _get_pg_client(info, dbname="postgres")
            admin_conn.autocommit = True
            db_esc = database.replace('"', '""')
            try:
                with admin_conn.cursor() as cur:
                    sql = f'CREATE DATABASE "{db_esc}"'
                    if template:
                        tpl_esc = template.replace('"', '""')
                        sql += f' TEMPLATE "{tpl_esc}"'
                    if encoding:
                        sql += f" ENCODING '{encoding}'"
                    cur.execute(sql)
            finally:
                admin_conn.close()

            u = urlparse(info["url"])
            new_url = f"{u.scheme}://{u.netloc}/{database}"
            _RAW_CONFIG[database] = new_url
            return {"success": True, "message": f"Database '{database}' successfully created on PostgreSQL server ({info['host']}:{info['port']}).", "database": database, "engine": "postgres"}
        else:
            conn = _get_mysql_client(info)
            db_esc = database.replace("`", "``")
            try:
                with conn.cursor() as cur:
                    sql = f"CREATE DATABASE IF NOT EXISTS `{db_esc}`"
                    if encoding:
                        sql += f" CHARACTER SET {encoding}"
                    cur.execute(sql)
            finally:
                conn.close()

            u = urlparse(info["url"])
            new_url = f"{u.scheme}://{u.netloc}/{database}"
            _RAW_CONFIG[database] = new_url
            return {"success": True, "message": f"Database '{database}' successfully created on MySQL server ({info['host']}:{info['port']}).", "database": database, "engine": "mysql"}
    except Exception as e:
        engine = info.get("engine", "unknown") if "info" in locals() else "unknown"
        return _format_db_error(e, engine)


@mcp.tool()
def drop_database(database: str, confirmName: str, force: bool = False, server: Optional[str] = None, connection: Optional[str] = None) -> Dict[str, Any]:
    """Safely drop a database. Requires exact 'confirmName' matching the database name. Supports 'force' to kill active connections."""
    global _ACTIVE_CONNECTION
    protected = {"postgres", "template0", "template1", "mysql", "information_schema", "performance_schema", "sys", "cloudsqladmin"}
    if database.lower() in protected:
        return {"error": True, "message": f"Forbidden: Cannot drop protected system database '{database}'."}

    if confirmName != database:
        return {"error": True, "message": f"Safety Confirmation Failed: 'confirmName' ({confirmName}) does not match 'database' ({database}). You must pass confirmName='{database}' to explicitly confirm deletion."}

    try:
        info = _get_connection(_resolve_conn(connection, server))
        if database in _CONNECTION_REGISTRY:
            del _CONNECTION_REGISTRY[database]
        _RAW_CONFIG.pop(database, None)
        if _ACTIVE_CONNECTION == database:
            _ACTIVE_CONNECTION = next(iter(_RAW_CONFIG.keys()), None)
            if _ACTIVE_CONNECTION:
                _save_active_connection(_ACTIVE_CONNECTION)

        if info["engine"] == "postgres":
            admin_conn = _get_pg_client(info, dbname="postgres")
            admin_conn.autocommit = True
            db_esc = database.replace('"', '""')
            try:
                with admin_conn.cursor() as cur:
                    if force:
                        cur.execute("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s AND pid <> pg_backend_pid();", (database,))
                        cur.execute(f'DROP DATABASE IF EXISTS "{db_esc}" WITH (FORCE);')
                    else:
                        cur.execute(f'DROP DATABASE "{db_esc}";')
            finally:
                admin_conn.close()

            return {"success": True, "message": f"Database '{database}' successfully dropped on PostgreSQL server ({info['host']}:{info['port']}).", "activeConnectionNow": _ACTIVE_CONNECTION}
        else:
            conn = _get_mysql_client(info)
            db_esc = database.replace("`", "``")
            try:
                with conn.cursor() as cur:
                    cur.execute(f"DROP DATABASE IF EXISTS `{db_esc}`;")
            finally:
                conn.close()

            return {"success": True, "message": f"Database '{database}' successfully dropped on MySQL server ({info['host']}:{info['port']}).", "activeConnectionNow": _ACTIVE_CONNECTION}
    except Exception as e:
        engine = info.get("engine", "unknown") if "info" in locals() else "unknown"
        return _format_db_error(e, engine)


@mcp.tool()
def clone_database(sourceDatabase: str, targetDatabase: str, server: Optional[str] = None, connection: Optional[str] = None) -> Dict[str, Any]:
    """Instantly clone an entire database (schema, tables, indexes, data). Uses native template cloning in PostgreSQL."""
    try:
        info = _get_connection(_resolve_conn(connection, server))
        if info["engine"] == "postgres":
            admin_conn = _get_pg_client(info, dbname="postgres")
            admin_conn.autocommit = True
            src_esc = sourceDatabase.replace('"', '""')
            tgt_esc = targetDatabase.replace('"', '""')
            try:
                with admin_conn.cursor() as cur:
                    try:
                        cur.execute(f'ALTER DATABASE "{src_esc}" WITH ALLOW_CONNECTIONS = false;')
                    except Exception:
                        pass
                    cur.execute("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s AND pid <> pg_backend_pid();", (sourceDatabase,))
                    cur.execute(f'CREATE DATABASE "{tgt_esc}" WITH TEMPLATE "{src_esc}";')
            finally:
                try:
                    with admin_conn.cursor() as cur:
                        cur.execute(f'ALTER DATABASE "{src_esc}" WITH ALLOW_CONNECTIONS = true;')
                except Exception:
                    pass
                admin_conn.close()

            u = urlparse(info["url"])
            new_url = f"{u.scheme}://{u.netloc}/{targetDatabase}"
            _RAW_CONFIG[targetDatabase] = new_url
            return {"success": True, "message": f"Database '{sourceDatabase}' cloned to '{targetDatabase}' successfully via native template cloning.", "source": sourceDatabase, "target": targetDatabase}
        else:
            conn = _get_mysql_client(info)
            src_esc = sourceDatabase.replace("`", "``")
            tgt_esc = targetDatabase.replace("`", "``")
            try:
                with conn.cursor() as cur:
                    cur.execute(f"CREATE DATABASE IF NOT EXISTS `{tgt_esc}`;")
                    cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = %s;", (sourceDatabase,))
                    tables = [r.get("table_name", next(iter(r.values()))) for r in cur.fetchall()]
                    for t in tables:
                        t_esc = str(t).replace("`", "``")
                        cur.execute(f"CREATE TABLE `{tgt_esc}`.`{t_esc}` LIKE `{src_esc}`.`{t_esc}`;")
                        cur.execute(f"INSERT INTO `{tgt_esc}`.`{t_esc}` SELECT * FROM `{src_esc}`.`{t_esc}`;")
            finally:
                conn.close()

            u = urlparse(info["url"])
            new_url = f"{u.scheme}://{u.netloc}/{targetDatabase}"
            _RAW_CONFIG[targetDatabase] = new_url
            return {"success": True, "message": f"Database '{sourceDatabase}' cloned to '{targetDatabase}' successfully ({len(tables)} tables copied).", "source": sourceDatabase, "target": targetDatabase}
    except Exception as e:
        engine = info.get("engine", "unknown") if "info" in locals() else "unknown"
        return _format_db_error(e, engine)


@mcp.tool()
def terminate_connections(database: str, server: Optional[str] = None, connection: Optional[str] = None) -> Dict[str, Any]:
    """Kill active client connections or hanging locks on a specific database."""
    try:
        info = _get_connection(_resolve_conn(connection, server))
        if info["engine"] == "postgres":
            admin_conn = _get_pg_client(info, dbname="postgres")
            admin_conn.autocommit = True
            try:
                with admin_conn.cursor() as cur:
                    cur.execute("SELECT pid, usename, client_addr, application_name, pg_terminate_backend(pid) as terminated FROM pg_stat_activity WHERE datname = %s AND pid <> pg_backend_pid();", (database,))
                    res = cur.fetchall()
                    return {"database": database, "terminatedCount": len(res), "sessions": res}
            finally:
                admin_conn.close()
        else:
            conn = _get_mysql_client(info)
            try:
                with conn.cursor() as cur:
                    cur.execute("SELECT ID, USER, HOST, DB, COMMAND, TIME, STATE FROM information_schema.processlist WHERE DB = %s;", (database,))
                    processes = cur.fetchall()
                    killed = 0
                    for p in processes:
                        try:
                            cur.execute(f"KILL {p['ID']};")
                            killed += 1
                        except Exception:
                            pass
                    return {"database": database, "terminatedCount": killed, "processes": processes}
            finally:
                conn.close()
    except Exception as e:
        engine = info.get("engine", "unknown") if "info" in locals() else "unknown"
        return _format_db_error(e, engine)


@mcp.tool()
def list_active_queries(database: Optional[str] = None, server: Optional[str] = None, connection: Optional[str] = None) -> Dict[str, Any]:
    """Inspect currently executing queries, lock waits, and execution durations."""
    try:
        info = _get_connection(_resolve_conn(connection, server))
        if info["engine"] == "postgres":
            conn = _get_pg_client(info)
            try:
                with conn.cursor() as cur:
                    sql = "SELECT pid, datname, usename, client_addr, application_name, state, to_char(now() - query_start, 'HH24:MI:SS') AS duration, query, wait_event_type, wait_event FROM pg_stat_activity WHERE state <> 'idle' AND pid <> pg_backend_pid()"
                    params = []
                    if database:
                        sql += " AND datname = %s"
                        params.append(database)
                    sql += " ORDER BY query_start ASC;"
                    if params:
                        cur.execute(sql, tuple(params))
                    else:
                        cur.execute(sql)
                    rows = cur.fetchall()
                    return {"activeQueryCount": len(rows), "queries": rows}
            finally:
                conn.close()
        else:
            conn = _get_mysql_client(info)
            try:
                with conn.cursor() as cur:
                    cur.execute("SELECT ID as pid, USER as usename, HOST as client_addr, DB as datname, COMMAND as state, TIME as duration_seconds, INFO as query FROM information_schema.processlist WHERE COMMAND <> 'Sleep' ORDER BY TIME DESC;")
                    rows = cur.fetchall()
                    return {"activeQueryCount": len(rows), "queries": rows}
            finally:
                conn.close()
    except Exception as e:
        engine = info.get("engine", "unknown") if "info" in locals() else "unknown"
        return _format_db_error(e, engine)


@mcp.tool()
def dump_database(database: Optional[str] = None, outputPath: Optional[str] = None, schemaOnly: bool = False, server: Optional[str] = None, connection: Optional[str] = None) -> Dict[str, Any]:
    """Export an SQL dump snapshot of the database using native pg_dump or mysqldump."""
    try:
        info = _get_connection(_resolve_conn(connection, server))
        target_db = database or info["database"]

        backup_dir = Path.home() / ".gemini" / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)

        ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        out_file = Path(outputPath) if outputPath else backup_dir / f"{target_db}_{'schema_' if schemaOnly else ''}{ts}.sql"

        if info["engine"] == "postgres":
            cmd = [
                "pg_dump",
                "-h", str(info["host"]),
                "-p", str(info["port"]),
                "-U", str(info["user"]),
                "-d", target_db,
                "-f", str(out_file),
            ]
            if schemaOnly:
                cmd.append("--schema-only")

            env = os.environ.copy()
            if info["password"]:
                env["PGPASSWORD"] = str(info["password"])

            res = subprocess.run(cmd, env=env, capture_output=True, text=True)
            if res.returncode != 0:
                raise RuntimeError(f"pg_dump failed: {res.stderr}")

            size_kb = round(out_file.stat().st_size / 1024, 2)
            return {
                "success": True,
                "message": f"PostgreSQL database '{target_db}' successfully dumped to '{out_file}'.",
                "outputPath": str(out_file),
                "sizeKb": size_kb,
                "schemaOnly": schemaOnly
            }
        else:
            cmd = [
                "mysqldump",
                "-h", str(info["host"]),
                "-P", str(info["port"]),
                "-u", str(info["user"]),
                f"-p{info['password']}",
                target_db,
                "-r", str(out_file),
            ]
            if schemaOnly:
                cmd.append("--no-data")

            res = subprocess.run(cmd, capture_output=True, text=True)
            if res.returncode != 0:
                raise RuntimeError(f"mysqldump failed: {res.stderr}")

            size_kb = round(out_file.stat().st_size / 1024, 2)
            return {
                "success": True,
                "message": f"MySQL database '{target_db}' successfully dumped to '{out_file}'.",
                "outputPath": str(out_file),
                "sizeKb": size_kb,
                "schemaOnly": schemaOnly
            }
    except Exception as e:
        engine = info.get("engine", "unknown") if "info" in locals() else "unknown"
        return _format_db_error(e, engine)


@mcp.tool()
def restore_database(database: str, dumpFilePath: str, server: Optional[str] = None, connection: Optional[str] = None) -> Dict[str, Any]:
    """Restore a database from a .sql dump file using native psql or mysql."""
    fpath = Path(dumpFilePath)
    if not fpath.exists():
        return {"error": True, "message": f"Dump file not found: {dumpFilePath}"}

    try:
        info = _get_connection(_resolve_conn(connection, server))
        if info["engine"] == "postgres":
            cmd = [
                "psql",
                "-h", str(info["host"]),
                "-p", str(info["port"]),
                "-U", str(info["user"]),
                "-d", database,
                "-f", str(fpath),
            ]
            env = os.environ.copy()
            if info["password"]:
                env["PGPASSWORD"] = str(info["password"])

            res = subprocess.run(cmd, env=env, capture_output=True, text=True)
            if res.returncode != 0:
                raise RuntimeError(f"psql restore failed: {res.stderr}")

            return {
                "success": True,
                "message": f"PostgreSQL database '{database}' successfully restored from '{dumpFilePath}'."
            }
        else:
            cmd = [
                "mysql",
                "-h", str(info["host"]),
                "-P", str(info["port"]),
                "-u", str(info["user"]),
            ]
            if info.get("password"):
                cmd.append(f"-p{info['password']}")
            cmd.append(database)

            with open(fpath, "r", encoding="utf-8", errors="replace") as dump_in:
                res = subprocess.run(cmd, stdin=dump_in, capture_output=True, text=True)

            if res.returncode != 0:
                raise RuntimeError(f"mysql restore failed: {res.stderr}")

            return {
                "success": True,
                "message": f"MySQL database '{database}' successfully restored from '{dumpFilePath}'.",
                "dumpFilePath": str(fpath)
            }
    except Exception as e:
        engine = info.get("engine", "unknown") if "info" in locals() else "unknown"
        return _format_db_error(e, engine)


# ==========================================================
# 6. ADVANCED DATABASE INDEX & SCHEMA AUDITING TOOLS
# ==========================================================

@mcp.tool()
def analyze_table_indexes(
    tableName: str,
    schema: Optional[str] = None,
    connection: Optional[str] = None,
    server: Optional[str] = None
) -> Dict[str, Any]:
    """
    Perform deep index analysis on a database table.
    Identifies defined indexes, primary keys, unindexed foreign keys
    (unindexed FKs cause full table scans during joins and cascaded deletes),
    and unused indexes.
    
    Args:
        tableName: Name of the table.
        schema: Target schema (Postgres). If None, auto-resolved.
        connection: Connection name to query.
        server: Optional server or connection alias.
    """
    try:
        info = _get_connection(_resolve_conn(connection, server))
        if info["engine"] == "postgres":
            conn = _get_pg_client(info)
            try:
                with conn.cursor() as cur:
                    resolved = _resolve_pg_table(cur, tableName, schema)
                    s = resolved["schema"]
                    t = resolved["table"]

                    # 1. Fetch Foreign Keys
                    cur.execute("""
                    SELECT kcu.column_name, tc.constraint_name, ccu.table_name AS referenced_table, ccu.column_name AS referenced_column
                    FROM information_schema.table_constraints tc
                    JOIN information_schema.key_column_usage kcu ON tc.constraint_name = kcu.constraint_name AND tc.table_schema = kcu.table_schema
                    JOIN information_schema.constraint_column_usage ccu ON ccu.constraint_name = tc.constraint_name AND ccu.table_schema = tc.table_schema
                    WHERE tc.constraint_type = 'FOREIGN KEY' AND tc.table_schema = %s AND tc.table_name = %s
                    """, (s, t))
                    fks = cur.fetchall()

                    # 2. Fetch Indexes with sizes and scan counts
                    cur.execute("""
                    SELECT
                        i.relname AS index_name,
                        pg_get_indexdef(i.oid) AS definition,
                        ix.indisprimary AS is_primary,
                        ix.indisunique AS is_unique,
                        pg_size_pretty(pg_relation_size(i.oid)) AS index_size,
                        COALESCE(s.idx_scan, 0) AS index_scans
                    FROM pg_class t
                    JOIN pg_index ix ON t.oid = ix.indrelid
                    JOIN pg_class i ON i.oid = ix.indexrelid
                    JOIN pg_namespace n ON n.oid = t.relnamespace
                    LEFT JOIN pg_stat_user_indexes s ON s.indexrelid = i.oid
                    WHERE n.nspname = %s AND t.relname = %s
                    ORDER BY i.relname
                    """, (s, t))
                    indexes = cur.fetchall()

                    # Extract indexed leading columns
                    indexed_cols = set()
                    for idx in indexes:
                        defn = idx["definition"]
                        m = re.search(r"\((.+?)\)", defn)
                        if m:
                            cols_in_idx = [c.strip().strip('"') for c in m.group(1).split(",")]
                            if cols_in_idx:
                                indexed_cols.add(cols_in_idx[0])

                    missing_fk_indexes = []
                    for fk in fks:
                        col = fk["column_name"]
                        if col not in indexed_cols:
                            missing_fk_indexes.append({
                                "column": col,
                                "constraint": fk["constraint_name"],
                                "referenced_table": fk["referenced_table"],
                                "recommended_sql": f'CREATE INDEX idx_{t}_{col} ON "{s}"."{t}" ("{col}");'
                            })

                    unused_indexes = [
                        idx["index_name"] for idx in indexes
                        if not idx["is_primary"] and idx["index_scans"] == 0
                    ]

                    return {
                        "connection": info["name"],
                        "database": info["database"],
                        "schema": s,
                        "table": t,
                        "total_indexes": len(indexes),
                        "indexes": indexes,
                        "missing_fk_indexes": missing_fk_indexes,
                        "unused_indexes": unused_indexes,
                        "status": "warning" if missing_fk_indexes else "healthy"
                    }
            finally:
                conn.close()
        else:
            conn = _get_mysql_client(info)
            try:
                with conn.cursor() as cur:
                    cur.execute(f"SHOW INDEX FROM `{tableName}`;")
                    raw_indexes = cur.fetchall()

                    cur.execute("""
                    SELECT COLUMN_NAME, CONSTRAINT_NAME, REFERENCED_TABLE_NAME, REFERENCED_COLUMN_NAME
                    FROM information_schema.KEY_COLUMN_USAGE
                    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s AND REFERENCED_TABLE_NAME IS NOT NULL
                    """, (tableName,))
                    fks = cur.fetchall()

                    indexed_leading_cols = {
                        idx["Column_name"] for idx in raw_indexes
                        if idx.get("Seq_in_index") == 1 and "Column_name" in idx
                    }

                    missing_fk = []
                    for fk in fks:
                        col = fk.get("COLUMN_NAME") or fk.get("column_name")
                        if col and col not in indexed_leading_cols:
                            missing_fk.append({
                                "column": col,
                                "constraint": fk.get("CONSTRAINT_NAME") or fk.get("constraint_name"),
                                "referenced_table": fk.get("REFERENCED_TABLE_NAME") or fk.get("referenced_table_name"),
                                "recommended_sql": f"CREATE INDEX `idx_{tableName}_{col}` ON `{tableName}` (`{col}`);"
                            })

                    return {
                        "connection": info["name"],
                        "database": info["database"],
                        "table": tableName,
                        "total_indexes": len(raw_indexes),
                        "indexes": raw_indexes,
                        "missing_fk_indexes": missing_fk,
                        "status": "warning" if missing_fk else "healthy"
                    }
            finally:
                conn.close()
    except Exception as e:
        engine = info.get("engine", "unknown") if "info" in locals() else "unknown"
        return _format_db_error(e, engine)


@mcp.tool()
def compare_schemas(
    source_connection: Optional[str] = None,
    target_connection: Optional[str] = None,
    schema: Optional[str] = "public",
    source_server: Optional[str] = None,
    target_server: Optional[str] = None
) -> Dict[str, Any]:
    """
    Compare table structures, missing tables, missing columns, and data type discrepancies between two database connections.
    Ideal for detecting environment drift (e.g. dev vs staging vs prod).
    
    Args:
        source_connection: Baseline source connection or server name.
        target_connection: Target connection or server name to compare against.
        schema: Target schema name (PostgreSQL, default: 'public').
        source_server: Optional alias for source_connection.
        target_server: Optional alias for target_connection.
    """
    src_name = _resolve_conn(source_connection, source_server)
    tgt_name = _resolve_conn(target_connection, target_server)
    if not src_name or not tgt_name:
        return {
            "error": True,
            "message": "Both source_connection (or source_server) and target_connection (or target_server) must be specified."
        }

    try:
        def _fetch_table_cols(conn_name: str) -> Dict[str, Dict[str, str]]:
            inf = _get_connection(conn_name)
            tbl_map: Dict[str, Dict[str, str]] = {}
            if inf["engine"] == "postgres":
                cn = _get_pg_client(inf)
                try:
                    with cn.cursor() as cur:
                        cur.execute("""
                        SELECT table_name, column_name, data_type, is_nullable
                        FROM information_schema.columns
                        WHERE table_schema = %s
                        ORDER BY table_name, ordinal_position
                        """, (schema or "public",))
                        for r in cur.fetchall():
                            tbl = r["table_name"]
                            tbl_map.setdefault(tbl, {})[r["column_name"]] = f"{r['data_type']} ({'NULL' if r['is_nullable'] == 'YES' else 'NOT NULL'})"
                finally:
                    cn.close()
            else:
                cn = _get_mysql_client(inf)
                try:
                    with cn.cursor() as cur:
                        cur.execute("""
                        SELECT table_name, column_name, column_type, is_nullable
                        FROM information_schema.columns
                        WHERE table_schema = DATABASE()
                        ORDER BY table_name, ordinal_position
                        """)
                        for r in cur.fetchall():
                            t_name = r.get("TABLE_NAME") or r.get("table_name")
                            c_name = r.get("COLUMN_NAME") or r.get("column_name")
                            c_type = r.get("COLUMN_TYPE") or r.get("column_type")
                            null_s = r.get("IS_NULLABLE") or r.get("is_nullable")
                            tbl_map.setdefault(t_name, {})[c_name] = f"{c_type} ({'NULL' if null_s == 'YES' else 'NOT NULL'})"
                finally:
                    cn.close()
            return tbl_map

        source_tables = _fetch_table_cols(src_name)
        target_tables = _fetch_table_cols(tgt_name)

        s_set = set(source_tables.keys())
        t_set = set(target_tables.keys())

        missing_in_target = sorted(list(s_set - t_set))
        extra_in_target = sorted(list(t_set - s_set))
        common_tables = sorted(list(s_set & t_set))

        discrepancies = []
        for tbl in common_tables:
            s_cols = source_tables[tbl]
            t_cols = target_tables[tbl]

            s_col_set = set(s_cols.keys())
            t_col_set = set(t_cols.keys())

            missing_cols = sorted(list(s_col_set - t_col_set))
            extra_cols = sorted(list(t_col_set - s_col_set))
            type_mismatches = []

            for c in (s_col_set & t_col_set):
                if s_cols[c] != t_cols[c]:
                    type_mismatches.append({
                        "column": c,
                        "source_type": s_cols[c],
                        "target_type": t_cols[c]
                    })

            if missing_cols or extra_cols or type_mismatches:
                discrepancies.append({
                    "table": tbl,
                    "missing_columns_in_target": missing_cols,
                    "extra_columns_in_target": extra_cols,
                    "type_mismatches": type_mismatches
                })

        # Generate migration SQL to bring target up to source
        migration_sql: List[str] = []
        sch = schema or "public"

        for tbl in missing_in_target:
            migration_sql.append(f"-- Table '{tbl}' exists in source but not in target")
            cols_ddl = ", ".join(
                f"{col} {typ.split(' (')[0]}"
                for col, typ in source_tables[tbl].items()
            )
            migration_sql.append(f"CREATE TABLE {sch}.{tbl} ({cols_ddl});")

        for disc in discrepancies:
            tbl = disc["table"]
            for col in disc["missing_columns_in_target"]:
                raw_type = source_tables[tbl][col].split(" (")[0]
                nullable = "NOT NULL" if "NOT NULL" in source_tables[tbl][col] else ""
                migration_sql.append(
                    f"ALTER TABLE {sch}.{tbl} ADD COLUMN {col} {raw_type} {nullable}".strip() + ";"
                )
            for mm in disc["type_mismatches"]:
                src_type = mm["source_type"].split(" (")[0]
                migration_sql.append(
                    f"-- Type mismatch on {tbl}.{mm['column']}: "
                    f"source={src_type}, target={mm['target_type'].split(' (')[0]}"
                )
                migration_sql.append(
                    f"ALTER TABLE {sch}.{tbl} ALTER COLUMN {mm['column']} TYPE {src_type};"
                )

        return {
            "source_connection": src_name,
            "target_connection": tgt_name,
            "identical": not (missing_in_target or extra_in_target or discrepancies),
            "tables_only_in_source": missing_in_target,
            "tables_only_in_target": extra_in_target,
            "common_tables_count": len(common_tables),
            "discrepancies_count": len(discrepancies),
            "table_discrepancies": discrepancies,
            "migration_sql": migration_sql,
            "migration_sql_hint": (
                "Apply migration_sql statements to bring the target schema up to source."
                if migration_sql else "Schemas are identical — no migration needed."
            )
        }
    except Exception as e:
        return _format_db_error(e)


@mcp.tool()
def audit_database_health(
    schema: Optional[str] = "public",
    connection: Optional[str] = None,
    server: Optional[str] = None
) -> Dict[str, Any]:
    """
    Comprehensive database-wide health audit for PostgreSQL.
    Returns three categories of actionable findings:
      1. unindexed_foreign_keys  — FK columns with no supporting index (causes slow JOINs).
      2. unused_indexes          — Indexes with zero scans since last stats reset (candidates for DROP).
      3. bloated_tables          — Tables with >20% dead tuples that need VACUUM.

    Args:
        schema:     Schema to audit (default: 'public'). Use '*' for all schemas.
        connection: Named connection or server alias to use; defaults to active connection.
        server:     Optional server or connection alias.
    """
    try:
        info = _get_connection(_resolve_conn(connection, server))
        if info["engine"] != "postgres":
            return {"error": "audit_database_health requires PostgreSQL. MySQL is not supported."}

        conn = _get_pg_client(info)
        try:
            with conn.cursor() as cur:
                sch_filter = "" if schema == "*" else f"AND kcu.table_schema = '{schema}'"
                sch_filter_idx = "" if schema == "*" else f"AND schemaname = '{schema}'"

                # ── 1. Unindexed Foreign Keys ─────────────────────────────────────────
                cur.execute(f"""
                    SELECT
                        kcu.table_schema,
                        kcu.table_name,
                        kcu.column_name,
                        ccu.table_name  AS references_table,
                        ccu.column_name AS references_column
                    FROM information_schema.key_column_usage kcu
                    JOIN information_schema.referential_constraints rc
                        ON kcu.constraint_name = rc.constraint_name
                        AND kcu.constraint_schema = rc.constraint_schema
                    JOIN information_schema.constraint_column_usage ccu
                        ON rc.unique_constraint_name = ccu.constraint_name
                    WHERE NOT EXISTS (
                        SELECT 1 FROM pg_index pi
                        JOIN pg_class pc ON pc.oid = pi.indrelid
                        JOIN pg_attribute pa ON pa.attrelid = pc.oid AND pa.attnum = ANY(pi.indkey)
                        JOIN pg_namespace pn ON pn.oid = pc.relnamespace
                        WHERE pc.relname = kcu.table_name
                          AND pn.nspname  = kcu.table_schema
                          AND pa.attname  = kcu.column_name
                    )
                    {sch_filter}
                    ORDER BY kcu.table_schema, kcu.table_name, kcu.column_name
                """)
                unindexed_fks = [
                    {
                        "schema": r["table_schema"],
                        "table": r["table_name"],
                        "column": r["column_name"],
                        "references": f"{r['references_table']}.{r['references_column']}",
                        "fix": f"CREATE INDEX ON {r['table_schema']}.{r['table_name']}({r['column_name']});"
                    }
                    for r in cur.fetchall()
                ]

                # ── 2. Unused Indexes ────────────────────────────────────────────────
                cur.execute(f"""
                    SELECT
                        schemaname,
                        relname      AS table_name,
                        indexrelname AS index_name,
                        idx_scan,
                        pg_size_pretty(pg_relation_size(indexrelid)) AS index_size
                    FROM pg_stat_user_indexes
                    WHERE idx_scan = 0
                      AND indexrelname NOT LIKE '%_pkey'
                    {sch_filter_idx}
                    ORDER BY pg_relation_size(indexrelid) DESC
                """)
                unused_indexes = [
                    {
                        "schema": r["schemaname"],
                        "table": r["table_name"],
                        "index": r["index_name"],
                        "scans": r["idx_scan"],
                        "size": r["index_size"],
                        "fix": f"DROP INDEX CONCURRENTLY {r['schemaname']}.{r['index_name']};"
                    }
                    for r in cur.fetchall()
                ]

                # ── 3. Bloated Tables ────────────────────────────────────────────────
                cur.execute(f"""
                    SELECT
                        schemaname,
                        relname                                          AS table_name,
                        n_live_tup,
                        n_dead_tup,
                        CASE WHEN n_live_tup + n_dead_tup = 0 THEN 0
                             ELSE ROUND(100.0 * n_dead_tup / (n_live_tup + n_dead_tup), 1)
                        END                                              AS dead_pct,
                        pg_size_pretty(pg_total_relation_size(relid))    AS table_size,
                        last_autovacuum,
                        last_vacuum
                    FROM pg_stat_user_tables
                    WHERE n_dead_tup > 0
                      AND (n_live_tup + n_dead_tup) > 0
                      AND (100.0 * n_dead_tup / (n_live_tup + n_dead_tup)) > 20
                    {sch_filter_idx}
                    ORDER BY dead_pct DESC
                """)
                bloated_tables = [
                    {
                        "schema": r["schemaname"],
                        "table": r["table_name"],
                        "live_rows": r["n_live_tup"],
                        "dead_rows": r["n_dead_tup"],
                        "dead_pct": float(r["dead_pct"]),
                        "size": r["table_size"],
                        "last_autovacuum": str(r["last_autovacuum"]) if r["last_autovacuum"] else None,
                        "last_vacuum": str(r["last_vacuum"]) if r["last_vacuum"] else None,
                        "fix": f"VACUUM ANALYZE {r['schemaname']}.{r['table_name']};"
                    }
                    for r in cur.fetchall()
                ]

                overall = "healthy"
                if unindexed_fks or unused_indexes or bloated_tables:
                    overall = "warnings_found"

                return {
                    "connection": info["name"],
                    "database": info["database"],
                    "schema_filter": schema,
                    "overall_status": overall,
                    "summary": {
                        "unindexed_foreign_keys": len(unindexed_fks),
                        "unused_indexes": len(unused_indexes),
                        "bloated_tables": len(bloated_tables)
                    },
                    "unindexed_foreign_keys": unindexed_fks,
                    "unused_indexes": unused_indexes,
                    "bloated_tables": bloated_tables,
                    "hint": (
                        "Each finding includes a 'fix' field with the recommended SQL statement."
                        if overall == "warnings_found" else
                        "No health issues detected in the audited schema."
                    )
                }
        finally:
            conn.close()
    except Exception as e:
        engine = info.get("engine", "unknown") if "info" in locals() else "unknown"
        return _format_db_error(e, engine)



def _clean_mermaid_type(data_type: str) -> str:
    dt = (data_type or "").lower().strip()
    if "char" in dt or "text" in dt:
        return "string"
    if "int" in dt or "serial" in dt:
        return "int"
    if any(k in dt for k in ("numeric", "decimal", "real", "double", "float")):
        return "float"
    if "bool" in dt:
        return "boolean"
    if any(k in dt for k in ("date", "time", "timestamp")):
        return "datetime"
    if "uuid" in dt:
        return "uuid"
    if "json" in dt:
        return "json"
    clean = re.sub(r'[^a-zA-Z0-9_]', '_', dt)
    return clean or "string"


def _serialize_db_val(v: Any) -> Any:
    if v is None:
        return None
    if isinstance(v, (datetime, date, time)):
        return v.isoformat()
    if isinstance(v, decimal.Decimal):
        return float(v)
    if isinstance(v, uuid.UUID):
        return str(v)
    if isinstance(v, bytes):
        return v.hex()
    return v


@mcp.tool()
def generate_erd(
    schema: Optional[str] = None,
    tables: Optional[List[str]] = None,
    include_columns: bool = True,
    connection: Optional[str] = None,
    server: Optional[str] = None
) -> Dict[str, Any]:
    """
    Generate an Entity-Relationship Diagram (ERD) in GitHub/Mermaid markdown syntax.
    Extracts all tables, columns, primary keys, and foreign key relationships directly
    from database catalog metadata.
    
    Args:
        schema: Target schema (PostgreSQL) or database (MySQL). If None, uses active/public schema.
        tables: Optional list of table names to filter ERD scope (e.g. ['materials', 'props_inventory']).
        include_columns: If True, includes column definitions with PK/FK annotations inside table blocks.
        connection: Optional connection name or URL (defaults to active connection).
        server: Optional server or connection alias.
    """
    try:
        info = _get_connection(_resolve_conn(connection, server))
    except Exception as e:
        return _format_db_error(e, "unknown")

    try:
        if info["engine"] == "postgres":
            conn = _get_pg_client(info)
            try:
                with conn.cursor() as cur:
                    target_schema = schema.strip() if schema else "public"
                    cur.execute("""
                        SELECT 
                            tc.table_schema, 
                            tc.table_name, 
                            kcu.column_name, 
                            ccu.table_schema AS foreign_table_schema,
                            ccu.table_name AS foreign_table_name,
                            ccu.column_name AS foreign_column_name,
                            tc.constraint_name
                        FROM information_schema.table_constraints tc
                        JOIN information_schema.key_column_usage kcu
                          ON tc.constraint_name = kcu.constraint_name AND tc.table_schema = kcu.table_schema
                        JOIN information_schema.constraint_column_usage ccu
                          ON ccu.constraint_name = tc.constraint_name AND ccu.table_schema = tc.table_schema
                        WHERE tc.constraint_type = 'FOREIGN KEY' AND tc.table_schema = %s
                    """, (target_schema,))
                    fks = cur.fetchall()

                    cur.execute("""
                        SELECT c.table_schema, c.table_name, c.column_name, c.data_type,
                               CASE WHEN pk.column_name IS NOT NULL THEN TRUE ELSE FALSE END as is_pk
                        FROM information_schema.columns c
                        LEFT JOIN (
                            SELECT tc.table_schema, tc.table_name, kcu.column_name
                            FROM information_schema.table_constraints tc
                            JOIN information_schema.key_column_usage kcu ON tc.constraint_name = kcu.constraint_name AND tc.table_schema = kcu.table_schema
                            WHERE tc.constraint_type = 'PRIMARY KEY' AND tc.table_schema = %s
                        ) pk ON pk.table_schema = c.table_schema AND pk.table_name = c.table_name AND pk.column_name = c.column_name
                        WHERE c.table_schema = %s
                        ORDER BY c.table_name, c.ordinal_position;
                    """, (target_schema, target_schema))
                    all_cols = cur.fetchall()
            finally:
                conn.close()
        else:
            conn = _get_mysql_client(info)
            try:
                with conn.cursor() as cur:
                    target_schema = schema.strip() if schema else info["database"]
                    cur.execute("""
                        SELECT 
                            TABLE_SCHEMA as table_schema,
                            TABLE_NAME as table_name,
                            COLUMN_NAME as column_name,
                            REFERENCED_TABLE_SCHEMA as foreign_table_schema,
                            REFERENCED_TABLE_NAME as foreign_table_name,
                            REFERENCED_COLUMN_NAME as foreign_column_name,
                            CONSTRAINT_NAME as constraint_name
                        FROM information_schema.KEY_COLUMN_USAGE
                        WHERE REFERENCED_TABLE_NAME IS NOT NULL AND TABLE_SCHEMA = %s
                    """, (target_schema,))
                    fks = cur.fetchall()

                    cur.execute("""
                        SELECT c.TABLE_SCHEMA as table_schema, c.TABLE_NAME as table_name, c.COLUMN_NAME as column_name, c.DATA_TYPE as data_type,
                               CASE WHEN c.COLUMN_KEY = 'PRI' THEN 1 ELSE 0 END as is_pk
                        FROM information_schema.COLUMNS c
                        WHERE c.TABLE_SCHEMA = %s
                        ORDER BY c.TABLE_NAME, c.ORDINAL_POSITION
                    """, (target_schema,))
                    all_cols = cur.fetchall()
            finally:
                conn.close()

        table_filter_set = set(t.lower() for t in tables) if tables else None

        filtered_fks = []
        for fk in fks:
            p = fk["foreign_table_name"]
            c = fk["table_name"]
            if table_filter_set and (p.lower() not in table_filter_set and c.lower() not in table_filter_set):
                continue
            filtered_fks.append(fk)

        table_cols_map = {}
        for col in all_cols:
            t = col["table_name"]
            if table_filter_set and t.lower() not in table_filter_set:
                continue
            table_cols_map.setdefault(t, []).append(col)

        mermaid_lines = ["erDiagram"]
        seen_rels = set()
        for fk in filtered_fks:
            p = fk["foreign_table_name"]
            c = fk["table_name"]
            col = fk["column_name"]
            rel_key = (p, c, col)
            if rel_key not in seen_rels:
                seen_rels.add(rel_key)
                mermaid_lines.append(f'    {p} ||--o{{ {c} : "{col}"')

        fk_cols_per_table = set((fk["table_name"], fk["column_name"]) for fk in fks)

        if include_columns:
            for t_name, c_list in table_cols_map.items():
                mermaid_lines.append(f"    {t_name} {{")
                for col in c_list:
                    c_type = _clean_mermaid_type(col["data_type"])
                    c_name = col["column_name"]
                    markers = []
                    if col.get("is_pk"):
                        markers.append("PK")
                    if (t_name, c_name) in fk_cols_per_table:
                        markers.append("FK")
                    marker_str = f" {' '.join(markers)}" if markers else ""
                    mermaid_lines.append(f"        {c_type} {c_name}{marker_str}")
                mermaid_lines.append("    }")

        mermaid_str = "\n".join(mermaid_lines)
        return {
            "connection": info["name"],
            "engine": info["engine"],
            "schema": target_schema,
            "tables_count": len(table_cols_map),
            "foreign_keys_count": len(filtered_fks),
            "mermaid": mermaid_str,
            "markdown": f"```mermaid\n{mermaid_str}\n```"
        }
    except Exception as e:
        return _format_db_error(e, info.get("engine", "unknown"))


@mcp.tool()
def diff_data(
    table1: str,
    table2: Optional[str] = None,
    key_columns: Optional[List[str]] = None,
    schema1: Optional[str] = None,
    schema2: Optional[str] = None,
    connection1: Optional[str] = None,
    connection2: Optional[str] = None,
    max_differences: int = 100
) -> Dict[str, Any]:
    """
    Compare row data between two tables (or across schemas/connections).
    Identifies rows only in source, rows only in target, and rows with modified values
    with column-by-column diffs.
    
    Args:
        table1: Source table name (e.g. 'materials').
        table2: Target table name. If omitted, defaults to table1 (useful for comparing across schemas/connections).
        key_columns: Primary key or unique identifier columns for matching rows. Auto-detected if omitted.
        schema1: Schema for table1 (Postgres).
        schema2: Schema for table2 (defaults to schema1 if omitted).
        connection1: Source connection name/alias.
        connection2: Target connection name/alias (defaults to connection1).
        max_differences: Maximum number of differing rows to return in details (default: 100).
    """
    try:
        info1 = _get_connection(_resolve_conn(connection1, None))
        info2 = _get_connection(_resolve_conn(connection2 or connection1, None))
    except Exception as e:
        return _format_db_error(e, "unknown")

    t1_name = table1.strip()
    t2_name = (table2 or table1).strip()
    s1_name = schema1.strip() if schema1 else None
    s2_name = (schema2 or schema1).strip() if (schema2 or schema1) else None

    # Fetch data from source table
    rows1 = []
    pks1 = []
    try:
        if info1["engine"] == "postgres":
            conn1 = _get_pg_client(info1)
            try:
                with conn1.cursor() as cur1:
                    res1 = _resolve_pg_table(cur1, t1_name, s1_name)
                    s1 = res1["schema"]
                    t1 = res1["table"]
                    if not key_columns:
                        cur1.execute("""
                            SELECT kcu.column_name
                            FROM information_schema.table_constraints tc
                            JOIN information_schema.key_column_usage kcu ON tc.constraint_name = kcu.constraint_name AND tc.table_schema = kcu.table_schema
                            WHERE tc.constraint_type = 'PRIMARY KEY' AND tc.table_schema = %s AND tc.table_name = %s
                        """, (s1, t1))
                        pks1 = [r["column_name"] for r in cur1.fetchall()]
                    cur1.execute(f'SELECT * FROM "{s1}"."{t1}" LIMIT 50000;')
                    rows1 = cur1.fetchall()
            finally:
                conn1.close()
        else:
            conn1 = _get_mysql_client(info1)
            try:
                with conn1.cursor() as cur1:
                    s1 = s1_name or info1["database"]
                    t1 = t1_name
                    if not key_columns:
                        cur1.execute("SHOW KEYS FROM `{}` WHERE Key_name = 'PRIMARY'".format(t1))
                        pks1 = [r["Column_name"] for r in cur1.fetchall()]
                    cur1.execute(f"SELECT * FROM `{t1}` LIMIT 50000;")
                    rows1 = cur1.fetchall()
            finally:
                conn1.close()
    except Exception as e:
        return _format_db_error(e, info1.get("engine", "unknown"), f"Querying {table1}")

    # Fetch data from target table
    rows2 = []
    try:
        if info2["engine"] == "postgres":
            conn2 = _get_pg_client(info2)
            try:
                with conn2.cursor() as cur2:
                    res2 = _resolve_pg_table(cur2, t2_name, s2_name)
                    s2 = res2["schema"]
                    t2 = res2["table"]
                    cur2.execute(f'SELECT * FROM "{s2}"."{t2}" LIMIT 50000;')
                    rows2 = cur2.fetchall()
            finally:
                conn2.close()
        else:
            conn2 = _get_mysql_client(info2)
            try:
                with conn2.cursor() as cur2:
                    s2 = s2_name or info2["database"]
                    t2 = t2_name
                    cur2.execute(f"SELECT * FROM `{t2}` LIMIT 50000;")
                    rows2 = cur2.fetchall()
            finally:
                conn2.close()
    except Exception as e:
        return _format_db_error(e, info2.get("engine", "unknown"), f"Querying {table2}")

    resolved_keys = key_columns or pks1
    if not resolved_keys:
        return {
            "error": True,
            "message": f"Table '{table1}' has no primary key. Please specify 'key_columns' explicitly for comparison."
        }

    # Index by key
    map1 = {tuple(str(_serialize_db_val(r.get(k))) for k in resolved_keys): r for r in rows1}
    map2 = {tuple(str(_serialize_db_val(r.get(k))) for k in resolved_keys): r for r in rows2}

    keys1 = set(map1.keys())
    keys2 = set(map2.keys())

    missing_in_target_keys = keys1 - keys2
    missing_in_source_keys = keys2 - keys1
    common_keys = keys1 & keys2

    missing_in_target = [{k: _serialize_db_val(v) for k, v in map1[k].items()} for k in list(missing_in_target_keys)[:max_differences]]
    missing_in_source = [{k: _serialize_db_val(v) for k, v in map2[k].items()} for k in list(missing_in_source_keys)[:max_differences]]

    modified_rows = []
    identical_count = 0

    for k in common_keys:
        r1 = map1[k]
        r2 = map2[k]
        diffs = {}
        all_cols = set(list(r1.keys()) + list(r2.keys()))
        for col in all_cols:
            v1 = _serialize_db_val(r1.get(col))
            v2 = _serialize_db_val(r2.get(col))
            if v1 != v2:
                diffs[col] = {"source": v1, "target": v2}
        if diffs:
            if len(modified_rows) < max_differences:
                modified_rows.append({"key": list(k), "differences": diffs})
        else:
            identical_count += 1

    return {
        "source": f"{info1['name']}:{s1}.{t1}",
        "target": f"{info2['name']}:{s2}.{t2}",
        "key_columns": resolved_keys,
        "total_source_rows": len(rows1),
        "total_target_rows": len(rows2),
        "identical_rows_count": identical_count,
        "modified_rows_count": len(common_keys) - identical_count,
        "missing_in_target_count": len(missing_in_target_keys),
        "missing_in_source_count": len(missing_in_source_keys),
        "modified_rows_sample": modified_rows,
        "missing_in_target_sample": missing_in_target,
        "missing_in_source_sample": missing_in_source
    }


@mcp.tool()
def list_slow_queries(
    limit: int = 20,
    min_duration_ms: float = 100.0,
    connection: Optional[str] = None,
    server: Optional[str] = None
) -> Dict[str, Any]:
    """
    Inspect slow database queries using pg_stat_statements / pg_stat_activity (PostgreSQL)
    or performance_schema / processlist (MySQL).
    
    Args:
        limit: Maximum number of slow queries to return (default: 20).
        min_duration_ms: Minimum execution time threshold in milliseconds (default: 100.0).
        connection: Optional connection name or URL.
        server: Optional server or connection alias.
    """
    try:
        info = _get_connection(_resolve_conn(connection, server))
    except Exception as e:
        return _format_db_error(e, "unknown")

    try:
        if info["engine"] == "postgres":
            conn = _get_pg_client(info)
            try:
                with conn.cursor() as cur:
                    has_pg_stat = False
                    try:
                        cur.execute("SELECT 1 FROM pg_extension WHERE extname = 'pg_stat_statements';")
                        has_pg_stat = bool(cur.fetchone())
                    except Exception:
                        pass

                    if has_pg_stat:
                        cur.execute("""
                            SELECT 
                                query, 
                                calls, 
                                round(total_exec_time::numeric, 2) AS total_time_ms,
                                round(mean_exec_time::numeric, 2) AS mean_time_ms,
                                round(max_exec_time::numeric, 2) AS max_time_ms,
                                rows AS total_rows
                            FROM pg_stat_statements
                            WHERE mean_exec_time >= %s
                            ORDER BY total_exec_time DESC
                            LIMIT %s;
                        """, (min_duration_ms, limit))
                        queries = cur.fetchall()
                        return {
                            "connection": info["name"],
                            "engine": "postgres",
                            "source": "pg_stat_statements",
                            "queries_count": len(queries),
                            "slow_queries": [
                                {
                                    "query": q["query"],
                                    "calls": q["calls"],
                                    "total_time_ms": float(q["total_time_ms"]),
                                    "mean_time_ms": float(q["mean_time_ms"]),
                                    "max_time_ms": float(q["max_time_ms"]),
                                    "rows": q["total_rows"]
                                }
                                for q in queries
                            ]
                        }
                    else:
                        cur.execute("""
                            SELECT 
                                pid, 
                                usename, 
                                application_name, 
                                client_addr, 
                                state, 
                                round(extract(epoch from (now() - query_start)) * 1000) AS duration_ms, 
                                query
                            FROM pg_stat_activity
                            WHERE state != 'idle' 
                              AND pid != pg_backend_pid()
                              AND query NOT ILIKE '%%pg_stat_activity%%'
                            ORDER BY query_start ASC
                            LIMIT %s;
                        """, (limit,))
                        queries = cur.fetchall()
                        return {
                            "connection": info["name"],
                            "engine": "postgres",
                            "source": "pg_stat_activity (active long-running)",
                            "pg_stat_statements_installed": False,
                            "hint": "Install pg_stat_statements extension (CREATE EXTENSION IF NOT EXISTS pg_stat_statements) for historical aggregated query statistics.",
                            "queries_count": len(queries),
                            "active_queries": [
                                {
                                    "pid": q["pid"],
                                    "user": q["usename"],
                                    "application": q["application_name"],
                                    "duration_ms": float(q["duration_ms"]) if q["duration_ms"] else 0,
                                    "state": q["state"],
                                    "query": q["query"]
                                }
                                for q in queries
                            ]
                        }
            finally:
                conn.close()
        else:
            conn = _get_mysql_client(info)
            try:
                with conn.cursor() as cur:
                    try:
                        cur.execute("""
                            SELECT 
                                DIGEST_TEXT AS query, 
                                COUNT_STAR AS calls, 
                                ROUND(SUM_TIMER_WAIT / 1000000000, 2) AS total_time_ms,
                                ROUND(AVG_TIMER_WAIT / 1000000000, 2) AS mean_time_ms,
                                ROUND(MAX_TIMER_WAIT / 1000000000, 2) AS max_time_ms,
                                SUM_ROWS_EXAMINED AS total_rows
                            FROM performance_schema.events_statements_summary_by_digest
                            WHERE (AVG_TIMER_WAIT / 1000000000) >= %s
                            ORDER BY SUM_TIMER_WAIT DESC
                            LIMIT %s;
                        """, (min_duration_ms, limit))
                        queries = cur.fetchall()
                        return {
                            "connection": info["name"],
                            "engine": "mysql",
                            "source": "performance_schema",
                            "queries_count": len(queries),
                            "slow_queries": queries
                        }
                    except Exception:
                        cur.execute("SHOW FULL PROCESSLIST;")
                        procs = cur.fetchall()
                        return {
                            "connection": info["name"],
                            "engine": "mysql",
                            "source": "processlist",
                            "queries_count": len(procs),
                            "active_queries": procs
                        }
            finally:
                conn.close()
    except Exception as e:
        return _format_db_error(e, info.get("engine", "unknown"))


@mcp.tool()
def get_locks(
    connection: Optional[str] = None,
    server: Optional[str] = None
) -> Dict[str, Any]:
    """
    Inspect active database locks and query blocking dependency trees.
    Reveals hanging transactions, blocking PIDs, locked tables, and lock wait times.
    
    Args:
        connection: Optional connection name or URL.
        server: Optional server or connection alias.
    """
    try:
        info = _get_connection(_resolve_conn(connection, server))
    except Exception as e:
        return _format_db_error(e, "unknown")

    try:
        if info["engine"] == "postgres":
            conn = _get_pg_client(info)
            try:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT
                            blocked_locks.pid     AS blocked_pid,
                            blocked_activity.usename  AS blocked_user,
                            blocking_locks.pid    AS blocking_pid,
                            blocking_activity.usename AS blocking_user,
                            blocked_activity.query    AS blocked_statement,
                            blocking_activity.query   AS blocking_statement,
                            round(extract(epoch from (now() - blocked_activity.query_start)) * 1000) AS blocked_duration_ms
                        FROM pg_catalog.pg_locks blocked_locks
                        JOIN pg_catalog.pg_stat_activity blocked_activity ON blocked_activity.pid = blocked_locks.pid
                        JOIN pg_catalog.pg_locks blocking_locks 
                            ON blocking_locks.locktype = blocked_locks.locktype
                            AND blocking_locks.database IS NOT DISTINCT FROM blocked_locks.database
                            AND blocking_locks.relation IS NOT DISTINCT FROM blocked_locks.relation
                            AND blocking_locks.pid != blocked_locks.pid
                        JOIN pg_catalog.pg_stat_activity blocking_activity ON blocking_activity.pid = blocking_locks.pid
                        WHERE NOT blocked_locks.granted;
                    """)
                    blockings = cur.fetchall()

                    cur.execute("""
                        SELECT mode, locktype, count(*) as count
                        FROM pg_locks
                        GROUP BY mode, locktype
                        ORDER BY count DESC;
                    """)
                    lock_counts = cur.fetchall()

                    return {
                        "connection": info["name"],
                        "engine": "postgres",
                        "status": "blocking_detected" if blockings else "healthy",
                        "blocking_trees_count": len(blockings),
                        "blocking_trees": [
                            {
                                "blocked_pid": b["blocked_pid"],
                                "blocked_user": b["blocked_user"],
                                "blocking_pid": b["blocking_pid"],
                                "blocking_user": b["blocking_user"],
                                "blocked_statement": b["blocked_statement"][:200] if b["blocked_statement"] else None,
                                "blocking_statement": b["blocking_statement"][:200] if b["blocking_statement"] else None,
                                "blocked_duration_ms": float(b["blocked_duration_ms"]) if b["blocked_duration_ms"] else 0,
                                "kill_command": f"SELECT pg_terminate_backend({b['blocking_pid']});"
                            }
                            for b in blockings
                        ],
                        "active_locks_summary": [
                            {"lock_type": l["locktype"], "mode": l["mode"], "count": l["count"]}
                            for l in lock_counts
                        ]
                    }
            finally:
                conn.close()
        else:
            conn = _get_mysql_client(info)
            try:
                with conn.cursor() as cur:
                    try:
                        cur.execute("""
                            SELECT 
                                r.trx_id waiting_trx_id, 
                                r.trx_mysql_thread_id waiting_thread, 
                                r.trx_query waiting_query,
                                b.trx_id blocking_trx_id, 
                                b.trx_mysql_thread_id blocking_thread, 
                                b.trx_query blocking_query
                            FROM performance_schema.data_lock_waits w
                            JOIN performance_schema.data_locks b ON b.ENGINE_LOCK_ID = w.BLOCKING_ENGINE_LOCK_ID
                            JOIN performance_schema.data_locks r ON r.ENGINE_LOCK_ID = w.REQUESTING_ENGINE_LOCK_ID;
                        """)
                        blocks = cur.fetchall()
                        return {
                            "connection": info["name"],
                            "engine": "mysql",
                            "blocking_count": len(blocks),
                            "blocking_trees": blocks
                        }
                    except Exception:
                        return {
                            "connection": info["name"],
                            "engine": "mysql",
                            "blocking_count": 0,
                            "message": "No lock contention detected."
                        }
            finally:
                conn.close()
    except Exception as e:
        return _format_db_error(e, info.get("engine", "unknown"))


@mcp.tool()
def export_table(
    table_or_query: str,
    output_path: str,
    format: str = "csv",
    is_query: bool = False,
    schema: Optional[str] = None,
    connection: Optional[str] = None,
    server: Optional[str] = None
) -> Dict[str, Any]:
    """
    Export an entire table or SQL query result directly to a file (CSV, JSON, or TSV) on disk.
    Executes in streaming batches without loading intermediate records into LLM context.
    
    Args:
        table_or_query: Table name (e.g. 'materials') or raw SQL query if is_query=True.
        output_path: Destination file path (e.g. 'exports/materials.csv').
        format: Export format: 'csv', 'json', or 'tsv' (default: 'csv').
        is_query: Set to True if table_or_query is a custom SQL SELECT statement.
        schema: Optional schema name if exporting a table in PostgreSQL.
        connection: Optional connection name or URL.
        server: Optional server or connection alias.
    """
    try:
        info = _get_connection(_resolve_conn(connection, server))
    except Exception as e:
        return _format_db_error(e, "unknown")

    target_file = Path(output_path).resolve()
    target_file.parent.mkdir(parents=True, exist_ok=True)

    fmt = format.lower().strip()
    if fmt not in ("csv", "json", "tsv"):
        return {"error": True, "message": f"Unsupported format '{format}'. Use 'csv', 'json', or 'tsv'."}

    try:
        if info["engine"] == "postgres":
            conn = _get_pg_client(info)
            try:
                with conn.cursor() as cur:
                    if is_query:
                        sql = table_or_query
                    else:
                        resolved = _resolve_pg_table(cur, table_or_query, schema)
                        sql = f'SELECT * FROM "{resolved["schema"]}"."{resolved["table"]}";'

                    cur.execute(sql)
                    col_names = [d[0] for d in cur.description] if cur.description else []
                    
                    rows_count = 0
                    if fmt == "json":
                        with open(target_file, "w", encoding="utf-8") as f:
                            f.write("[\n")
                            first = True
                            while True:
                                batch = cur.fetchmany(2000)
                                if not batch:
                                    break
                                for row in batch:
                                    rows_count += 1
                                    d = {c: _serialize_db_val(row[c]) for c in col_names}
                                    if not first:
                                        f.write(",\n")
                                    f.write("  " + json.dumps(d))
                                    first = False
                            f.write("\n]\n")
                    else:
                        delim = "\t" if fmt == "tsv" else ","
                        with open(target_file, "w", newline="", encoding="utf-8") as f:
                            writer = csv.writer(f, delimiter=delim)
                            writer.writerow(col_names)
                            while True:
                                batch = cur.fetchmany(2000)
                                if not batch:
                                    break
                                for row in batch:
                                    rows_count += 1
                                    writer.writerow([_serialize_db_val(row[c]) for c in col_names])
            finally:
                conn.close()
        else:
            conn = _get_mysql_client(info)
            try:
                with conn.cursor() as cur:
                    sql = table_or_query if is_query else f"SELECT * FROM `{table_or_query}`;"
                    cur.execute(sql)
                    col_names = [d[0] for d in cur.description] if cur.description else []
                    
                    rows_count = 0
                    if fmt == "json":
                        with open(target_file, "w", encoding="utf-8") as f:
                            f.write("[\n")
                            first = True
                            while True:
                                batch = cur.fetchmany(2000)
                                if not batch:
                                    break
                                for row in batch:
                                    rows_count += 1
                                    d = {c: _serialize_db_val(row[c]) for c in col_names}
                                    if not first:
                                        f.write(",\n")
                                    f.write("  " + json.dumps(d))
                                    first = False
                            f.write("\n]\n")
                    else:
                        delim = "\t" if fmt == "tsv" else ","
                        with open(target_file, "w", newline="", encoding="utf-8") as f:
                            writer = csv.writer(f, delimiter=delim)
                            writer.writerow(col_names)
                            while True:
                                batch = cur.fetchmany(2000)
                                if not batch:
                                    break
                                for row in batch:
                                    rows_count += 1
                                    writer.writerow([_serialize_db_val(row[c]) for c in col_names])
            finally:
                conn.close()

        return {
            "status": "success",
            "output_path": str(target_file),
            "rows_exported": rows_count,
            "columns": col_names,
            "file_size_bytes": target_file.stat().st_size
        }
    except Exception as e:
        return _format_db_error(e, info.get("engine", "unknown"), table_or_query)


@mcp.tool()
def import_csv(
    table_name: str,
    csv_path: str,
    delimiter: str = ",",
    schema: Optional[str] = None,
    if_exists: str = "append",
    on_conflict: str = "error",
    batch_size: int = 1000,
    dry_run: bool = False,
    connection: Optional[str] = None,
    server: Optional[str] = None
) -> Dict[str, Any]:
    """
    Bulk import a CSV file directly into a database table with batching and transaction safety.
    Supports dry-run validation (checks all rows against constraints, then safely rolls back).
    
    Args:
        table_name: Destination database table name.
        csv_path: Path to the source CSV file.
        delimiter: CSV delimiter character (default: ',').
        schema: Target schema name (PostgreSQL).
        if_exists: 'append' to insert rows, or 'truncate' to clear table before inserting.
        on_conflict: 'error' (fail on unique constraint violation) or 'ignore' (skip conflicting rows).
        batch_size: Batch size for chunked INSERT execution (default: 1000).
        dry_run: If True, executes the entire insert inside a transaction and rolls back (validates syntax & constraints).
        connection: Optional connection name or URL.
        server: Optional server or connection alias.
    """
    try:
        info = _get_connection(_resolve_conn(connection, server))
    except Exception as e:
        return _format_db_error(e, "unknown")

    src_file = Path(csv_path).resolve()
    if not src_file.exists():
        return {"error": True, "message": f"CSV file not found: {csv_path}"}

    try:
        with open(src_file, "r", encoding="utf-8") as f:
            reader = csv.reader(f, delimiter=delimiter)
            headers = next(reader, None)
            if not headers:
                return {"error": True, "message": "CSV file is empty or missing headers."}
            rows = [r for r in reader if any(r)]

        if not rows:
            return {"status": "success", "message": "CSV contained headers but no data rows.", "rows_inserted": 0}

        quoted_cols = ", ".join(f'"{h.strip()}"' for h in headers)
        
        if info["engine"] == "postgres":
            conn = _get_pg_client(info)
            try:
                conn.autocommit = False
                with conn.cursor() as cur:
                    resolved = _resolve_pg_table(cur, table_name, schema)
                    full_tbl = f'"{resolved["schema"]}"."{resolved["table"]}"'

                    if if_exists.lower() == "truncate" and not dry_run:
                        cur.execute(f"TRUNCATE TABLE {full_tbl} CASCADE;")

                    placeholders = ", ".join(["%s"] * len(headers))
                    conflict_clause = " ON CONFLICT DO NOTHING" if on_conflict.lower() == "ignore" else ""
                    insert_sql = f"INSERT INTO {full_tbl} ({quoted_cols}) VALUES ({placeholders}){conflict_clause}"

                    cleaned_rows = [
                        [None if (val is None or str(val).strip() == "") else val for val in row]
                        for row in rows
                    ]

                    from psycopg2.extras import execute_batch
                    execute_batch(cur, insert_sql, cleaned_rows, page_size=batch_size)

                    if dry_run:
                        conn.rollback()
                        return {
                            "status": "dry_run_success",
                            "message": f"Dry-run simulation succeeded! {len(cleaned_rows)} rows validated against table {full_tbl} constraints without committing.",
                            "table": full_tbl,
                            "rows_validated": len(cleaned_rows),
                            "columns": headers,
                            "dry_run": True
                        }
                    else:
                        conn.commit()
                        return {
                            "status": "success",
                            "message": f"Successfully inserted {len(cleaned_rows)} rows into {full_tbl}.",
                            "table": full_tbl,
                            "rows_inserted": len(cleaned_rows),
                            "columns": headers,
                            "dry_run": False
                        }
            except Exception as e:
                conn.rollback()
                return _format_db_error(e, "postgres", f"INSERT INTO {table_name}")
            finally:
                conn.close()
        else:
            conn = _get_mysql_client(info)
            try:
                conn.autocommit = False
                with conn.cursor() as cur:
                    t = table_name.strip()
                    if if_exists.lower() == "truncate" and not dry_run:
                        cur.execute(f"TRUNCATE TABLE `{t}`;")

                    mysql_cols = ", ".join(f'`{h.strip()}`' for h in headers)
                    placeholders = ", ".join(["%s"] * len(headers))
                    verb = "INSERT IGNORE INTO" if on_conflict.lower() == "ignore" else "INSERT INTO"
                    insert_sql = f"{verb} `{t}` ({mysql_cols}) VALUES ({placeholders})"

                    cleaned_rows = [
                        [None if (val is None or str(val).strip() == "") else val for val in row]
                        for row in rows
                    ]

                    cur.executemany(insert_sql, cleaned_rows)

                    if dry_run:
                        conn.rollback()
                        return {
                            "status": "dry_run_success",
                            "message": f"Dry-run simulation succeeded! {len(cleaned_rows)} rows validated without committing.",
                            "table": t,
                            "rows_validated": len(cleaned_rows),
                            "columns": headers,
                            "dry_run": True
                        }
                    else:
                        conn.commit()
                        return {
                            "status": "success",
                            "message": f"Successfully inserted {len(cleaned_rows)} rows into `{t}`.",
                            "table": t,
                            "rows_inserted": len(cleaned_rows),
                            "columns": headers,
                            "dry_run": False
                        }
            except Exception as e:
                conn.rollback()
                return _format_db_error(e, "mysql", f"INSERT INTO {table_name}")
            finally:
                conn.close()
    except Exception as e:
        return _format_db_error(e, info.get("engine", "unknown"))


def main():
    mcp.run()


if __name__ == "__main__":
    main()
