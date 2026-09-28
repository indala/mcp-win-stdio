#!/usr/bin/env python3
"""
Unified Database MCP Server for PostgreSQL and MySQL
Part of mcp-win-stdio.
"""

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
            if "default" in data and not _ACTIVE_CONNECTION:
                _ACTIVE_CONNECTION = data["default"]
            conns = data.get("connections", data.get("SERVERS", data))
            if isinstance(conns, dict):
                for k, v in conns.items():
                    if k not in _RAW_CONFIG:
                        _RAW_CONFIG[k] = v
        except Exception as e:
            sys.stderr.write(f"Warning: Failed to load config file: {e}\n")

    # 3. Fallback DATABASE_URL
    db_url = os.environ.get("DATABASE_URL")
    if db_url and "default" not in _RAW_CONFIG:
        _RAW_CONFIG["default"] = db_url

    if not _ACTIVE_CONNECTION and _RAW_CONFIG:
        _ACTIVE_CONNECTION = next(iter(_RAW_CONFIG.keys()))

    # Pre-register all raw configs in connection registry
    for k, v in _RAW_CONFIG.items():
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


def _parse_url(url: str) -> Dict[str, Any]:
    u = urlparse(url)
    engine = "postgres" if u.scheme in ("postgres", "postgresql") else "mysql"
    return {
        "engine": engine,
        "host": u.hostname or "localhost",
        "port": u.port or (5432 if engine == "postgres" else 3306),
        "user": unquote(u.username or ("postgres" if engine == "postgres" else "root")),
        "password": unquote(u.password or ""),
        "database": u.path.lstrip("/") or ("postgres" if engine == "postgres" else ""),
    }


def _get_connection(target_name: Optional[str] = None) -> Dict[str, Any]:
    global _ACTIVE_CONNECTION
    norm_name = _normalize_connection_param(target_name)
    name = norm_name or _ACTIVE_CONNECTION
    if not name:
        raise ValueError("No database connection specified and no active connection set.")

    if name in _CONNECTION_REGISTRY:
        return _CONNECTION_REGISTRY[name]

    if name in _RAW_CONFIG:
        entry = _RAW_CONFIG[name]
        url = entry if isinstance(entry, str) else entry.get("url", "")
        info = _parse_url(url)
        info["name"] = name
        info["url"] = url
        _CONNECTION_REGISTRY[name] = info
        return info

    # Try to derive sibling DB on active server
    if _ACTIVE_CONNECTION and _ACTIVE_CONNECTION in _CONNECTION_REGISTRY:
        curr = _CONNECTION_REGISTRY[_ACTIVE_CONNECTION]
        u = urlparse(curr["url"])
        new_url = f"{u.scheme}://{u.netloc}/{name}"
        info = _parse_url(new_url)
        info["name"] = name
        info["url"] = new_url

        # Test connect
        if info["engine"] == "postgres":
            conn = psycopg2.connect(new_url)
            conn.close()
        else:
            conn = pymysql.connect(
                host=info["host"], port=info["port"], user=info["user"],
                password=info["password"], database=info["database"]
            )
            conn.close()

        _CONNECTION_REGISTRY[name] = info
        _RAW_CONFIG[name] = new_url
        return info

    raise ValueError(f"Connection '{name}' not found. Available: {list(_RAW_CONFIG.keys())}")


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


def _truncate_cell(val: Any, max_chars: int = 500) -> Any:
    """Truncate massive strings or raw binary data and serialize rich DB types (Decimal, UUID, datetime)."""
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
        return [_truncate_cell(x, max_chars) for x in val]
    if isinstance(val, dict):
        return {k: _truncate_cell(v, max_chars) for k, v in val.items()}
    if isinstance(val, str):
        if len(val) > max_chars:
            return val[:max_chars] + f"... [truncated {len(val) - max_chars} chars]"
        return val
    return val


def _truncate_row(row: Dict[str, Any], max_chars: int = 500) -> Dict[str, Any]:
    """Truncate all values in a single row dictionary."""
    return {k: _truncate_cell(v, max_chars) for k, v in row.items()}


# ==========================================
# MCP TOOLS
# ==========================================


