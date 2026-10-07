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
    py_template_pipeline as run_py_template_pipeline,
    resolve_sqlalchemy_url
)
from mcp_win_stdio.excel_db.engine import run_cross_source_query
from mcp_win_stdio.excel_db.auditor import (
    reconcile_db_vs_excel as audit_reconcile,
    compare_master_datasets as audit_compare_masters
)
from mcp_win_stdio.excel_db.migrator import (
    generate_master_migration_plan as gen_migration_plan,
    sync_master_to_db as execute_sync
)

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
                    entry = conns[target_key]
                    return entry if isinstance(entry, str) else entry.get("url", entry)
            except Exception:
                pass

    # 4. Fallback: If bare db name without protocol, default to local PostgreSQL
    if conn_name_or_url and "://" not in conn_name_or_url and conn_name_or_url != "default":
        return f"postgresql://postgres:postgres@localhost:5432/{conn_name_or_url}"

    return conn_name_or_url or "postgresql://postgres:postgres@localhost:5432/showreel_dev"


@mcp.tool()
def db_to_excel_stream(
    sql_query: str,
    target_excel_path: str,
    connection_name_or_url: Optional[str] = None,
    sheet_name: str = "QueryResults",
    if_sheet_exists: str = "replace",
    table_style: Optional[str] = "TableStyleMedium9",
    autofit_columns: bool = True
) -> Dict[str, Any]:
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
    return res


@mcp.tool()
def excel_to_db_upsert(
    excel_path: str,
    target_table: str,
    connection_name_or_url: Optional[str] = None,
    sheet_name: Optional[Union[str, int]] = 0,
    if_table_exists: str = "append",
    chunk_size: int = 1000
) -> Dict[str, Any]:
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
    return res


@mcp.tool()
def query_unified_sources(
    pipeline_spec_json: Union[Dict[str, Any], str]
) -> Dict[str, Any]:
    """
    Execute a unified cross-source SQL query joining SQL Database tables and Excel spreadsheets in memory.

    Args:
        pipeline_spec_json: Spec dictionary or JSON string defining data sources, transformation SQL, and export target.
    """
    spec = json.loads(pipeline_spec_json) if isinstance(pipeline_spec_json, str) else pipeline_spec_json
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
    return res


