#!/usr/bin/env python3
"""
High-Performance Excel & DB Power Engine MCP Server.
Part of mcp-win-stdio.
"""

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

try:
    from mcp.server.mcpserver import MCPServer as FastMCP
except (ImportError, ModuleNotFoundError):
    from mcp.server.fastmcp import FastMCP

from mcp_win_stdio.excel_db.stream import (
    stream_db_to_excel,
    stream_excel_to_db,
    stream_db_to_template,
    resolve_sqlalchemy_url
)
from mcp_win_stdio.excel_db.engine import run_cross_source_query
from mcp_win_stdio.excel_db.auditor import reconcile_db_vs_excel as audit_reconcile

mcp = FastMCP("excel-db-mcp")


def _get_db_config(conn_name_or_url: Optional[str] = None) -> str:
    """Resolve database connection identifier against SERVERS env, connections.json, or raw URL."""
    if not conn_name_or_url:
        # Check active default
        conn_name_or_url = "default"

    # 1. Check if raw connection string
    if any(conn_name_or_url.startswith(prefix) for prefix in ("postgresql://", "postgres://", "mysql://", "sqlite://")):
        return conn_name_or_url

    # 2. Check SERVERS environment variable
    servers_env = os.environ.get("SERVERS")
    if servers_env:
        try:
            parsed = json.loads(servers_env)
            s_map = parsed.get("SERVERS", parsed) if isinstance(parsed, dict) else {}
            if conn_name_or_url in s_map:
                return s_map[conn_name_or_url]
            elif conn_name_or_url == "default" and s_map:
                return next(iter(s_map.values()))
        except Exception:
            pass

    # 3. Check ~/.gemini/config/mcp-servers/database-mcp/connections.json
    cfg_paths = [
        Path.home() / ".gemini" / "config" / "mcp-servers" / "database-mcp" / "connections.json",
        Path.home() / ".mcp-win-stdio" / "db_connections.json"
    ]
    for cp in cfg_paths:
        if cp.exists():
            try:
                with open(cp, "r", encoding="utf-8") as f:
                    data = json.load(f)
                target_key = data.get("default") if conn_name_or_url == "default" else conn_name_or_url
                conns = data.get("connections", data)
                if target_key in conns:
                    return conns[target_key]
            except Exception:
                pass

    return conn_name_or_url


@mcp.tool()
def db_to_excel_stream(
    sql_query: str,
    target_excel_path: str,
    connection_name_or_url: Optional[str] = None,
    sheet_name: str = "QueryResults",
    if_sheet_exists: str = "replace",
    table_style: Optional[str] = "TableStyleMedium9",
    autofit_columns: bool = True
) -> str:
    """
    Stream database query results directly to an Excel file without loading intermediate rows into LLM context.
    
    Args:
        sql_query: SQL SELECT query to execute on the database.
        target_excel_path: Path to the target .xlsx file.
        connection_name_or_url: Database connection name or connection URL (uses default if omitted).
        sheet_name: Worksheet name to write to.
        if_sheet_exists: 'replace', 'overlay', or 'new'.
        table_style: Excel table style (e.g. 'TableStyleMedium9' or None).
        autofit_columns: Auto-adjust column widths based on contents.
    """
    db_conn = _get_db_config(connection_name_or_url)
    res = stream_db_to_excel(
        sql_query=sql_query,
        target_excel_path=target_excel_path,
        db_url_or_config=db_conn,
        sheet_name=sheet_name,
        if_sheet_exists=if_sheet_exists,
        table_style=table_style,
        autofit_columns=autofit_columns
    )
    return json.dumps(res, indent=2)


@mcp.tool()
def excel_to_db_upsert(
    excel_path: str,
    target_table: str,
    connection_name_or_url: Optional[str] = None,
    sheet_name: Optional[Union[str, int]] = 0,
    if_table_exists: str = "append",
    chunk_size: int = 1000
) -> str:
    """
    Bulk stream an Excel worksheet directly into a database table with chunking.

    Args:
        excel_path: Path to the source Excel file.
        target_table: Destination database table name.
        connection_name_or_url: Target database connection name or URL.
        sheet_name: Sheet name or index (default: 0).
        if_table_exists: 'append', 'replace', or 'fail'.
        chunk_size: Batch size for chunked database insertion.
    """
    db_conn = _get_db_config(connection_name_or_url)
    res = stream_excel_to_db(
        excel_path=excel_path,
        target_table=target_table,
        db_url_or_config=db_conn,
        sheet_name=sheet_name,
        if_table_exists=if_table_exists,
        chunk_size=chunk_size
    )
    return json.dumps(res, indent=2)


