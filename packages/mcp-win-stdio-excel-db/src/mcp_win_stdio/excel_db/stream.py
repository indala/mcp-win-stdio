#!/usr/bin/env python3
"""
High-Performance Bi-Directional Streaming Engine between SQL Databases and Excel Workbooks.
"""

import json
import math
import os
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from urllib.parse import urlparse, unquote

import pandas as pd
from openpyxl import Workbook, load_workbook
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.table import Table, TableStyleInfo
from sqlalchemy import create_engine, text


def clean_cell_value(val: Any) -> Any:
    """Format primitives safely for Excel cells and JSON serialization."""
    if pd.isna(val):
        return None
    elif hasattr(val, "isoformat"):
        return val.isoformat()
    elif isinstance(val, (float, int)) and (math.isnan(val) or math.isinf(val)):
        return None
    return val


def resolve_sqlalchemy_url(conn_config: Union[str, Dict[str, Any]]) -> str:
    """Resolve a raw URL or connection config dictionary into a valid SQLAlchemy connection string."""
    if isinstance(conn_config, str):
        url = conn_config.strip()
        if url.startswith("mysql://"):
            return url.replace("mysql://", "mysql+pymysql://", 1)
        elif url.startswith("postgres://"):
            return url.replace("postgres://", "postgresql+psycopg2://", 1)
        elif url.startswith("postgresql://"):
            return url.replace("postgresql://", "postgresql+psycopg2://", 1)
        elif url.startswith("sqlite://"):
            return url
        return url

    # If dict config
    db_type = conn_config.get("type", "postgres").lower()
    user = conn_config.get("user", "")
    pwd = conn_config.get("password", "")
    host = conn_config.get("host", "localhost")
    port = conn_config.get("port", 5432 if db_type == "postgres" else 3306)
    dbname = conn_config.get("database", "")

    if db_type in ("postgres", "postgresql"):
        return f"postgresql+psycopg2://{user}:{pwd}@{host}:{port}/{dbname}"
    elif db_type == "mysql":
        return f"mysql+pymysql://{user}:{pwd}@{host}:{port}/{dbname}"
    else:
        return f"sqlite:///{dbname}"


def stream_db_to_excel(
    sql_query: str,
    target_excel_path: str,
    db_url_or_config: Union[str, Dict[str, Any]],
    sheet_name: str = "QueryResults",
    if_sheet_exists: str = "replace",
    table_style: Optional[str] = "TableStyleMedium9",
    autofit_columns: bool = True
) -> Dict[str, Any]:
    """Execute SQL query against database and stream directly to Excel workbook file."""
    t_start = datetime.now()
    db_url = resolve_sqlalchemy_url(db_url_or_config)
    engine = create_engine(db_url)

    # Read data directly from database via SQLAlchemy engine
    with engine.connect() as conn:
        df = pd.read_sql_query(text(sql_query), conn)

    row_count, col_count = df.shape
    target_path = Path(target_excel_path).resolve()
    target_path.parent.mkdir(parents=True, exist_ok=True)

    if target_path.exists():
        wb = load_workbook(target_path)
    else:
        wb = Workbook()
        if "Sheet" in wb.sheetnames:
            wb.remove(wb["Sheet"])

    if sheet_name in wb.sheetnames:
        if if_sheet_exists == "replace":
            del wb[sheet_name]
            ws = wb.create_sheet(sheet_name)
        elif if_sheet_exists == "new":
            idx = 1
            new_name = f"{sheet_name}_{idx}"
            while new_name in wb.sheetnames:
                idx += 1
                new_name = f"{sheet_name}_{idx}"
            sheet_name = new_name
            ws = wb.create_sheet(sheet_name)
        else:
            ws = wb[sheet_name]
    else:
        ws = wb.create_sheet(sheet_name)

    # Write headers & rows
    headers = list(df.columns)
    ws.append(headers)

    for row in df.itertuples(index=False, name=None):
        clean_row = [clean_cell_value(v) for v in row]
        ws.append(clean_row)

    # Apply Table Styling
    if table_style and row_count > 0 and col_count > 0:
        table_ref = f"A1:{get_column_letter(col_count)}{row_count + 1}"
        tab_name = re.sub(r'[^a-zA-Z0-9_]', '_', f"Tab_{sheet_name}_{uuid.uuid4().hex[:6]}")
        tab = Table(displayName=tab_name, ref=table_ref)
        tab.tableStyleInfo = TableStyleInfo(name=table_style, showFirstColumn=False, showLastColumn=False, showRowStripes=True)
        ws.add_table(tab)

    # Auto-fit column widths
    if autofit_columns and col_count > 0:
        for col in ws.columns:
            max_len = max(len(str(cell.value or '')) for cell in col)
            col_letter = get_column_letter(col[0].column)
            ws.column_dimensions[col_letter].width = max(min(max_len + 3, 50), 12)

    wb.save(target_path)
    duration = (datetime.now() - t_start).total_seconds()

    return {
        "status": "success",
        "excel_file": str(target_path),
        "sheet_name": sheet_name,
        "rows_streamed": row_count,
        "columns_streamed": col_count,
        "duration_seconds": round(duration, 3),
        "llm_token_savings": "100% (Direct disk streaming)"
    }


