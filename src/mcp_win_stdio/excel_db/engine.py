#!/usr/bin/env python3
"""
Cross-Source Join Engine for executing unified SQL queries across SQL Databases and Excel Workbooks.
"""

import json
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import pandas as pd
from sqlalchemy import create_engine, text

from mcp_win_stdio.excel_db.stream import resolve_sqlalchemy_url, stream_db_to_excel


def run_cross_source_query(
    sources: List[Dict[str, Any]],
    transformation_sql: str,
    target: Optional[Dict[str, Any]] = None,
    db_resolver_func = None
) -> Dict[str, Any]:
    """
    Execute a unified SQL query joining SQL databases and Excel spreadsheets in memory.

    Args:
        sources: List of data source definitions:
            - {"name": "orders", "type": "db", "connection": "postgres", "query": "SELECT * FROM orders"}
            - {"name": "clients", "type": "excel", "path": "Z:/data/clients.xlsx", "sheet": "VIP"}
        transformation_sql: The SQL query to join/transform data across sources.
        target: Optional export target:
            - {"type": "excel", "path": "Z:/out.xlsx", "sheet": "Report"}
            - {"type": "db", "connection": "mysql", "table": "report_tbl"}
        db_resolver_func: Function to resolve connection names to db URLs.
    """
    t_start = datetime.now()
    mem_conn = sqlite3.connect(":memory:")
    loaded_sources_info = []

    try:
        # 1. Ingest all sources into in-memory engine
        for src in sources:
            s_name = src.get("name")
            s_type = src.get("type", "db").lower()

            if not s_name:
                raise ValueError("Each source must specify a unique 'name' table alias.")

            if s_type == "db":
                conn_id = src.get("connection")
                raw_sql = src.get("query")
                if not raw_sql:
                    raise ValueError(f"Source '{s_name}' is missing 'query'.")

                # Resolve DB URL
                db_url = db_resolver_func(conn_id) if db_resolver_func else conn_id
                resolved_url = resolve_sqlalchemy_url(db_url)
                eng = create_engine(resolved_url)

                with eng.connect() as c:
                    df = pd.read_sql_query(text(raw_sql), c)

            elif s_type in ("excel", "xlsx", "csv"):
                file_path = Path(src.get("path", "")).resolve()
                if not file_path.exists():
                    raise FileNotFoundError(f"Source file not found: {file_path}")

                if file_path.suffix.lower() == ".csv":
                    df = pd.read_csv(file_path)
                else:
                    sheet = src.get("sheet", 0)
                    df = pd.read_excel(file_path, sheet_name=sheet)

            else:
                raise ValueError(f"Unsupported source type: '{s_type}'. Supported: 'db', 'excel', 'csv'.")

            # Clean column headers for SQLite
            df.columns = [re.sub(r'[^a-zA-Z0-9_]', '_', str(col).strip()) for col in df.columns]
            df.to_sql(s_name, mem_conn, index=False, if_exists="replace")
            loaded_sources_info.append(f"{s_name} ({len(df)} rows, {len(df.columns)} cols)")

        # 2. Execute unified transformation query
        result_df = pd.read_sql_query(transformation_sql, mem_conn)
        res_rows, res_cols = result_df.shape

        # 3. Export to target or return summary
        output_summary = {}
        if target:
            t_type = target.get("type", "excel").lower()
            if t_type == "excel":
                out_path = Path(target.get("path", "unified_report.xlsx")).resolve()
                out_path.parent.mkdir(parents=True, exist_ok=True)
                sheet_name = target.get("sheet", "Report")
                
                with pd.ExcelWriter(out_path, engine="openpyxl") as writer:
                    result_df.to_excel(writer, sheet_name=sheet_name, index=False)
                output_summary = {
                    "type": "excel",
                    "path": str(out_path),
                    "sheet": sheet_name,
                    "rows_written": res_rows
                }

            elif t_type == "db":
                conn_id = target.get("connection")
                tbl_name = target.get("table", "pipeline_results")
                if_exists = target.get("if_exists", "append")

                db_url = db_resolver_func(conn_id) if db_resolver_func else conn_id
                resolved_url = resolve_sqlalchemy_url(db_url)
                eng = create_engine(resolved_url)

                result_df.to_sql(tbl_name, con=eng, if_exists=if_exists, index=False, chunksize=1000)
                output_summary = {
                    "type": "db",
                    "table": tbl_name,
                    "rows_inserted": res_rows
                }

        duration = (datetime.now() - t_start).total_seconds()

        # If no target specified, return small sample preview (up to 5 rows)
        sample_preview = result_df.head(5).to_dict(orient="records") if not target else None

        return {
            "status": "success",
            "sources_loaded": loaded_sources_info,
            "result_rows": res_rows,
            "result_columns": res_cols,
            "columns": list(result_df.columns),
            "output_target": output_summary if target else "In-Memory Preview",
            "preview_sample": sample_preview,
            "duration_seconds": round(duration, 3)
        }

    finally:
        mem_conn.close()