@mcp.tool()
def query_unified_sources(
    pipeline_spec_json: str
) -> str:
    """
    Execute a unified cross-source SQL query joining SQL Database tables and Excel spreadsheets in memory.

    Args:
        pipeline_spec_json: JSON string defining data sources, transformation SQL, and export target.

    Example pipeline_spec_json:
    {
      "sources": [
        {"name": "orders", "type": "db", "connection": "ijitest", "query": "SELECT id, user_id, amount FROM orders"},
        {"name": "vip_users", "type": "excel", "path": "Z:/data/VIP.xlsx", "sheet": "Users"}
      ],
      "transformation_sql": "SELECT o.id, v.username, o.amount FROM orders o JOIN vip_users v ON o.user_id = v.id WHERE o.amount > 100",
      "target": {"type": "excel", "path": "Z:/reports/VIP_Orders.xlsx", "sheet": "VIP_Summary"}
    }
    """
    spec = json.loads(pipeline_spec_json)
    sources = spec.get("sources", [])
    transformation_sql = spec.get("transformation_sql")
    target = spec.get("target")

    if not transformation_sql:
        raise ValueError("Missing 'transformation_sql' in pipeline spec.")

    res = run_cross_source_query(
        sources=sources,
        transformation_sql=transformation_sql,
        target=target,
        db_resolver_func=_get_db_config
    )
    return json.dumps(res, indent=2)


@mcp.tool()
def reconcile_db_vs_excel(
    sql_query: str,
    excel_path: str,
    key_columns: List[str],
    connection_name_or_url: Optional[str] = None,
    sheet_name: Optional[Union[str, int]] = 0,
    compare_columns: Optional[List[str]] = None,
    output_report_path: Optional[str] = None
) -> str:
    """
    Compare a database query against an Excel spreadsheet, detecting missing records and field-level mismatches.

    Args:
        sql_query: Database query to retrieve ground truth.
        excel_path: Path to Excel spreadsheet to compare against.
        key_columns: List of primary key column names to join on.
        connection_name_or_url: Database connection name or URL.
        sheet_name: Sheet name or index.
        compare_columns: Optional subset of columns to compare.
        output_report_path: Optional path to write a styled Excel Diff report.
    """
    db_conn = _get_db_config(connection_name_or_url)
    res = audit_reconcile(
        sql_query=sql_query,
        excel_path=excel_path,
        key_columns=key_columns,
        db_url_or_config=db_conn,
        sheet_name=sheet_name,
        compare_columns=compare_columns,
        output_report_path=output_report_path
    )
    return json.dumps(res, indent=2)


@mcp.tool()
def db_to_excel_template(
    sql_query: str,
    template_excel_path: str,
    output_excel_path: str,
    connection_name_or_url: Optional[str] = None,
    sheet_name: str = "Sheet1",
    start_cell: str = "A2"
) -> str:
    """
    Inject database query results into a pre-styled Excel template preserving logos, charts, and formulas.

    Args:
        sql_query: SQL query to execute.
        template_excel_path: Path to existing template .xlsx.
        output_excel_path: Destination path for populated .xlsx.
        connection_name_or_url: Database connection name or URL.
        sheet_name: Sheet name to write into.
        start_cell: Top-left anchor cell (e.g. 'A2', 'B5').
    """
    db_conn = _get_db_config(connection_name_or_url)
    res = stream_db_to_template(
        sql_query=sql_query,
        template_excel_path=template_excel_path,
        output_excel_path=output_excel_path,
        db_url_or_config=db_conn,
        sheet_name=sheet_name,
        start_cell=start_cell
    )
    return json.dumps(res, indent=2)