@mcp.tool()
def list_connections() -> Dict[str, Any]:
    """List all configured database connections (PostgreSQL & MySQL) and indicate the active connection."""
    conns = []
    for k in _RAW_CONFIG.keys():
        try:
            info = _get_connection(k)
            conns.append({
                "name": k,
                "engine": info["engine"],
                "host": info["host"],
                "port": info["port"],
                "database": info["database"],
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
def use_database(database: str, server: Optional[str] = None) -> Dict[str, Any]:
    """
    Switch active database connection. Automatically discovers and connects to sibling databases on the same server.
    Sticky connection state is guaranteed for all subsequent tool calls when connection is omitted.
    
    Args:
        database: Database name to connect to, or registered connection name.
        server: Optional base server/connection name to find sibling database on (defaults to currently active connection).
    """
    global _ACTIVE_CONNECTION
    clean_db = str(database).strip()
    norm_server = _normalize_connection_param(server)

    # 1. If clean_db is already a known connection name
    if clean_db in _RAW_CONFIG or clean_db in _CONNECTION_REGISTRY:
        try:
            info = _get_connection(clean_db)
            _ACTIVE_CONNECTION = info["name"]
            _save_active_connection(_ACTIVE_CONNECTION)
            return {
                "success": True,
                "message": f"Active connection switched to '{_ACTIVE_CONNECTION}' ({info['engine']} on {info['host']}:{info['port']}/{info['database']}).",
                "activeConnection": _ACTIVE_CONNECTION,
                "engine": info["engine"],
                "database": info["database"]
            }
        except Exception as e:
            return _format_db_error(e)

    # 2. Derive sibling database on server or active connection
    base_name = norm_server or _ACTIVE_CONNECTION
    if not base_name:
        return {
            "error": True,
            "message": "No active connection available to derive sibling database from. Please specify server parameter."
        }

    try:
        base_info = _get_connection(base_name)
    except Exception as e:
        return _format_db_error(e)

    u = urlparse(base_info["url"])
    new_url = f"{u.scheme}://{u.netloc}/{clean_db}"
    info = _parse_url(new_url)
    info["name"] = clean_db
    info["url"] = new_url

    # Verify connectivity before registering
    try:
        if info["engine"] == "postgres":
            conn = psycopg2.connect(new_url)
            conn.close()
        else:
            conn = pymysql.connect(
                host=info["host"], port=info["port"], user=info["user"],
                password=info["password"], database=info["database"]
            )
            conn.close()
    except Exception as e:
        return _format_db_error(e, info["engine"])

    _CONNECTION_REGISTRY[clean_db] = info
    _RAW_CONFIG[clean_db] = new_url
    _ACTIVE_CONNECTION = clean_db
    _save_active_connection(_ACTIVE_CONNECTION)

    return {
        "success": True,
        "message": f"Active connection switched to '{_ACTIVE_CONNECTION}' ({info['engine']} on {info['host']}:{info['port']}/{info['database']}).",
        "activeConnection": _ACTIVE_CONNECTION,
        "engine": info["engine"],
        "database": info["database"]
    }


@mcp.tool()
def list_databases(connection: Optional[str] = None) -> Dict[str, Any]:
    """List all databases available on the active (or specified) server instance."""
    try:
        info = _get_connection(connection)
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
def list_schemas(connection: Optional[str] = None) -> Dict[str, Any]:
    """List all user schemas with table count and disk size (PostgreSQL) or current database table summary (MySQL)."""
    try:
        info = _get_connection(connection)
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
def describe_table(tableName: str, schema: Optional[str] = None, connection: Optional[str] = None) -> Dict[str, Any]:
    """Deep inspection of a table: column types, defaults, nullability, PKs, FKs, indexes, and sizes."""
    try:
        info = _get_connection(connection)
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
def schema_overview(
    schema: Optional[str] = "public",
    connection: Optional[str] = None,
    max_tables: int = 60,
) -> Dict[str, Any]:
    """
    High-level architecture map of tables, column summaries, estimated row counts, and disk sizes.
    Capped to prevent context window bloat in large enterprise databases.
    
    Args:
        schema: Target schema name or 'all' (PostgreSQL). Default 'public'.
        connection: Connection name to query.
        max_tables: Maximum number of tables to detail (default 60, max 150).
    """
    safe_max = min(max(1, max_tables), 150)
    try:
        info = _get_connection(connection)
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
                    cur.execute(sql, tuple(params))
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
def get_table_sample(tableName: str, limit: int = 5, schema: Optional[str] = None, connection: Optional[str] = None) -> Dict[str, Any]:
    """Fetch sample rows from a table along with column metadata and row count estimate."""
    lim = min(max(limit, 1), 100)
    try:
        info = _get_connection(connection)
        if info["engine"] == "postgres":
            conn = _get_pg_client(info)
            try:
                with conn.cursor() as cur:
                    resolved = _resolve_pg_table(cur, tableName, schema)
                    s = resolved["schema"]
                    t = resolved["table"]
                    cur.execute(f'SELECT * FROM "{s}"."{t}" LIMIT %s;', (lim,))
                    rows = cur.fetchall()
                    cleaned_rows = [_truncate_row(r) for r in rows]
                    return {
                        "connection": info["name"],
                        "database": info["database"],
                        "table": t,
                        "schema": s,
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
                    cleaned_rows = [_truncate_row(r) for r in rows]
                    return {
                        "connection": info["name"],
                        "database": info["database"],
                        "table": tableName,
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
    connection: Optional[str] = None
) -> Dict[str, Any]:
    """Search across tables and column names for a keyword with safety limits to protect context window."""
    safe_max = min(max(1, max_results), 100)
    pat = f"%{searchTerm}%"
    try:
        info = _get_connection(connection)
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
    connection: Optional[str] = None
) -> Dict[str, Any]:
    """
    Safely execute a read-only SELECT query inside a read-only transaction with automatic rollback and token-safe pagination.
    Forwards native PostgreSQL / MySQL error diagnostics directly upon error.
    """
    try:
        info = _get_connection(connection)
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
    connection: Optional[str] = None
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
    """
    try:
        info = _get_connection(connection)
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
def explain_query(sql: str, analyze: bool = True, connection: Optional[str] = None) -> Dict[str, Any]:
    """Run EXPLAIN on a SQL statement to inspect execution plan and costs."""
    try:
        info = _get_connection(connection)
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
def get_database_stats(connection: Optional[str] = None) -> Dict[str, Any]:
    """Get database metrics: database size, active connections, cache hit ratio, engine version."""
    try:
        info = _get_connection(connection)
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
            conn = psycopg2.connect(url)
            conn.close()
        else:
            conn = pymysql.connect(
                host=info["host"], port=info["port"], user=info["user"],
                password=info["password"], database=info["database"]
            )
            conn.close()

        _CONNECTION_REGISTRY[name] = info
        _RAW_CONFIG[name] = url
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
def create_database(database: str, server: Optional[str] = None, encoding: Optional[str] = None, template: Optional[str] = None) -> Dict[str, Any]:
    """Create a new database on the active (or specified) PostgreSQL or MySQL server instance."""
    try:
        info = _get_connection(server)
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
def drop_database(database: str, confirmName: str, force: bool = False, server: Optional[str] = None) -> Dict[str, Any]:
    """Safely drop a database. Requires exact 'confirmName' matching the database name. Supports 'force' to kill active connections."""
    global _ACTIVE_CONNECTION
    protected = {"postgres", "template0", "template1", "mysql", "information_schema", "performance_schema", "sys", "cloudsqladmin"}
    if database.lower() in protected:
        return {"error": True, "message": f"Forbidden: Cannot drop protected system database '{database}'."}

    if confirmName != database:
        return {"error": True, "message": f"Safety Confirmation Failed: 'confirmName' ({confirmName}) does not match 'database' ({database}). You must pass confirmName='{database}' to explicitly confirm deletion."}

    try:
        info = _get_connection(server)
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
def clone_database(sourceDatabase: str, targetDatabase: str, server: Optional[str] = None) -> Dict[str, Any]:
    """Instantly clone an entire database (schema, tables, indexes, data). Uses native template cloning in PostgreSQL."""
    try:
        info = _get_connection(server)
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
def terminate_connections(database: str, server: Optional[str] = None) -> Dict[str, Any]:
    """Kill active client connections or hanging locks on a specific database."""
    try:
        info = _get_connection(server)
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
def list_active_queries(database: Optional[str] = None, server: Optional[str] = None) -> Dict[str, Any]:
    """Inspect currently executing queries, lock waits, and execution durations."""
    try:
        info = _get_connection(server)
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
                    cur.execute(sql, tuple(params))
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
def dump_database(database: Optional[str] = None, outputPath: Optional[str] = None, schemaOnly: bool = False, server: Optional[str] = None) -> Dict[str, Any]:
    """Export an SQL dump snapshot of the database using native pg_dump or mysqldump."""
    try:
        info = _get_connection(server)
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
def restore_database(database: str, dumpFilePath: str, server: Optional[str] = None) -> Dict[str, Any]:
    """Restore a database from a .sql dump file using native psql or mysql."""
    fpath = Path(dumpFilePath)
    if not fpath.exists():
        return {"error": True, "message": f"Dump file not found: {dumpFilePath}"}

    try:
        info = _get_connection(server)
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
    connection: Optional[str] = None
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
    """
    try:
        info = _get_connection(connection)
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
    source_connection: str,
    target_connection: str,
    schema: Optional[str] = "public"
) -> Dict[str, Any]:
    """
    Compare table structures, missing tables, missing columns, and data type discrepancies between two database connections.
    Ideal for detecting environment drift (e.g. dev vs staging vs prod).
    
    Args:
        source_connection: Baseline source connection name.
        target_connection: Target connection name to compare against.
        schema: Target schema name (PostgreSQL, default: 'public').
    """
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

        source_tables = _fetch_table_cols(source_connection)
        target_tables = _fetch_table_cols(target_connection)

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

        return {
            "source_connection": source_connection,
            "target_connection": target_connection,
            "identical": not (missing_in_target or extra_in_target or discrepancies),
            "tables_only_in_source": missing_in_target,
            "tables_only_in_target": extra_in_target,
            "common_tables_count": len(common_tables),
            "discrepancies_count": len(discrepancies),
            "table_discrepancies": discrepancies
        }
    except Exception as e:
        return _format_db_error(e)


def main():
    mcp.run()


if __name__ == "__main__":
    main()
