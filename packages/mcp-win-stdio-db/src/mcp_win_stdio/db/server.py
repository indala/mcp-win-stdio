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


_init_config()


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
    name = target_name or _ACTIVE_CONNECTION
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
    """Switch active database connection. Automatically discovers and connects to sibling databases on the same server."""
    global _ACTIVE_CONNECTION
    info = _get_connection(database)
    _ACTIVE_CONNECTION = info["name"]
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


@mcp.tool()
def list_schemas(connection: Optional[str] = None) -> Dict[str, Any]:
    """List all user schemas with table count and disk size (PostgreSQL) or current database table summary (MySQL)."""
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


@mcp.tool()
def describe_table(tableName: str, schema: Optional[str] = None, connection: Optional[str] = None) -> Dict[str, Any]:
    """Deep inspection of a table: column types, defaults, nullability, PKs, FKs, indexes, and sizes."""
    info = _get_connection(connection)
    if info["engine"] == "postgres":
        conn = _get_pg_client(info)
        try:
            with conn.cursor() as cur:
                resolved = _resolve_pg_table(cur, tableName, schema)
                if resolved.get("notFound"):
                    raise ValueError(f"Table '{tableName}' not found in schema '{resolved['schema']}' or any user schema.")

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


@mcp.tool()
def schema_overview(schema: Optional[str] = "public", connection: Optional[str] = None) -> Dict[str, Any]:
    """High-level architecture map of tables, column summaries, estimated row counts, and disk sizes."""
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
                return {
                    "connection": info["name"],
                    "database": info["database"],
                    "tableCount": len(rows),
                    "tables": rows
                }
        finally:
            conn.close()
    else:
        conn = _get_mysql_client(info)
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT table_name, table_rows AS estimated_rows, ROUND((data_length + index_length) / 1024, 2) AS total_size_kb FROM information_schema.tables WHERE table_schema = DATABASE() ORDER BY table_name;")
                rows = cur.fetchall()
                return {
                    "connection": info["name"],
                    "database": info["database"],
                    "tableCount": len(rows),
                    "tables": rows
                }
        finally:
            conn.close()


@mcp.tool()
def get_table_sample(tableName: str, limit: int = 5, schema: Optional[str] = None, connection: Optional[str] = None) -> Dict[str, Any]:
    """Fetch sample rows from a table along with column metadata and row count estimate."""
    lim = min(max(limit, 1), 100)
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


@mcp.tool()
def search_schema(
    searchTerm: str,
    schema: Optional[str] = "all",
    max_results: int = 50,
    connection: Optional[str] = None
) -> Dict[str, Any]:
    """Search across tables and column names for a keyword with safety limits to protect context window."""
    info = _get_connection(connection)
    safe_max = min(max(1, max_results), 100)
    pat = f"%{searchTerm}%"
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


@mcp.tool()
def read_query(
    sql: str,
    params: Optional[List[Any]] = None,
    limit: int = 50,
    max_cell_chars: int = 500,
    connection: Optional[str] = None
) -> Dict[str, Any]:
    """Safely execute a read-only SELECT query inside a read-only transaction with automatic rollback and token-safe pagination."""
    info = _get_connection(connection)
    p = tuple(params) if params else ()
    safe_limit = min(max(1, limit), 200)

    if info["engine"] == "postgres":
        conn = _get_pg_client(info)
        try:
            conn.set_session(readonly=True, autocommit=False)
            with conn.cursor() as cur:
                cur.execute(sql, p)
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
        finally:
            conn.rollback()
            conn.close()
    else:
        conn = _get_mysql_client(info)
        try:
            with conn.cursor() as cur:
                cur.execute(sql, p)
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
        finally:
            conn.close()



@mcp.tool()
def execute_query(sql: str, params: Optional[List[Any]] = None, dry_run: bool = False, connection: Optional[str] = None) -> Dict[str, Any]:
    """Execute an INSERT, UPDATE, DELETE, or DDL statement with dry_run rollback support."""
    info = _get_connection(connection)
    p = tuple(params) if params else ()
    if info["engine"] == "postgres":
        conn = _get_pg_client(info)
        try:
            with conn.cursor() as cur:
                cur.execute(sql, p)
                rowcount = cur.rowcount
                status = cur.statusmessage
                if dry_run:
                    conn.rollback()
                    return {"connection": info["name"], "dryRun": True, "status": "SUCCESS (ROLLED BACK)", "rowCount": rowcount}
                else:
                    conn.commit()
                    return {"connection": info["name"], "status": status, "rowCount": rowcount}
        finally:
            conn.close()
    else:
        conn = _get_mysql_client(info)
        try:
            with conn.cursor() as cur:
                cur.execute("START TRANSACTION;")
                cur.execute(sql, p)
                rowcount = cur.rowcount
                if dry_run:
                    cur.execute("ROLLBACK;")
                    return {"connection": info["name"], "dryRun": True, "status": "SUCCESS (ROLLED BACK)", "rowCount": rowcount}
                else:
                    cur.execute("COMMIT;")
                    return {"connection": info["name"], "status": "SUCCESS", "rowCount": rowcount}
        finally:
            conn.close()