def stream_excel_to_db(
    excel_path: str,
    target_table: str,
    db_url_or_config: Union[str, Dict[str, Any]],
    sheet_name: Optional[Union[str, int]] = 0,
    if_table_exists: str = "append",
    chunk_size: int = 1000
) -> Dict[str, Any]:
    """Bulk stream an Excel worksheet into a database table with chunking."""
    t_start = datetime.now()
    src_path = Path(excel_path).resolve()
    if not src_path.exists():
        raise FileNotFoundError(f"Excel file not found: {src_path}")

    db_url = resolve_sqlalchemy_url(db_url_or_config)
    engine = create_engine(db_url)

    df = pd.read_excel(src_path, sheet_name=sheet_name)
    total_rows, total_cols = df.shape

    # Clean column headers for SQL compliance
    df.columns = [re.sub(r'[^a-zA-Z0-9_]', '_', str(c).strip()) for c in df.columns]

    df.to_sql(
        name=target_table,
        con=engine,
        if_exists=if_table_exists,
        index=False,
        chunksize=chunk_size,
        method="multi"
    )

    duration = (datetime.now() - t_start).total_seconds()

    return {
        "status": "success",
        "target_table": target_table,
        "rows_inserted": total_rows,
        "columns_inserted": total_cols,
        "duration_seconds": round(duration, 3)
    }


def stream_db_to_template(
    sql_query: str,
    template_excel_path: str,
    output_excel_path: str,
    db_url_or_config: Union[str, Dict[str, Any]],
    sheet_name: str = "Sheet1",
    start_cell: str = "A2"
) -> Dict[str, Any]:
    """Inject SQL query results into a pre-styled Excel template preserving formatting and formulas."""
    from openpyxl.utils.cell import coordinate_from_string, column_index_from_string
    
    t_start = datetime.now()
    tpl_path = Path(template_excel_path).resolve()
    out_path = Path(output_excel_path).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if not tpl_path.exists():
        raise FileNotFoundError(f"Template Excel file not found: {tpl_path}")

    db_url = resolve_sqlalchemy_url(db_url_or_config)
    engine = create_engine(db_url)

    with engine.connect() as conn:
        df = pd.read_sql_query(text(sql_query), conn)

    wb = load_workbook(tpl_path)
    if sheet_name not in wb.sheetnames:
        ws = wb.active
    else:
        ws = wb[sheet_name]

    col_letter, start_row = coordinate_from_string(start_cell)
    start_col_idx = column_index_from_string(col_letter)

    for r_idx, row in enumerate(df.itertuples(index=False, name=None)):
        for c_idx, val in enumerate(row):
            ws.cell(row=start_row + r_idx, column=start_col_idx + c_idx, value=clean_cell_value(val))

    wb.save(out_path)
    duration = (datetime.now() - t_start).total_seconds()

    return {
        "status": "success",
        "template_used": str(tpl_path),
        "output_file": str(out_path),
        "sheet_name": sheet_name,
        "rows_injected": len(df),
        "duration_seconds": round(duration, 3)
    }