@mcp.tool()
def reconcile_db_vs_excel(
    sql_query: str,
    excel_path: str,
    key_columns: List[str],
    connection_name_or_url: Optional[str] = None,
    sheet_name: Optional[Union[str, int]] = 0,
    compare_columns: Optional[List[str]] = None,
    output_report_path: Optional[str] = None
) -> Dict[str, Any]:
    """
    Compare a database query against an Excel spreadsheet, detecting missing records and field-level mismatches.
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
    return res


@mcp.tool()
def compare_master_datasets(
    source_a: Optional[Any] = None,
    source_b: Optional[Any] = None,
    key_columns: Optional[List[str]] = None,
    source_a_json: Optional[str] = None,
    source_b_json: Optional[str] = None,
    source_a_path: Optional[str] = None,
    source_b_path: Optional[str] = None,
    column_mapping: Optional[Union[Dict[str, str], str]] = None,
    column_mapping_json: Optional[str] = None,
    compare_columns: Optional[List[str]] = None,
    numeric_tolerance: float = 0.001,
    tolerance: Optional[float] = None,
    ignore_whitespace_case: bool = True,
    output_report_path: Optional[str] = None,
    output_audit_path: Optional[str] = None
) -> Dict[str, Any]:
    """
    Deterministically compare two master datasets (Excel vs Excel, DB vs Excel, or DB vs DB).
    Detects additions, removals, and field discrepancies with floating-point tolerance.
    Produces a styled multi-tab Excel audit report with KPI summary cards and highlighted diffs.

    Args:
        source_a: Baseline dataset path, dict, or JSON spec.
        source_b: Comparison dataset path, dict, or JSON spec.
        key_columns: Primary key column list in Source A (e.g. ["material_number"]).
        source_a_json: Optional baseline dataset JSON string or path.
        source_b_json: Optional comparison dataset JSON string or path.
        source_a_path: Optional baseline Excel/CSV file path.
        source_b_path: Optional comparison Excel/CSV file path.
        column_mapping: Optional dictionary or JSON mapping Source B columns to Source A columns.
        column_mapping_json: Optional JSON string mapping Source B columns to Source A columns.
        compare_columns: Optional subset of columns to compare.
        numeric_tolerance: Floating-point delta threshold (default 0.001).
        tolerance: Alias for numeric_tolerance.
        ignore_whitespace_case: Trim whitespace and ignore case for text comparison (default True).
        output_report_path: Optional path to generate a styled 4-tab Excel audit diff workbook.
        output_audit_path: Alias for output_report_path.
    """
    raw_a = source_a_path if source_a_path is not None else (source_a if source_a is not None else source_a_json)
    if isinstance(raw_a, str):
        try:
            src_a = json.loads(raw_a)
        except Exception:
            src_a = raw_a
    else:
        src_a = raw_a

    raw_b = source_b_path if source_b_path is not None else (source_b if source_b is not None else source_b_json)
    if isinstance(raw_b, str):
        try:
            src_b = json.loads(raw_b)
        except Exception:
            src_b = raw_b
    else:
        src_b = raw_b

    raw_map = column_mapping if column_mapping is not None else column_mapping_json
    if isinstance(raw_map, str):
        try:
            mapping = json.loads(raw_map)
        except Exception:
            mapping = raw_map
    else:
        mapping = raw_map

    effective_keys = key_columns or []
    effective_tol = tolerance if tolerance is not None else numeric_tolerance
    out_path = output_audit_path or output_report_path

    res = audit_compare_masters(
        source_a=src_a,
        source_b=src_b,
        key_columns=effective_keys,
        column_mapping=mapping,
        compare_columns=compare_columns,
        numeric_tolerance=effective_tol,
        ignore_whitespace_case=ignore_whitespace_case,
        output_report_path=out_path,
        db_resolver_func=_get_db_config
    )
    return res


@mcp.tool()
def generate_master_migration_plan(
    excel_path: str,
    target_table: str,
    key_columns: List[str],
    column_mapping_json: Union[Dict[str, str], str],
    connection_name_or_url: Optional[str] = None,
    sheet_name: Optional[Union[str, int]] = 0,
    output_sql_path: Optional[str] = None,
    on_conflict_action: str = "update",
    fk_lookups_json: Optional[Union[Dict[str, Any], str]] = None,
    price_history_table: Optional[str] = None
) -> Dict[str, Any]:
    """
    Generate atomic, transactional PostgreSQL/MySQL migration SQL from an Excel master.
    Includes pre-flight foreign key validation (resolving codes like 'm' to UUIDs against live DB)
    and conflict handling (UPSERT).

    Args:
        excel_path: Path to Excel master spreadsheet.
        target_table: Destination DB table (e.g. 'props_management.materials').
        key_columns: Primary/unique key columns (e.g. ['material_number']).
        column_mapping_json: Dict or JSON mapping Excel headers to DB columns.
        connection_name_or_url: Optional DB connection alias (e.g. 'showreel_dev') to validate live schema and resolve FKs.
        sheet_name: Sheet name or index (default 0).
        output_sql_path: Optional path to save the generated .sql migration script.
        on_conflict_action: 'update' (UPSERT) or 'nothing'.
        fk_lookups_json: Optional dict or JSON mapping columns to DB lookup tables for foreign keys.
            e.g. '{"base_uom_id": {"table": "props_management.units_of_measurement", "lookup_col": "code", "id_col": "id"}}'
        price_history_table: Optional audit table to log price modifications.
    """
    mapping = json.loads(column_mapping_json) if isinstance(column_mapping_json, str) else column_mapping_json
    fk_lookups = json.loads(fk_lookups_json) if isinstance(fk_lookups_json, str) else fk_lookups_json

    res = gen_migration_plan(
        excel_path=excel_path,
        target_table=target_table,
        key_columns=key_columns,
        column_mapping=mapping,
        connection_name_or_url=connection_name_or_url,
        sheet_name=sheet_name,
        output_sql_path=output_sql_path,
        on_conflict_action=on_conflict_action,
        fk_lookups=fk_lookups,
        price_history_table=price_history_table,
        db_resolver_func=_get_db_config
    )
    return res


@mcp.tool()
def sync_master_to_db(
    excel_path: str,
    target_table: str,
    key_columns: List[str],
    column_mapping_json: Union[Dict[str, str], str],
    connection_name_or_url: str,
    sheet_name: Optional[Union[str, int]] = 0,
    fk_lookups_json: Optional[Union[Dict[str, Any], str]] = None,
    dry_run: bool = True,
    chunk_size: int = 500
) -> Dict[str, Any]:
    """
    Execute master data synchronization against live database with transactional safety.
    Dry-run mode (default) simulates the entire migration and verifies all constraints without committing.

    Args:
        excel_path: Path to Excel master spreadsheet.
        target_table: Destination database table.
        key_columns: Primary/unique key columns.
        column_mapping_json: Dict or JSON mapping Excel headers to DB columns.
        connection_name_or_url: Target database connection alias.
        sheet_name: Sheet name or index.
        fk_lookups_json: Optional dict or JSON mapping columns to DB lookup tables for foreign keys.
        dry_run: If True (default), simulates the migration and rolls back safely. If False, commits changes.
        chunk_size: Batch transaction size.
    """
    mapping = json.loads(column_mapping_json) if isinstance(column_mapping_json, str) else column_mapping_json
    fk_lookups = json.loads(fk_lookups_json) if isinstance(fk_lookups_json, str) else fk_lookups_json

    res = execute_sync(
        excel_path=excel_path,
        target_table=target_table,
        key_columns=key_columns,
        column_mapping=mapping,
        connection_name_or_url=connection_name_or_url,
        sheet_name=sheet_name,
        fk_lookups=fk_lookups,
        dry_run=dry_run,
        chunk_size=chunk_size,
        db_resolver_func=_get_db_config
    )
    return res


@mcp.tool()
def py_template_pipeline(
    template_excel_path: str,
    output_excel_path: str,
    pipeline_spec_json: Union[Dict[str, Any], str]
) -> Dict[str, Any]:
    """
    Execute custom Python/Pandas logic across multiple data sources to construct
    structured DataFrames (e.g. Materials Summary + Inventory Details), and inject them
    into a styled Excel template workbook as styled tables.

    Args:
        template_excel_path: Path to master/template Excel workbook.
        output_excel_path: Path to save the populated workbook.
        pipeline_spec_json: Dict or JSON string defining data sources, python transformation script, and placement targets.
    """
    spec = json.loads(pipeline_spec_json) if isinstance(pipeline_spec_json, str) else pipeline_spec_json
    sources = spec.get("sources", [])
    python_script = spec.get("python_script", "")
    targets = spec.get("targets", [])

    res = run_py_template_pipeline(
        template_excel_path=template_excel_path,
        output_excel_path=output_excel_path,
        sources=sources,
        python_script=python_script,
        targets=targets,
        db_resolver_func=_get_db_config
    )
    return res


@mcp.tool()
def db_to_excel_template(
    sql_query: str,
    template_excel_path: str,
    output_excel_path: str,
    connection_name_or_url: Optional[str] = None,
    sheet_name: str = "Sheet1",
    start_cell: str = "A2"
) -> Dict[str, Any]:
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
    return res