@mcp.tool()
def explain_query(sql: str, analyze: bool = True, connection: Optional[str] = None) -> Dict[str, Any]:
    """Run EXPLAIN on a SQL statement to inspect execution plan and costs."""
    info = _get_connection(connection)
    if info["engine"] == "postgres":
        conn = _get_pg_client(info)
        try:
            with conn.cursor() as cur:
                exp = f"EXPLAIN (ANALYZE, BUFFERS, COSTS, VERBOSE, FORMAT JSON) {sql}" if analyze else f"EXPLAIN (COSTS, VERBOSE, FORMAT JSON) {sql}"
                cur.execute(exp)
                res = cur.fetchone()
                return {"connection": info["name"], "plan": res[list(res.keys())[0]]}
        finally:
            conn.close()
    else:
        conn = _get_mysql_client(info)
        try:
            with conn.cursor() as cur:
                cur.execute(f"EXPLAIN FORMAT=JSON {sql}")
                res = cur.fetchone()
                return {"connection": info["name"], "plan": res}
        finally:
            conn.close()


@mcp.tool()
def get_database_stats(connection: Optional[str] = None) -> Dict[str, Any]:
    """Get database metrics: database size, active connections, cache hit ratio, engine version."""
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


@mcp.tool()
def add_connection(name: str, url: str, type: Optional[str] = None, setActive: bool = True) -> Dict[str, Any]:
    """Dynamically add a new PostgreSQL or MySQL connection at runtime."""
    global _ACTIVE_CONNECTION
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

    return {
        "success": True,
        "message": f"Connection '{name}' ({info['engine']}) successfully connected and registered.",
        "isActive": _ACTIVE_CONNECTION == name
    }


# ==========================================
# DBA & DATABASE MANAGEMENT TOOLS
# ==========================================

@mcp.tool()
def create_database(database: str, server: Optional[str] = None, encoding: Optional[str] = None, template: Optional[str] = None) -> Dict[str, Any]:
    """Create a new database on the active (or specified) PostgreSQL or MySQL server instance."""
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


@mcp.tool()
def drop_database(database: str, confirmName: str, force: bool = False, server: Optional[str] = None) -> Dict[str, Any]:
    """Safely drop a database. Requires exact 'confirmName' matching the database name. Supports 'force' to kill active connections."""
    global _ACTIVE_CONNECTION
    protected = {"postgres", "template0", "template1", "mysql", "information_schema", "performance_schema", "sys", "cloudsqladmin"}
    if database.lower() in protected:
        raise ValueError(f"Forbidden: Cannot drop protected system database '{database}'.")

    if confirmName != database:
        raise ValueError(f"Safety Confirmation Failed: 'confirmName' ({confirmName}) does not match 'database' ({database}). You must pass confirmName='{database}' to explicitly confirm deletion.")

    info = _get_connection(server)
    if database in _CONNECTION_REGISTRY:
        del _CONNECTION_REGISTRY[database]
    _RAW_CONFIG.pop(database, None)
    if _ACTIVE_CONNECTION == database:
        _ACTIVE_CONNECTION = next(iter(_RAW_CONFIG.keys()), None)

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


@mcp.tool()
def clone_database(sourceDatabase: str, targetDatabase: str, server: Optional[str] = None) -> Dict[str, Any]:
    """Instantly clone an entire database (schema, tables, indexes, data). Uses native template cloning in PostgreSQL."""
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


@mcp.tool()
def terminate_connections(database: str, server: Optional[str] = None) -> Dict[str, Any]:
    """Kill active client connections or hanging locks on a specific database."""
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


@mcp.tool()
def list_active_queries(database: Optional[str] = None, server: Optional[str] = None) -> Dict[str, Any]:
    """Inspect currently executing queries, lock waits, and execution durations."""
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


@mcp.tool()
def dump_database(database: Optional[str] = None, outputPath: Optional[str] = None, schemaOnly: bool = False, server: Optional[str] = None) -> Dict[str, Any]:
    """Export an SQL dump snapshot of the database using native pg_dump or mysqldump."""
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


@mcp.tool()
def restore_database(database: str, dumpFilePath: str, server: Optional[str] = None) -> Dict[str, Any]:
    """Restore a database from a .sql dump file using native psql or mysql."""
    fpath = Path(dumpFilePath)
    if not fpath.exists():
        raise FileNotFoundError(f"Dump file not found: {dumpFilePath}")

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


def main():
    mcp.run()


if __name__ == "__main__":
    main()
