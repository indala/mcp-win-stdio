#!/usr/bin/env python3
"""
High-Performance Excel MCP Server powered by Python, Pandas, OpenPyXL,
and Native Windows Microsoft Excel (COM Automation via PyWin32).
"""

import os
from pathlib import Path
import math
import json
import re
import sqlite3
from typing import Any, Optional, List, Dict, Union, Literal
import pandas as pd
import openpyxl
from copy import copy
from openpyxl.styles import Font, PatternFill, Border, Side, Alignment, numbers
from openpyxl.formatting.rule import CellIsRule, ColorScaleRule, FormulaRule, Rule
from openpyxl.styles.differential import DifferentialStyle
from openpyxl.utils import get_column_letter, column_index_from_string
from openpyxl.utils.cell import coordinate_to_tuple, range_boundaries
from openpyxl.chart import BarChart, LineChart, PieChart, AreaChart, Reference
from openpyxl.worksheet.table import Table, TableStyleInfo
try:
    from mcp.server.mcpserver import MCPServer as FastMCP
except (ImportError, ModuleNotFoundError):
    from mcp.server.fastmcp import FastMCP

# Try importing pywin32 for native Windows Excel COM automation
HAS_WIN32 = False
try:
    import win32com.client
    import pythoncom
    HAS_WIN32 = True
except ImportError:
    HAS_WIN32 = False

# Try importing rapidfuzz
HAS_RAPIDFUZZ = False
try:
    from rapidfuzz import fuzz
    HAS_RAPIDFUZZ = True
except ImportError:
    HAS_RAPIDFUZZ = False

mcp = FastMCP("excel-tools")


def _clean_val(v: Any) -> Any:
    """Helper to convert individual cell values to JSON-safe primitives."""
    if pd.isna(v):
        return None
    elif hasattr(v, "isoformat"):
        return v.isoformat()
    elif isinstance(v, (float, int)) and (math.isnan(v) or math.isinf(v)):
        return None
    return v


def _df_to_clean_records(df: pd.DataFrame) -> List[Dict[str, Any]]:
    """Convert DataFrame to JSON-safe records, cleanly handling NaT, NaN, Timestamps, and dates."""
    clean = df.astype(object).where(pd.notnull(df), None)
    records = clean.to_dict(orient="records")
    for row in records:
        for k, v in row.items():
            row[k] = _clean_val(v)
    return records


def _format_dataframe_output(df: pd.DataFrame, format_type: str = "records") -> Any:
    """Format DataFrame into token-safe output (records, compact list of lists, or tsv)."""
    if format_type == "compact":
        clean = df.astype(object).where(pd.notnull(df), None)
        return [[_clean_val(val) for val in row] for row in clean.itertuples(index=False, name=None)]
    elif format_type == "tsv":
        clean = df.astype(object).where(pd.notnull(df), "")
        return clean.to_csv(sep="\t", index=False)
    else:
        return _df_to_clean_records(df)


# ============================================================================
# EXCEL CELL FORMATTING & STYLING HELPERS
# ============================================================================

NUMBER_FORMAT_PRESETS = {
    "currency": "$#,##0.00",
    "currency_usd": "$#,##0.00",
    "currency_eur": "€#,##0.00",
    "currency_gbp": "£#,##0.00",
    "currency_inr": "₹#,##0.00",
    "currency_int": "$#,##0",
    "percent": "0.0%",
    "percent_2": "0.00%",
    "percentage": "0.00%",
    "number": "#,##0.00",
    "decimal": "#,##0.00",
    "decimal_1": "#,##0.0",
    "integer": "#,##0",
    "int": "#,##0",
    "date": "yyyy-mm-dd",
    "datetime": "yyyy-mm-dd hh:mm:ss",
    "time": "hh:mm:ss",
    "text": "@",
    "scientific": "0.00E+00",
}

COLOR_SCALE_PRESETS = {
    "green_yellow_red": {"min": "63BE7B", "mid": "FFEB84", "max": "F8696B"},
    "red_yellow_green": {"min": "F8696B", "mid": "FFEB84", "max": "63BE7B"},
    "green_white_red": {"min": "63BE7B", "mid": "FFFFFF", "max": "F8696B"},
    "red_white_green": {"min": "F8696B", "mid": "FFFFFF", "max": "63BE7B"},
    "blue_white_red": {"min": "5B9BD5", "mid": "FFFFFF", "max": "ED7D31"},
    "white_green": {"min": "FFFFFF", "max": "63BE7B"},
    "white_red": {"min": "FFFFFF", "max": "F8696B"},
    "white_blue": {"min": "FFFFFF", "max": "5B9BD5"},
}

NAMED_HEX_COLORS = {
    "black": "000000",
    "white": "FFFFFF",
    "red": "FF0000",
    "green": "008000",
    "blue": "0000FF",
    "yellow": "FFFF00",
    "orange": "FFA500",
    "purple": "800080",
    "gray": "808080",
    "grey": "808080",
    "navy": "000080",
    "teal": "008080",
    "silver": "C0C0C0",
    "maroon": "800000",
    "olive": "808000",
    "lightgreen": "C6EFCE",
    "darkgreen": "006100",
    "lightred": "FFC7CE",
    "darkred": "9C0006",
    "lightyellow": "FFEB9C",
    "darkyellow": "9C6500",
    "lightblue": "D9E1F2",
    "darkblue": "1F497D",
}


def _normalize_hex_color(color: Optional[str]) -> Optional[str]:
    if not color:
        return None
    c = str(color).strip().lstrip("#")
    if c.lower() in NAMED_HEX_COLORS:
        return NAMED_HEX_COLORS[c.lower()].upper()
    return c.upper()


def _resolve_number_format(fmt: Optional[str]) -> Optional[str]:
    if not fmt:
        return None
    fmt_lower = fmt.strip().lower()
    return NUMBER_FORMAT_PRESETS.get(fmt_lower, fmt.strip())


def _build_fill(fill_spec: Union[Dict[str, Any], str, None]) -> Optional[PatternFill]:
    if not fill_spec:
        return None
    if isinstance(fill_spec, str):
        color = _normalize_hex_color(fill_spec)
        fill_type = "solid"
    elif isinstance(fill_spec, dict):
        color = _normalize_hex_color(fill_spec.get("color"))
        fill_type = fill_spec.get("fill_type", "solid")
    else:
        return None
    if not color:
        return None
    return PatternFill(start_color=color, end_color=color, fill_type=fill_type)


def _build_border(border_spec: Union[Dict[str, Any], str, None]) -> Optional[Border]:
    if not border_spec:
        return None
    if isinstance(border_spec, str):
        border_spec = {"style": border_spec, "sides": "all"}

    style = border_spec.get("style", "thin")
    color = _normalize_hex_color(border_spec.get("color", "000000"))
    sides = border_spec.get("sides", "all")
    if isinstance(sides, str):
        sides = [sides.lower()]
    elif isinstance(sides, (list, tuple)):
        sides = [str(s).lower() for s in sides]
    else:
        sides = ["all"]

    side_obj = Side(style=style, color=color)
    none_side = Side(style=None)

    apply_all = "all" in sides
    apply_outline = "outline" in sides
    top = side_obj if (apply_all or apply_outline or "top" in sides) else none_side
    bottom = side_obj if (apply_all or apply_outline or "bottom" in sides) else none_side
    left = side_obj if (apply_all or apply_outline or "left" in sides) else none_side
    right = side_obj if (apply_all or apply_outline or "right" in sides) else none_side

    return Border(left=left, right=right, top=top, bottom=bottom)


def _get_cells_in_range(sheet: Any, range_address: str) -> List[Any]:
    """Return a flat list of cell objects from a range string (e.g. 'A1', 'A1:C5')."""
    selected = sheet[range_address]
    cells = []
    if isinstance(selected, tuple):
        for item in selected:
            if isinstance(item, tuple):
                cells.extend(item)
            else:
                cells.append(item)
    else:
        cells.append(selected)
    return cells


def _apply_style_to_cell(
    cell: Any,
    font_spec: Optional[Dict[str, Any]] = None,
    fill_spec: Union[Dict[str, Any], str, None] = None,
    border_spec: Union[Dict[str, Any], str, None] = None,
    alignment_spec: Optional[Dict[str, Any]] = None,
    number_format: Optional[str] = None,
):
    if font_spec:
        cur_f = cell.font
        color = _normalize_hex_color(font_spec.get("color"))
        u_val = font_spec.get("underline")
        underline = u_val if u_val in ["single", "double"] else ("single" if u_val is True else (None if u_val is False else None))
        cell.font = Font(
            name=font_spec.get("name") or (cur_f.name if cur_f and cur_f.name else "Calibri"),
            size=font_spec.get("size") if font_spec.get("size") is not None else (cur_f.size if cur_f and cur_f.size else 11),
            bold=font_spec.get("bold") if font_spec.get("bold") is not None else (cur_f.bold if cur_f else False),
            italic=font_spec.get("italic") if font_spec.get("italic") is not None else (cur_f.italic if cur_f else False),
            underline=underline if underline is not None else (cur_f.underline if cur_f else None),
            strike=font_spec.get("strike") if font_spec.get("strike") is not None else (cur_f.strike if cur_f else False),
            color=color if color is not None else (cur_f.color.rgb if cur_f and cur_f.color and hasattr(cur_f.color, "rgb") else None),
        )

    if fill_spec is not None:
        fill_obj = _build_fill(fill_spec)
        if fill_obj:
            cell.fill = fill_obj

    if border_spec is not None:
        border_obj = _build_border(border_spec)
        if border_obj:
            cell.border = border_obj

    if alignment_spec is not None:
        cur_a = cell.alignment
        cell.alignment = Alignment(
            horizontal=alignment_spec.get("horizontal") or (cur_a.horizontal if cur_a else None),
            vertical=alignment_spec.get("vertical") or (cur_a.vertical if cur_a else None),
            wrap_text=alignment_spec.get("wrap_text") if alignment_spec.get("wrap_text") is not None else (cur_a.wrap_text if cur_a else None),
            text_rotation=alignment_spec.get("text_rotation") if alignment_spec.get("text_rotation") is not None else (cur_a.text_rotation if cur_a else 0),
            indent=alignment_spec.get("indent") if alignment_spec.get("indent") is not None else (cur_a.indent if cur_a else 0),
        )

    if number_format is not None:
        cell.number_format = _resolve_number_format(number_format)


def _handle_excel_lock(file_path: str, err: Exception) -> PermissionError:
    filename = os.path.basename(file_path)
    msg = (
        f"FILE LOCKED BY EXCEL: The file '{filename}' ({file_path}) cannot be written to "
        f"because it is currently open in Microsoft Excel desktop (or another process has an exclusive lock on it).\n\n"
        f"🚨 AGENT ACTION REQUIRED: DO NOT attempt terminal workarounds, PowerShell commands, or custom Python scripts.\n"
        f"👉 PLEASE ASK THE USER: 'Please save and close \"{filename}\" in Microsoft Excel so I can apply the updates.', "
        f"and wait for the user to confirm before retrying."
    )
    return PermissionError(msg)


def _safe_save_workbook(wb: Any, save_path: str):
    """Save an openpyxl workbook with a clear instruction to the agent if locked by desktop Excel."""
    try:
        wb.save(save_path)
    except (PermissionError, OSError) as e:
        raise _handle_excel_lock(save_path, e) from e


# ==========================================
# 1. PANDAS & OPENPYXL FAST DATA TOOLS
# ==========================================

@mcp.tool()
def get_workbook_info(file_path: str) -> Dict[str, Any]:
    """
    Get metadata for an Excel workbook without loading entire sheets into RAM.
    Returns sheet names, dimensions, column headers, and file size.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    file_size_mb = round(os.path.getsize(file_path) / (1024 * 1024), 2)
    wb = openpyxl.load_workbook(file_path, read_only=True, data_only=True)
    sheets_info = []

    try:
        for name in wb.sheetnames:
            ws = wb[name]
            headers = []
            for row in ws.iter_rows(min_row=1, max_row=1, values_only=True):
                headers = [str(cell) if cell is not None else f"Column_{i+1}" for i, cell in enumerate(row)]
                break

            sheets_info.append({
                "name": name,
                "max_rows": ws.max_row,
                "max_columns": ws.max_column,
                "header_count": len(headers),
                "headers_preview": headers[:30],
            })
    finally:
        wb.close()

    return {
        "file_path": file_path,
        "file_size_mb": file_size_mb,
        "total_sheets": len(sheets_info),
        "sheets": sheets_info,
    }


@mcp.tool()
def preview_sheet(
    file_path: str,
    sheet_name: Optional[str] = None,
    header_row: Optional[int] = None,
    nrows: int = 10,
    format: Literal["records", "compact", "tsv"] = "records",
) -> Dict[str, Any]:
    """
    Preview the first N rows of a sheet. Loads only requested rows for speed and minimal token consumption.
    
    Args:
        file_path: Path to the Excel file (.xlsx, .xls, .xlsm).
        sheet_name: Sheet name or index (default is first sheet).
        header_row: 0-indexed row number containing headers (e.g. 5 if header is row 6).
        nrows: Number of preview rows (default 10, max 50).
        format: 'records' (list of dicts), 'compact' (list of lists), or 'tsv'.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    nrows = max(1, min(nrows, 50))
    h_idx = header_row if header_row is not None else 0
    df = pd.read_excel(file_path, sheet_name=sheet_name or 0, nrows=nrows, header=h_idx)
    data = _format_dataframe_output(df, format)

    return {
        "sheet_name": sheet_name or "First Sheet",
        "preview_row_count": len(df),
        "columns": [str(c) for c in df.columns],
        "column_types": {str(col): str(dtype) for col, dtype in df.dtypes.items()},
        "format": format,
        "rows": data if format != "tsv" else None,
        "data": data,
    }


@mcp.tool()
def query_rows(
    file_path: str,
    sheet_name: Optional[str] = None,
    query: Optional[str] = None,
    columns: Optional[List[str]] = None,
    header_row: Optional[int] = None,
    limit: int = 50,
    offset: int = 0,
    format: Literal["records", "compact", "tsv"] = "records",
) -> Dict[str, Any]:
    """
    Query, filter, and paginate through Excel rows using Pandas vectorized expressions.
    To protect chat context window from credit-draining token bloat, responses are safety-capped.
    For bulk data (>100 rows), use 'get_column_values', 'compare_column_values', 'export_to_csv', or format='compact' / 'tsv'.
    
    Args:
        file_path: Path to the Excel file.
        sheet_name: Sheet name or index.
        query: Pandas query filter expression (e.g. "Age > 30 and Status == 'Active'").
        columns: Specific column names to load.
        header_row: 0-indexed row number containing headers (e.g. 5 if header is row 6).
        limit: Max rows to return (default 50; capped at 100 for 'records', 200 for 'compact', 300 for 'tsv').
        offset: Number of rows to skip.
        format: 'records' (list of dicts), 'compact' (list of lists, saves 60% tokens), or 'tsv' (saves 75% tokens).
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    # Safety caps based on format to prevent context bloat
    if format == "tsv":
        max_allowed = 300
    elif format == "compact":
        max_allowed = 200
    else:
        max_allowed = 100

    limit = max(1, min(limit, max_allowed))
    offset = max(0, offset)

    h_idx = header_row if header_row is not None else 0
    df = pd.read_excel(file_path, sheet_name=sheet_name or 0, usecols=columns, header=h_idx)

    if query:
        try:
            df = df.query(query)
        except Exception as e:
            raise ValueError(f"Invalid query expression '{query}': {str(e)}")

    total_matches = len(df)
    paginated_df = df.iloc[offset : offset + limit]
    data = _format_dataframe_output(paginated_df, format)

    result: Dict[str, Any] = {
        "total_matches": total_matches,
        "offset": offset,
        "limit": limit,
        "returned_rows": len(paginated_df),
        "columns": [str(c) for c in df.columns],
        "format": format,
        "rows": data if format != "tsv" else None,
        "data": data,
    }

    if total_matches > (offset + limit):
        result["context_protection_notice"] = (
            f"Returned {len(paginated_df)} of {total_matches} rows. Capped at {limit} to protect your LLM context window. "
            f"DO NOT paginate through thousands of rows in batches through chat, as it will exhaust your token and message limits! "
            f"Instead: 1) Use 'get_column_values' if you only need IDs/codes; 2) Use 'compare_column_values' to compare with DB or other data; "
            f"3) Use 'export_to_csv' to process files on disk locally."
        )

    return result


@mcp.tool()
def read_range(
    file_path: str,
    sheet_name: Optional[str] = None,
    start_row: int = 1,
    end_row: int = 50,
    columns: Optional[List[str]] = None,
    header_row: Optional[int] = None,
    format: Literal["records", "compact", "tsv"] = "records",
) -> Dict[str, Any]:
    """
    Read a specific slice of rows (e.g. rows 100 to 150) without loading the entire spreadsheet.
    Capped to prevent context window bloat.
    
    Args:
        file_path: Path to the Excel file.
        sheet_name: Sheet name or index.
        start_row: First row to read (1-indexed).
        end_row: Last row to read (1-indexed).
        columns: Specific columns to load.
        header_row: Row containing column headers (0-indexed).
        format: 'records', 'compact', or 'tsv'.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    if start_row < 1:
        start_row = 1
    if end_row < start_row:
        raise ValueError(f"end_row ({end_row}) must be >= start_row ({start_row})")

    max_allowed = 300 if format == "tsv" else (200 if format == "compact" else 100)
    nrows = min(end_row - start_row + 1, max_allowed)

    h_idx = header_row if header_row is not None else 0
    if start_row <= (h_idx + 1):
        df = pd.read_excel(file_path, sheet_name=sheet_name or 0, nrows=nrows, usecols=columns, header=h_idx)
    else:
        header_df = pd.read_excel(file_path, sheet_name=sheet_name or 0, nrows=0, usecols=columns, header=h_idx)
        df = pd.read_excel(
            file_path,
            sheet_name=sheet_name or 0,
            skiprows=range(h_idx + 1, start_row),
            nrows=nrows,
            names=header_df.columns,
            usecols=columns,
        )

    data = _format_dataframe_output(df, format)
    res_range: Dict[str, Any] = {
        "start_row": start_row,
        "end_row": start_row + len(df) - 1,
        "row_count": len(df),
        "columns": [str(c) for c in df.columns],
        "format": format,
        "rows": data if format != "tsv" else None,
        "data": data,
    }
    if (end_row - start_row + 1) > max_allowed:
        res_range["context_protection_notice"] = (
            f"Requested {end_row - start_row + 1} rows capped at {max_allowed} to protect your LLM context window. "
            f"Use start_row/end_row to page through specific slices or export_to_csv to process on disk."
        )
    return res_range


@mcp.tool()
def get_column_values(
    file_path: str,
    column: str,
    sheet_name: Optional[str] = None,
    header_row: Optional[int] = None,
    distinct_only: bool = True,
    dropna: bool = True,
    limit: int = 500,
    offset: int = 0,
) -> Dict[str, Any]:
    """
    Extract values from a single column in an Excel sheet with minimal token consumption.
    Ideal for extracting ID lists, SAP codes, SKUs, or status values without dumping full rows into chat.
    
    Args:
        file_path: Path to the Excel file.
        column: Column name to extract.
        sheet_name: Sheet name or index.
        header_row: Row containing headers (0-indexed, default 0).
        distinct_only: Only return unique values (deduplicated, default True).
        dropna: Exclude empty/null values (default True).
        limit: Max values to return (default 500, max 1000).
        offset: Offset into the values list.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    limit = max(1, min(limit, 1000))
    offset = max(0, offset)

    h_idx = header_row if header_row is not None else 0
    df = pd.read_excel(
        file_path,
        sheet_name=sheet_name or 0,
        usecols=[column],
        header=h_idx,
    )
    series = df[column]
    if dropna:
        series = series.dropna()

    total_count = len(series)
    if distinct_only:
        unique_series = series.drop_duplicates()
        total_unique = len(unique_series)
        sliced = unique_series.iloc[offset : offset + limit]
    else:
        total_unique = series.nunique()
        sliced = series.iloc[offset : offset + limit]

    values = [_clean_val(v) for v in sliced]

    return {
        "column": column,
        "total_rows": total_count,
        "unique_count": total_unique,
        "offset": offset,
        "limit": limit,
        "returned_count": len(values),
        "has_more": (offset + limit) < (total_unique if distinct_only else total_count),
        "values": values,
    }


@mcp.tool()
def compare_column_values(
    file_path: str,
    column: str,
    candidate_values: List[Union[str, int, float]],
    sheet_name: Optional[str] = None,
    header_row: Optional[int] = None,
    case_sensitive: bool = False,
    max_sample_items: int = 50,
) -> Dict[str, Any]:
    """
    Compare values in an Excel column against an external candidate list (e.g. from database query).
    Performs instant in-memory set diffing on the server without dumping thousands of rows into LLM context!
    Returns match statistics, count of missing items in candidate list, and count of new items.
    
    Args:
        file_path: Path to the Excel file.
        column: Column name to compare.
        candidate_values: List of values to check against (e.g. IDs from database query).
        sheet_name: Sheet name or index.
        header_row: Header row index (0-indexed, default 0).
        case_sensitive: Case sensitivity for string comparison (default False).
        max_sample_items: Number of sample missing/new items to display in result (default 50).
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    h_idx = header_row if header_row is not None else 0
    df = pd.read_excel(
        file_path,
        sheet_name=sheet_name or 0,
        usecols=[column],
        header=h_idx,
    )
    excel_series = df[column].dropna().astype(str)

    if not case_sensitive:
        excel_norm_map = {val.strip().lower(): val.strip() for val in excel_series if val.strip()}
        cand_norm_map = {str(val).strip().lower(): str(val).strip() for val in candidate_values if str(val).strip()}
    else:
        excel_norm_map = {val.strip(): val.strip() for val in excel_series if val.strip()}
        cand_norm_map = {str(val).strip(): str(val).strip() for val in candidate_values if str(val).strip()}

    excel_set = set(excel_norm_map.keys())
    cand_set = set(cand_norm_map.keys())

    matching_keys = excel_set.intersection(cand_set)
    in_excel_only_keys = excel_set - cand_set
    in_candidates_only_keys = cand_set - excel_set

    in_excel_only = [excel_norm_map[k] for k in list(in_excel_only_keys)[:max_sample_items]]
    in_candidates_only = [cand_norm_map[k] for k in list(in_candidates_only_keys)[:max_sample_items]]

    return {
        "column": column,
        "excel_total_items": len(excel_series),
        "excel_unique_items": len(excel_set),
        "candidate_unique_items": len(cand_set),
        "matched_count": len(matching_keys),
        "new_in_excel_count": len(in_excel_only_keys),
        "missing_from_excel_count": len(in_candidates_only_keys),
        "sample_new_in_excel": in_excel_only,
        "sample_missing_from_excel": in_candidates_only,
        "summary": (
            f"Comparison Complete: {len(matching_keys)} matched. "
            f"{len(in_excel_only_keys)} new items in Excel not in candidate list. "
            f"{len(in_candidates_only_keys)} items in candidate list not in Excel."
        )
    }



@mcp.tool()
def summarize_column(
    file_path: str,
    column: str,
    sheet_name: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Statistical profiling for a specific column in an Excel sheet.
    Computes min, max, median, mean, nulls, or top distinct values.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    df = pd.read_excel(file_path, sheet_name=sheet_name or 0, usecols=[column])
    series = df[column]

    total_count = len(series)
    null_count = int(series.isnull().sum())
    unique_count = int(series.nunique())

    summary: Dict[str, Any] = {
        "column": column,
        "total_rows": total_count,
        "null_count": null_count,
        "unique_count": unique_count,
        "data_type": str(series.dtype),
    }

    if pd.api.types.is_numeric_dtype(series):
        valid = series.dropna()
        if len(valid) > 0:
            summary["numeric_stats"] = {
                "min": float(valid.min()),
                "max": float(valid.max()),
                "mean": round(float(valid.mean()), 4),
                "median": float(valid.median()),
                "std": round(float(valid.std()), 4) if len(valid) > 1 else 0.0,
                "sum": round(float(valid.sum()), 4),
            }
    else:
        val_counts = series.value_counts(dropna=True).head(10).to_dict()
        summary["top_values"] = {str(k): int(v) for k, v in val_counts.items()}

    return summary


@mcp.tool()
def search_text(
    file_path: str,
    search_term: str,
    sheet_name: Optional[str] = None,
    max_results: int = 25,
) -> Dict[str, Any]:
    """
    Search across an Excel sheet for a text keyword or number.
    Returns matching row index, column names, and row preview.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    df = pd.read_excel(file_path, sheet_name=sheet_name or 0)
    mask = df.astype(str).apply(lambda col: col.str.contains(search_term, case=False, na=False, regex=False))
    matched_rows_mask = mask.any(axis=1)

    matched_indices = df[matched_rows_mask].index[:max_results].tolist()
    results = []

    for idx in matched_indices:
        cleaned_row_list = _df_to_clean_records(df.iloc[[idx]])
        row_data = cleaned_row_list[0] if cleaned_row_list else {}
        matching_cols = [col for col in df.columns if str(search_term).lower() in str(df.at[idx, col]).lower()]
        results.append({
            "excel_row_number": idx + 2,
            "matching_columns": matching_cols,
            "row_data": row_data,
        })

    return {
        "search_term": search_term,
        "matches_found": int(matched_rows_mask.sum()),
        "returned_matches": len(results),
        "results": results,
    }


@mcp.tool()
def create_workbook(
    file_path: str,
    data: Union[List[Dict[str, Any]], List[List[Any]]],
    sheet_name: str = "Sheet1",
) -> Dict[str, Any]:
    """
    Create a new Excel file from a list of record dictionaries or a 2D matrix of rows.
    Automatically sets up headers and adjusts column widths.
    """
    if not data:
        raise ValueError("Data list cannot be empty.")

    out_dir = os.path.dirname(os.path.abspath(file_path))
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    if isinstance(data, list) and len(data) > 0 and isinstance(data[0], (list, tuple)):
        headers = [str(h) for h in data[0]]
        rows = data[1:]
        df = pd.DataFrame(rows, columns=headers)
    else:
        df = pd.DataFrame(data)
    try:
        with pd.ExcelWriter(file_path, engine="openpyxl") as writer:
            df.to_excel(writer, sheet_name=sheet_name, index=False)
            ws = writer.sheets[sheet_name]
            for col in ws.columns:
                max_len = max(len(str(cell.value or "")) for cell in col)
                col_letter = openpyxl.utils.get_column_letter(col[0].column)
                ws.column_dimensions[col_letter].width = min(max(max_len + 3, 10), 50)
    except (PermissionError, OSError) as e:
        raise _handle_excel_lock(file_path, e) from e

    return {
        "status": "success",
        "file_path": file_path,
        "sheet_name": sheet_name,
        "rows_created": len(df),
        "columns": list(df.columns),
    }


@mcp.tool()
def append_rows(
    file_path: str,
    rows: List[Dict[str, Any]],
    sheet_name: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Append new rows to an existing sheet without rewriting the entire workbook.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    wb = openpyxl.load_workbook(file_path)
    sheet = wb[sheet_name] if sheet_name and sheet_name in wb.sheetnames else wb.active

    headers = [cell.value for cell in sheet[1]]
    if not headers or all(h is None for h in headers):
        raise ValueError("Sheet does not have a valid header row to append data to.")

    appended_count = 0
    for row_dict in rows:
        row_values = [row_dict.get(h, None) for h in headers]
        sheet.append(row_values)
        appended_count += 1

    _safe_save_workbook(wb, file_path)
    wb.close()

    return {
        "status": "success",
        "file_path": file_path,
        "rows_appended": appended_count,
        "new_total_rows": sheet.max_row,
    }


@mcp.tool()
def add_sheet(
    file_path: str,
    sheet_name: str,
    data: Optional[List[Dict[str, Any]]] = None,
    headers: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Add a new worksheet tab to an existing Excel workbook without modifying other sheets.
    Optionally populates it with initial headers and rows.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    wb = openpyxl.load_workbook(file_path)
    if sheet_name in wb.sheetnames:
        raise ValueError(f"Sheet '{sheet_name}' already exists in workbook. Existing sheets: {wb.sheetnames}")

    ws = wb.create_sheet(title=sheet_name)
    rows_added = 0

    if data and len(data) > 0:
        cols = headers if headers else list(data[0].keys())
        ws.append(cols)
        for item in data:
            ws.append([item.get(c, None) for c in cols])
            rows_added += 1

        # Auto-adjust column widths
        for col in ws.columns:
            max_len = max(len(str(cell.value or "")) for cell in col)
            col_letter = openpyxl.utils.get_column_letter(col[0].column)
            ws.column_dimensions[col_letter].width = min(max(max_len + 3, 10), 50)
    elif headers:
        ws.append(headers)

    all_sheets = list(wb.sheetnames)
    _safe_save_workbook(wb, file_path)
    wb.close()

    return {
        "status": "success",
        "file_path": file_path,
        "sheet_added": sheet_name,
        "rows_added": rows_added,
        "all_sheets": all_sheets,
    }


@mcp.tool()
def rename_sheet(
    file_path: str,
    old_name: str,
    new_name: str,
) -> Dict[str, Any]:
    """
    Rename an existing worksheet tab in an Excel workbook.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    wb = openpyxl.load_workbook(file_path)
    if old_name not in wb.sheetnames:
        raise ValueError(f"Sheet '{old_name}' not found. Available sheets: {wb.sheetnames}")
    if new_name in wb.sheetnames:
        raise ValueError(f"A sheet named '{new_name}' already exists.")

    wb[old_name].title = new_name
    all_sheets = list(wb.sheetnames)
    _safe_save_workbook(wb, file_path)
    wb.close()

    return {
        "status": "success",
        "file_path": file_path,
        "renamed_from": old_name,
        "renamed_to": new_name,
        "all_sheets": all_sheets,
    }


@mcp.tool()
def delete_sheet(
    file_path: str,
    sheet_name: str,
) -> Dict[str, Any]:
    """
    Delete a specific worksheet tab from an existing Excel workbook.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    wb = openpyxl.load_workbook(file_path)
    if sheet_name not in wb.sheetnames:
        raise ValueError(f"Sheet '{sheet_name}' not found. Available sheets: {wb.sheetnames}")
    if len(wb.sheetnames) <= 1:
        raise ValueError("Cannot delete the only sheet in a workbook.")

    wb.remove(wb[sheet_name])
    remaining_sheets = list(wb.sheetnames)
    _safe_save_workbook(wb, file_path)
    wb.close()

    return {
        "status": "success",
        "file_path": file_path,
        "sheet_deleted": sheet_name,
        "remaining_sheets": remaining_sheets,
    }


@mcp.tool()
def update_cells(
    file_path: str,
    updates: List[Dict[str, Any]],
    sheet_name: Optional[str] = None,
    output_path: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Update specific cell coordinates, formulas, and optional styles.
    Example updates:
      [
        {"cell": "B5", "value": 1500, "number_format": "currency", "font": {"bold": True}},
        {"cell": "C5", "value": "=A5*B5", "fill": "D9E1F2"}
      ]

    NOTE: If this file is currently open in Microsoft Excel desktop, saving will fail with
    a locked file error. Ask the user to close the workbook in Excel and retry; do NOT
    attempt terminal workarounds or custom Python scripts.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    wb = openpyxl.load_workbook(file_path)
    sheet = wb[sheet_name] if sheet_name and sheet_name in wb.sheetnames else wb.active

    updated_count = 0
    for item in updates:
        coord = item.get("cell")
        if not coord:
            continue
        
        cell_obj = sheet[coord]
        if "value" in item:
            cell_obj.value = item.get("value")

        # Optional styling
        font_spec = item.get("font")
        fill_spec = item.get("fill")
        border_spec = item.get("border")
        align_spec = item.get("alignment")
        num_fmt = item.get("number_format")

        if any(x is not None for x in (font_spec, fill_spec, border_spec, align_spec, num_fmt)):
            _apply_style_to_cell(
                cell_obj,
                font_spec=font_spec,
                fill_spec=fill_spec,
                border_spec=border_spec,
                alignment_spec=align_spec,
                number_format=num_fmt,
            )
        updated_count += 1

    save_target = output_path or file_path
    _safe_save_workbook(wb, save_target)
    wb.close()

    return {
        "status": "success",
        "file_path": file_path,
        "saved_path": save_target,
        "cells_updated": updated_count,
    }


@mcp.tool()
def write_range(
    file_path: str,
    data: List[List[Any]],
    start_cell: str = "A1",
    sheet_name: Optional[str] = None,
    output_path: Optional[str] = None,
    clear_subsequent_rows: bool = False,
) -> Dict[str, Any]:
    """
    Write a 2D matrix (list of rows) into a worksheet starting at start_cell (e.g. 'A2').
    Significantly faster and more token-efficient than update_cells when writing tabular
    rows, rebuilding entire sheets, or replacing tables.

    Example:
      data=[
        ["AC01001", "AC", "Accessories", 1, "Power Distribution & Boards"],
        ["AC01002", "AC", "Accessories", 1, "Power Distribution & Boards"]
      ]
      start_cell="A2"
      clear_subsequent_rows=True  # (cleans out any old leftover rows below start_cell)

    NOTE: If this file is currently open in Microsoft Excel desktop, saving will fail with
    a locked file error. Ask the user to close the workbook in Excel and retry; do NOT
    attempt terminal workarounds or custom Python scripts.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    wb = openpyxl.load_workbook(file_path)
    sheet = wb[sheet_name] if sheet_name and sheet_name in wb.sheetnames else wb.active

    start_row, start_col = coordinate_to_tuple(start_cell)

    if clear_subsequent_rows and sheet.max_row >= start_row:
        rows_to_delete = sheet.max_row - start_row + 1
        if rows_to_delete > 0:
            sheet.delete_rows(start_row, rows_to_delete)

    cells_written = 0
    for r_offset, row in enumerate(data):
        current_row = start_row + r_offset
        for c_offset, val in enumerate(row):
            current_col = start_col + c_offset
            cell_obj = sheet.cell(row=current_row, column=current_col)
            cell_obj.value = val
            cells_written += 1

    save_target = output_path or file_path
    _safe_save_workbook(wb, save_target)
    wb.close()

    return {
        "status": "success",
        "file_path": file_path,
        "saved_path": save_target,
        "sheet_name": sheet.title,
        "start_cell": start_cell,
        "rows_written": len(data),
        "cells_written": cells_written,
    }


# ============================================================================
# 1B. STYLING, CONDITIONAL FORMATTING & LAYOUT TOOLS
# ============================================================================

@mcp.tool()
def format_cells(
    file_path: str,
    range_address: Optional[str] = None,
    sheet_name: Optional[str] = None,
    output_path: Optional[str] = None,
    font: Optional[Dict[str, Any]] = None,
    fill: Optional[Union[Dict[str, Any], str]] = None,
    border: Optional[Union[Dict[str, Any], str]] = None,
    alignment: Optional[Dict[str, Any]] = None,
    number_format: Optional[str] = None,
    batch_formats: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    Format a range of cells (e.g. 'A1:E1', 'B2:B20', 'C5') or multiple ranges with custom styles.

    Parameters:
    - file_path: Path to the .xlsx workbook.
    - range_address: Cell coordinate or range string (e.g., 'A1:H1', 'B2:B50', 'C5').
    - sheet_name: Optional worksheet name (defaults to active sheet).
    - output_path: Optional output path (if None, modifies workbook in-place).
    - font: Dict with styling options:
        {"name": "Calibri", "size": 12, "bold": True, "italic": False, "color": "FF0000", "underline": "single", "strike": False}
    - fill: Hex color string (e.g. "1F497D", "#D9E1F2", "lightgreen") or dict {"color": "1F497D", "fill_type": "solid"}.
    - border: Border style string ("thin", "thick", "double", "dashed") or dict
        {"style": "thin", "color": "000000", "sides": ["top", "bottom", "left", "right"]}.
    - alignment: Dict with alignment options:
        {"horizontal": "center", "vertical": "center", "wrap_text": True, "text_rotation": 0, "indent": 0}.
    - number_format: Preset ("currency", "percent", "decimal", "integer", "date") or custom Excel format string (e.g. "$#,##0.00").
    - batch_formats: Optional list of formatting rules for multiple ranges in one turn:
        [
          {"range": "A1:E1", "fill": "1F497D", "font": {"bold": True, "color": "FFFFFF"}, "alignment": {"horizontal": "center"}},
          {"range": "D2:D100", "number_format": "currency"},
          {"range": "E2:E100", "number_format": "percent"}
        ]

    NOTE: If this file is currently open in Microsoft Excel desktop, saving will fail with
    a locked file error. Ask the user to close the workbook in Excel and retry; do NOT
    attempt terminal workarounds or custom Python scripts.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    wb = openpyxl.load_workbook(file_path)
    sheet = wb[sheet_name] if sheet_name and sheet_name in wb.sheetnames else wb.active

    operations = []
    if batch_formats:
        operations.extend(batch_formats)
    if range_address:
        operations.append({
            "range": range_address,
            "font": font,
            "fill": fill,
            "border": border,
            "alignment": alignment,
            "number_format": number_format,
        })

    if not operations:
        wb.close()
        return {
            "status": "warning",
            "message": "No formatting applied: specify range_address or batch_formats.",
            "file_path": file_path,
            "cells_formatted": 0,
        }

    total_cells = 0
    for op in operations:
        r_addr = op.get("range") or op.get("range_address")
        if not r_addr:
            continue
        cells = _get_cells_in_range(sheet, r_addr)
        op_font = op.get("font")
        op_fill = op.get("fill")
        op_border = op.get("border")
        op_align = op.get("alignment")
        op_num = op.get("number_format")

        for cell in cells:
            _apply_style_to_cell(
                cell,
                font_spec=op_font,
                fill_spec=op_fill,
                border_spec=op_border,
                alignment_spec=op_align,
                number_format=op_num,
            )
            total_cells += 1

    save_target = output_path or file_path
    _safe_save_workbook(wb, save_target)
    wb.close()

    return {
        "status": "success",
        "file_path": file_path,
        "saved_path": save_target,
        "ranges_formatted": len(operations),
        "cells_formatted": total_cells,
    }


@mcp.tool()
def get_cell_formatting(
    file_path: str,
    cells: Optional[Union[List[str], str]] = None,
    range_address: Optional[str] = None,
    sheet_name: Optional[str] = None,
    max_cells: int = 50,
) -> Dict[str, Any]:
    """
    Inspect the visual formatting, typography, fills, alignments, borders, and number formats
    of specific cells or cell ranges in an Excel worksheet.

    Ideal for:
    - Checking the exact font name, size, bold weight, and hex color of existing table headers.
    - Inspecting cell fill colors (hex RGB) and alignments to replicate existing styling.
    - Inspecting number formats (currency, percentage, date strings) on specific cells.

    Parameters:
    - file_path: Path to the .xlsx workbook.
    - cells: Specific cell coordinate(s), e.g. ["K1", "L1"] or "K1, L1, M1" or "A1".
    - range_address: Cell range coordinate (e.g. "A1:E1" or "K1:L10").
    - sheet_name: Optional sheet name (defaults to active sheet).
    - max_cells: Maximum number of cells to inspect to protect context window (default 50).
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    wb = openpyxl.load_workbook(file_path, data_only=False)
    sheet = wb[sheet_name] if sheet_name and sheet_name in wb.sheetnames else wb.active

    target_cells: List[str] = []
    if cells:
        if isinstance(cells, str):
            target_cells.extend([c.strip().upper() for c in re.split(r"[,;\s]+", cells) if c.strip()])
        elif isinstance(cells, list):
            for c in cells:
                if isinstance(c, str):
                    target_cells.extend([x.strip().upper() for x in re.split(r"[,;\s]+", c) if x.strip()])

    if range_address:
        try:
            for row in sheet[range_address]:
                if isinstance(row, (tuple, list)):
                    for cell in row:
                        if cell.coordinate not in target_cells:
                            target_cells.append(cell.coordinate)
                else:
                    if row.coordinate not in target_cells:
                        target_cells.append(row.coordinate)
        except Exception:
            pass

    if not target_cells:
        for col in range(1, min(15, sheet.max_column + 1)):
            target_cells.append(f"{get_column_letter(col)}1")

    target_cells = target_cells[:max_cells]

    formatted_results = []
    for coord in target_cells:
        try:
            cell_obj = sheet[coord]
        except Exception:
            continue

        font_info = {}
        if cell_obj.font:
            font_color = None
            if cell_obj.font.color:
                if hasattr(cell_obj.font.color, "rgb") and cell_obj.font.color.rgb is not None:
                    font_color = str(cell_obj.font.color.rgb)
                elif hasattr(cell_obj.font.color, "theme") and cell_obj.font.color.theme is not None:
                    font_color = f"theme:{cell_obj.font.color.theme}"
            font_info = {
                "name": cell_obj.font.name,
                "size": cell_obj.font.size,
                "bold": bool(cell_obj.font.bold),
                "italic": bool(cell_obj.font.italic),
                "underline": cell_obj.font.underline,
                "strike": bool(cell_obj.font.strike),
                "color": font_color,
            }

        fill_info = {}
        if cell_obj.fill:
            fg_color = None
            fg = getattr(cell_obj.fill, "fgColor", None) or getattr(cell_obj.fill, "start_color", None)
            if fg and hasattr(fg, "rgb") and fg.rgb is not None:
                fg_color = str(fg.rgb)
            elif fg and hasattr(fg, "theme") and fg.theme is not None:
                fg_color = f"theme:{fg.theme}"

            bg_color = None
            bg = getattr(cell_obj.fill, "bgColor", None) or getattr(cell_obj.fill, "end_color", None)
            if bg and hasattr(bg, "rgb") and bg.rgb is not None:
                bg_color = str(bg.rgb)

            fill_info = {
                "fill_type": cell_obj.fill.fill_type,
                "fg_color": fg_color,
                "bg_color": bg_color,
            }

        align_info = {}
        if cell_obj.alignment:
            align_info = {
                "horizontal": cell_obj.alignment.horizontal,
                "vertical": cell_obj.alignment.vertical,
                "wrap_text": bool(cell_obj.alignment.wrap_text),
                "text_rotation": cell_obj.alignment.text_rotation,
            }

        border_info = {}
        if cell_obj.border:
            border_info = {
                "top": cell_obj.border.top.style if cell_obj.border.top else None,
                "bottom": cell_obj.border.bottom.style if cell_obj.border.bottom else None,
                "left": cell_obj.border.left.style if cell_obj.border.left else None,
                "right": cell_obj.border.right.style if cell_obj.border.right else None,
            }

        formatted_results.append({
            "cell": coord,
            "value": _clean_val(cell_obj.value),
            "data_type": cell_obj.data_type,
            "number_format": cell_obj.number_format,
            "font": font_info,
            "fill": fill_info,
            "alignment": align_info,
            "border": border_info,
        })

    wb.close()
    return {
        "status": "success",
        "file_path": file_path,
        "sheet_name": sheet.title,
        "total_cells_inspected": len(formatted_results),
        "cells": formatted_results,
    }


@mcp.tool()
def apply_conditional_formatting(
    file_path: str,
    range_address: str,
    rule_type: str,
    sheet_name: Optional[str] = None,
    output_path: Optional[str] = None,
    operator: Optional[str] = None,
    formula: Optional[List[str]] = None,
    fill_color: Optional[str] = None,
    font_color: Optional[str] = None,
    bold: Optional[bool] = None,
    color_scale_preset: Optional[str] = None,
    color_scale: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """
    Apply conditional formatting rules to an Excel sheet.

    Rule types supported:
    1. 'cell_is': Highlights cells based on comparison operator
       - operator: 'greaterThan', 'lessThan', 'equal', 'notEqual', 'between', 'notBetween', 'greaterThanOrEqual', 'lessThanOrEqual'.
       - formula: e.g. ["100"] or ["50", "100"] for between.
       - fill_color: Hex color string (e.g. "C6EFCE" for soft green, "FFC7CE" for soft red).
       - font_color: Hex color string (e.g. "006100" for dark green, "9C0006" for dark red).
       - bold: Optional boolean.

    2. 'color_scale': Applies 2-color or 3-color heatmap gradients.
       - color_scale_preset: 'green_yellow_red', 'red_yellow_green', 'green_white_red', 'red_white_green', 'blue_white_red', 'white_green', 'white_red', 'white_blue'.
       - color_scale: Custom dict with 'min', 'mid' (optional), 'max' hex colors (e.g. {"min": "63BE7B", "mid": "FFEB84", "max": "F8696B"}).

    3. 'duplicate_values' / 'unique_values':
       - Highlights duplicate or unique cells in the range with fill_color/font_color.

    4. 'formula':
       - Evaluates custom Excel formula (e.g. formula=["$B2>100"] or formula=["ISBLANK(C2)"]).
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    wb = openpyxl.load_workbook(file_path)
    sheet = wb[sheet_name] if sheet_name and sheet_name in wb.sheetnames else wb.active

    norm_fill = _normalize_hex_color(fill_color)
    norm_font = _normalize_hex_color(font_color)
    fill_obj = PatternFill(start_color=norm_fill, end_color=norm_fill, fill_type="solid") if norm_fill else None
    font_obj = Font(color=norm_font, bold=bold) if (norm_font or bold is not None) else None

    rt = rule_type.lower().replace("-", "_")

    if rt == "cell_is":
        op = operator or "greaterThan"
        form_list = formula or ["0"]
        rule = CellIsRule(operator=op, formula=form_list, stopIfTrue=True, fill=fill_obj, font=font_obj)
        sheet.conditional_formatting.add(range_address, rule)

    elif rt == "color_scale":
        preset_dict = None
        if color_scale_preset and color_scale_preset.lower() in COLOR_SCALE_PRESETS:
            preset_dict = COLOR_SCALE_PRESETS[color_scale_preset.lower()]
        elif color_scale:
            preset_dict = color_scale

        if not preset_dict:
            preset_dict = COLOR_SCALE_PRESETS["green_yellow_red"]

        min_c = _normalize_hex_color(preset_dict.get("min", "63BE7B"))
        mid_c = _normalize_hex_color(preset_dict.get("mid"))
        max_c = _normalize_hex_color(preset_dict.get("max", "F8696B"))

        if mid_c:
            scale_rule = ColorScaleRule(
                start_type="min",
                start_color=min_c,
                mid_type="percentile",
                mid_value=50,
                mid_color=mid_c,
                end_type="max",
                end_color=max_c,
            )
        else:
            scale_rule = ColorScaleRule(start_type="min", start_color=min_c, end_type="max", end_color=max_c)
        sheet.conditional_formatting.add(range_address, scale_rule)

    elif rt in ("duplicate_values", "unique_values"):
        dxf_type = "duplicateValues" if rt == "duplicate_values" else "uniqueValues"
        dxf = DifferentialStyle(font=font_obj, fill=fill_obj)
        rule = Rule(type=dxf_type, dxf=dxf, stopIfTrue=True)
        sheet.conditional_formatting.add(range_address, rule)

    elif rt == "formula":
        form_list = formula or ["$A1>0"]
        rule = FormulaRule(formula=form_list, stopIfTrue=True, fill=fill_obj, font=font_obj)
        sheet.conditional_formatting.add(range_address, rule)

    else:
        wb.close()
        raise ValueError(
            f"Unsupported rule_type '{rule_type}'. Supported: 'cell_is', 'color_scale', 'duplicate_values', 'unique_values', 'formula'."
        )

    save_target = output_path or file_path
    _safe_save_workbook(wb, save_target)
    wb.close()

    return {
        "status": "success",
        "file_path": file_path,
        "saved_path": save_target,
        "range_address": range_address,
        "rule_type": rt,
        "operator": operator if rt == "cell_is" else None,
    }


@mcp.tool()
def set_sheet_layout_and_freeze(
    file_path: str,
    sheet_name: Optional[str] = None,
    output_path: Optional[str] = None,
    column_widths: Optional[Dict[str, float]] = None,
    auto_fit_columns: bool = False,
    row_heights: Optional[Dict[Union[int, str], float]] = None,
    freeze_panes: Optional[str] = None,
    show_grid_lines: Optional[bool] = None,
) -> Dict[str, Any]:
    """
    Configure worksheet layout, column widths, auto-fitting, row heights, and freeze panes.

    Parameters:
    - file_path: Path to the .xlsx workbook.
    - sheet_name: Optional worksheet name (defaults to active sheet).
    - output_path: Optional output path (if None, modifies in-place).
    - column_widths: Dict mapping column letter to width in characters (e.g. {"A": 15, "B": 30, "C": 20}).
    - auto_fit_columns: If True, automatically measures text lengths across all columns and sets optimal column widths with padding.
    - row_heights: Dict mapping row index to height in points (e.g. {"1": 28, "2": 20}).
    - freeze_panes: Cell coordinate to freeze at (e.g. "A2" freezes header row 1, "B2" freezes col A & row 1, "None" or "" unfreezes).
    - show_grid_lines: True to display gridlines, False to hide them.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    wb = openpyxl.load_workbook(file_path)
    sheet = wb[sheet_name] if sheet_name and sheet_name in wb.sheetnames else wb.active

    results = {}

    if auto_fit_columns:
        col_widths = {}
        for col in sheet.columns:
            col_letter = get_column_letter(col[0].column)
            max_len = 0
            for cell in col:
                if cell.value is not None:
                    for line in str(cell.value).split("\n"):
                        if len(line) > max_len:
                            max_len = len(line)
            calculated = max(max_len + 3, 10.0)
            sheet.column_dimensions[col_letter].width = calculated
            col_widths[col_letter] = calculated
        results["auto_fit_columns"] = col_widths

    if column_widths:
        for col_letter, width in column_widths.items():
            clean_letter = col_letter.strip().upper()
            sheet.column_dimensions[clean_letter].width = float(width)
        results["custom_column_widths"] = column_widths

    if row_heights:
        for row_idx, height in row_heights.items():
            clean_idx = int(str(row_idx).strip())
            sheet.row_dimensions[clean_idx].height = float(height)
        results["row_heights"] = row_heights

    if freeze_panes is not None:
        if str(freeze_panes).lower() in ("none", "", "false", "null"):
            sheet.freeze_panes = None
            results["freeze_panes"] = None
        else:
            sheet.freeze_panes = str(freeze_panes).strip().upper()
            results["freeze_panes"] = sheet.freeze_panes

    if show_grid_lines is not None:
        if hasattr(sheet, "views") and sheet.views.sheetView:
            sheet.views.sheetView[0].showGridLines = bool(show_grid_lines)
        else:
            sheet.sheet_view.showGridLines = bool(show_grid_lines)
        results["show_grid_lines"] = show_grid_lines

    save_target = output_path or file_path
    _safe_save_workbook(wb, save_target)
    wb.close()

    return {
        "status": "success",
        "file_path": file_path,
        "saved_path": save_target,
        "sheet_name": sheet.title,
        "settings_applied": results,
    }


@mcp.tool()
def create_chart(
    file_path: str,
    chart_type: str,
    data_range: str,
    categories_range: Optional[str] = None,
    title: Optional[str] = None,
    target_cell: str = "E2",
    sheet_name: Optional[str] = None,
    output_path: Optional[str] = None,
    x_axis_title: Optional[str] = None,
    y_axis_title: Optional[str] = None,
    width: float = 16.0,
    height: float = 10.0,
) -> Dict[str, Any]:
    """
    Create an embedded native Excel chart (column, bar, line, pie, area) and insert it into a sheet.

    Parameters:
    - file_path: Path to the .xlsx workbook.
    - chart_type: 'col' (or 'column'), 'bar' (horizontal), 'line', 'pie', 'area'.
    - data_range: Coordinates of numeric series including header (e.g. 'B1:C10').
    - categories_range: Coordinates of X-axis labels/categories excluding header (e.g. 'A2:A10').
    - title: Title displayed above the chart.
    - target_cell: Top-left cell coordinate where the chart will be placed (default 'E2').
    - sheet_name: Worksheet name (defaults to active sheet).
    - output_path: Optional output path (if None, modifies in-place).
    - x_axis_title / y_axis_title: Optional axis labels.
    - width / height: Chart dimensions in cm (default 16 x 10).

    NOTE: If this file is currently open in Microsoft Excel desktop, saving will fail with
    a locked file error. Ask the user to close the workbook in Excel and retry; do NOT
    attempt terminal workarounds or custom Python scripts.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    wb = openpyxl.load_workbook(file_path)
    sheet = wb[sheet_name] if sheet_name and sheet_name in wb.sheetnames else wb.active

    ct = chart_type.lower().strip()
    if ct in ("col", "column"):
        chart = BarChart()
        chart.type = "col"
    elif ct == "bar":
        chart = BarChart()
        chart.type = "bar"
    elif ct == "line":
        chart = LineChart()
    elif ct == "pie":
        chart = PieChart()
    elif ct == "area":
        chart = AreaChart()
    else:
        wb.close()
        raise ValueError(
            f"Unsupported chart_type '{chart_type}'. Supported types: 'col', 'bar', 'line', 'pie', 'area'."
        )

    if title:
        chart.title = title
    chart.width = width
    chart.height = height

    if x_axis_title and hasattr(chart, "x_axis") and chart.x_axis:
        chart.x_axis.title = x_axis_title
    if y_axis_title and hasattr(chart, "y_axis") and chart.y_axis:
        chart.y_axis.title = y_axis_title

    min_col, min_row, max_col, max_row = range_boundaries(data_range)
    data_ref = Reference(sheet, min_col=min_col, min_row=min_row, max_col=max_col, max_row=max_row)
    chart.add_data(data_ref, titles_from_data=True)

    if categories_range:
        c_min_col, c_min_row, c_max_col, c_max_row = range_boundaries(categories_range)
        cats_ref = Reference(sheet, min_col=c_min_col, min_row=c_min_row, max_col=c_max_col, max_row=c_max_row)
        chart.set_categories(cats_ref)

    sheet.add_chart(chart, target_cell)

    save_target = output_path or file_path
    _safe_save_workbook(wb, save_target)
    wb.close()

    return {
        "status": "success",
        "file_path": file_path,
        "saved_path": save_target,
        "sheet_name": sheet.title,
        "chart_type": ct,
        "target_cell": target_cell,
        "title": title,
    }


@mcp.tool()
def clean_and_deduplicate_sheet(
    file_path: str,
    sheet_name: Optional[str] = None,
    output_path: Optional[str] = None,
    deduplicate_columns: Optional[List[str]] = None,
    trim_text: bool = True,
    normalize_dates: bool = False,
    date_columns: Optional[List[str]] = None,
    drop_empty_rows: bool = True,
    drop_empty_columns: bool = False,
    fill_nulls: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    Perform automated high-speed data cleaning, standardization, and deduplication on an Excel sheet using Pandas.

    Parameters:
    - file_path: Path to the .xlsx workbook.
    - sheet_name: Optional worksheet name (defaults to active sheet).
    - output_path: Optional output path (if None, modifies in-place).
    - deduplicate_columns: List of column names to check for duplicates (or all columns if None).
    - trim_text: Strip leading and trailing whitespace from text values (default True).
    - normalize_dates: Attempt parsing and standardizing dates to YYYY-MM-DD.
    - date_columns: Optional list of specific column names to normalize dates on.
    - drop_empty_rows: Remove rows that are completely blank (default True).
    - drop_empty_columns: Remove columns that are completely blank (default False).
    - fill_nulls: Optional value to replace remaining null/NaN cells with.

    Returns cleaning metrics: initial_rows, final_rows, duplicates_removed, empty_rows_dropped.

    NOTE: If this file is currently open in Microsoft Excel desktop, saving will fail with
    a locked file error. Ask the user to close the workbook in Excel and retry; do NOT
    attempt terminal workarounds or custom Python scripts.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    wb_meta = openpyxl.load_workbook(file_path, read_only=True)
    target_sheet = sheet_name if sheet_name and sheet_name in wb_meta.sheetnames else wb_meta.sheetnames[0]
    wb_meta.close()

    df = pd.read_excel(file_path, sheet_name=target_sheet)
    initial_rows = len(df)

    empty_rows_dropped = 0
    if drop_empty_rows:
        before = len(df)
        df = df.dropna(how="all")
        empty_rows_dropped = before - len(df)

    empty_cols_dropped = 0
    if drop_empty_columns:
        before_c = len(df.columns)
        df = df.dropna(axis=1, how="all")
        empty_cols_dropped = before_c - len(df.columns)

    if trim_text:
        for col in df.select_dtypes(include=["object", "string"]).columns:
            df[col] = df[col].astype(str).str.strip().replace({"nan": None, "None": None, "<NA>": None})

    if normalize_dates:
        target_date_cols = date_columns if date_columns else list(df.select_dtypes(include=["object", "string", "datetime"]).columns)
        for col in target_date_cols:
            if col in df.columns:
                try:
                    parsed = pd.to_datetime(df[col], errors="coerce")
                    if parsed.notnull().sum() > 0:
                        df[col] = parsed.dt.strftime("%Y-%m-%d")
                except Exception:
                    pass

    duplicates_removed = 0
    if deduplicate_columns:
        valid_cols = [c for c in deduplicate_columns if c in df.columns]
        if valid_cols:
            before_d = len(df)
            df = df.drop_duplicates(subset=valid_cols)
            duplicates_removed = before_d - len(df)
    else:
        before_d = len(df)
        df = df.drop_duplicates()
        duplicates_removed = before_d - len(df)

    if fill_nulls is not None:
        df = df.fillna(fill_nulls)

    save_target = output_path or file_path

    try:
        with pd.ExcelWriter(save_target, engine="openpyxl", mode="a", if_sheet_exists="replace") as writer:
            df.to_excel(writer, sheet_name=target_sheet, index=False)
    except Exception:
        try:
            with pd.ExcelWriter(save_target, engine="openpyxl") as writer:
                df.to_excel(writer, sheet_name=target_sheet, index=False)
        except (PermissionError, OSError) as e:
            raise _handle_excel_lock(save_target, e) from e

    return {
        "status": "success",
        "file_path": file_path,
        "saved_path": save_target,
        "sheet_name": target_sheet,
        "initial_rows": initial_rows,
        "final_rows": len(df),
        "duplicates_removed": duplicates_removed,
        "empty_rows_dropped": empty_rows_dropped,
        "empty_columns_dropped": empty_cols_dropped,
    }


@mcp.tool()
def transform_sheet_data(
    file_path: str,
    source_sheet: Optional[str] = None,
    output_sheet: str = "Transformed_Summary",
    group_by: Optional[List[str]] = None,
    aggregations: Optional[Dict[str, str]] = None,
    filter_expr: Optional[str] = None,
    sort_by: Optional[str] = None,
    ascending: bool = True,
    output_path: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Perform advanced Python/Pandas in-memory aggregation and transformation on an Excel sheet
    (similar to Python in Excel =PY()), and write the result into a new or existing sheet tab.

    Parameters:
    - file_path: Path to the .xlsx workbook.
    - source_sheet: Source worksheet name.
    - output_sheet: Destination worksheet tab to write the transformed table to.
    - group_by: Columns to group by (e.g. ['Category', 'Region']).
    - aggregations: Aggregation mapping (e.g. {'Sales': 'sum', 'Quantity': 'mean', 'Order_ID': 'count'}).
    - filter_expr: Optional Pandas query filter (e.g. 'Sales > 500').
    - sort_by: Column to sort final result by.
    - ascending: Sort direction (default True).
    - output_path: Optional output path.

    NOTE: If this file is currently open in Microsoft Excel desktop, saving will fail with
    a locked file error. Ask the user to close the workbook in Excel and retry; do NOT
    attempt terminal workarounds or custom Python scripts.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    wb_meta = openpyxl.load_workbook(file_path, read_only=True)
    target_src = source_sheet if source_sheet and source_sheet in wb_meta.sheetnames else wb_meta.sheetnames[0]
    wb_meta.close()

    df = pd.read_excel(file_path, sheet_name=target_src)
    initial_rows = len(df)

    if filter_expr:
        try:
            df = df.query(filter_expr)
        except Exception as e:
            raise ValueError(f"Invalid filter_expr '{filter_expr}': {e}") from e

    if group_by:
        valid_gb = [c for c in group_by if c in df.columns]
        if valid_gb:
            if aggregations:
                valid_aggs = {k: v for k, v in aggregations.items() if k in df.columns}
                if valid_aggs:
                    df = df.groupby(valid_gb).agg(valid_aggs).reset_index()
                else:
                    df = df.groupby(valid_gb).size().reset_index(name="Count")
            else:
                df = df.groupby(valid_gb).size().reset_index(name="Count")

    if sort_by and sort_by in df.columns:
        df = df.sort_values(by=sort_by, ascending=ascending)

    save_target = output_path or file_path

    try:
        with pd.ExcelWriter(save_target, engine="openpyxl", mode="a", if_sheet_exists="replace") as writer:
            df.to_excel(writer, sheet_name=output_sheet, index=False)
    except Exception:
        try:
            with pd.ExcelWriter(save_target, engine="openpyxl") as writer:
                df.to_excel(writer, sheet_name=output_sheet, index=False)
        except (PermissionError, OSError) as e:
            raise _handle_excel_lock(save_target, e) from e

    return {
        "status": "success",
        "file_path": file_path,
        "saved_path": save_target,
        "source_sheet": target_src,
        "output_sheet": output_sheet,
        "initial_rows": initial_rows,
        "result_rows": len(df),
        "columns": list(df.columns),
    }


@mcp.tool()
def export_to_csv(
    file_path: str,
    output_csv_path: str,
    sheet_name: Optional[str] = None,
    header_row: Optional[int] = None,
    columns: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Export an Excel sheet to a clean CSV file on disk for fast external or Python/SQL processing.
    Avoids consuming any LLM context window tokens while handling massive datasets (10,000+ rows).
    
    Args:
        file_path: Path to the Excel file.
        output_csv_path: Destination path for the CSV.
        sheet_name: Sheet name or index.
        header_row: Row containing column headers (0-indexed, default 0).
        columns: Specific columns to export (default all).
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    out_dir = os.path.dirname(os.path.abspath(output_csv_path))
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    h_idx = header_row if header_row is not None else 0
    df = pd.read_excel(file_path, sheet_name=sheet_name or 0, usecols=columns, header=h_idx)
    df.to_csv(output_csv_path, index=False)

    return {
        "status": "success",
        "input_excel": file_path,
        "output_csv": output_csv_path,
        "rows_exported": len(df),
        "columns_exported": [str(c) for c in df.columns],
        "message": f"Successfully exported {len(df)} rows directly to disk at '{output_csv_path}'.",
    }


@mcp.tool()
def export_to_json(
    file_path: str,
    output_json_path: str,
    sheet_name: Optional[str] = None,
    header_row: Optional[int] = None,
    columns: Optional[List[str]] = None,
    orient: Literal["records", "split", "index", "columns"] = "records",
    indent: Optional[int] = 2,
) -> Dict[str, Any]:
    """
    Export an Excel sheet directly to a JSON file on disk.
    Allows LLMs and scripts to process structured JSON locally without bloating chat context window.
    
    Args:
        file_path: Path to the Excel file.
        output_json_path: Destination path for the exported .json file.
        sheet_name: Sheet name or index (default first sheet).
        header_row: Row containing column headers (0-indexed, default 0).
        columns: Specific column names to export.
        orient: Format of JSON structure ('records', 'split', 'index', or 'columns'). Default 'records'.
        indent: JSON indentation formatting (default 2, None for minified).
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    out_dir = os.path.dirname(os.path.abspath(output_json_path))
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    h_idx = header_row if header_row is not None else 0
    df = pd.read_excel(file_path, sheet_name=sheet_name or 0, usecols=columns, header=h_idx)

    clean_records = _df_to_clean_records(df)
    with open(output_json_path, "w", encoding="utf-8") as f:
        if orient == "records":
            json.dump(clean_records, f, indent=indent)
        else:
            df.to_json(f, orient=orient, indent=indent, date_format="iso")

    file_size_kb = round(os.path.getsize(output_json_path) / 1024, 2)
    return {
        "status": "success",
        "input_excel": file_path,
        "output_json": output_json_path,
        "rows_exported": len(df),
        "columns_exported": [str(c) for c in df.columns],
        "file_size_kb": file_size_kb,
        "orient": orient,
        "message": f"Successfully exported {len(df)} rows directly to '{output_json_path}' ({file_size_kb} KB) with zero token bloat.",
    }


@mcp.tool()
def profile_sheet(
    file_path: str,
    sheet_name: Optional[str] = None,
    header_row: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Generate an instant high-level statistical profile and data quality audit of an entire Excel sheet.
    Provides complete analytics (null rates, unique counts, top frequent values, numeric distributions)
    in a single compact response (~400 tokens) without dumping raw rows into the chat context.
    
    Args:
        file_path: Path to the Excel file.
        sheet_name: Sheet name or index (default first sheet).
        header_row: Row containing column headers (0-indexed, default 0).
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    h_idx = header_row if header_row is not None else 0
    df = pd.read_excel(file_path, sheet_name=sheet_name or 0, header=h_idx)
    total_rows = len(df)
    total_cols = len(df.columns)

    col_profiles = {}
    for col in df.columns:
        series = df[col]
        null_count = int(series.isnull().sum())
        non_null_count = total_rows - null_count
        null_pct = round((null_count / max(total_rows, 1)) * 100, 2)
        unique_count = int(series.nunique())

        profile: Dict[str, Any] = {
            "dtype": str(series.dtype),
            "non_null_count": non_null_count,
            "null_count": null_count,
            "null_pct": null_pct,
            "unique_count": unique_count,
        }

        if pd.api.types.is_numeric_dtype(series):
            valid = series.dropna()
            if len(valid) > 0:
                profile["numeric_stats"] = {
                    "min": float(valid.min()),
                    "max": float(valid.max()),
                    "mean": round(float(valid.mean()), 2),
                    "sum": round(float(valid.sum()), 2),
                }
        else:
            top_vals = series.dropna().value_counts().head(5).to_dict()
            profile["top_frequent"] = {str(k)[:40]: int(v) for k, v in top_vals.items()}

        col_profiles[str(col)] = profile

    return {
        "file_path": file_path,
        "sheet_name": sheet_name or "First Sheet",
        "total_rows": total_rows,
        "total_columns": total_cols,
        "columns": [str(c) for c in df.columns],
        "column_profiles": col_profiles,
    }


@mcp.tool()
def query_excel_sql(
    file_path: str,
    sql_query: str,
    sheet_name: Optional[str] = None,
    header_row: Optional[int] = None,
    limit: int = 50,
    format: Literal["records", "compact", "tsv"] = "records",
) -> Dict[str, Any]:
    """
    Execute arbitrary SQL queries (GROUP BY, JOIN, AGGREGATE, WHERE, HAVING, ORDER BY)
    directly on an Excel sheet using an in-memory SQL engine (SQLite).
    Allows powerful analytics, deduplication, and filtering on the server with minimal token consumption!
    The Excel table is exposed as 'sheet' (and 'data'). Column names are sanitized to valid SQL identifiers (spaces -> underscores).
    
    Args:
        file_path: Path to the Excel file.
        sql_query: SQL query to execute (e.g. "SELECT prefix, COUNT(*), MAX(code) FROM sheet GROUP BY prefix").
        sheet_name: Sheet name or index (default first sheet).
        header_row: Row containing headers (0-indexed, default 0).
        limit: Max rows to return (default 50, max 100 for records, 200 for compact, 300 for tsv).
        format: Output format ('records', 'compact', or 'tsv').
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    h_idx = header_row if header_row is not None else 0
    df = pd.read_excel(file_path, sheet_name=sheet_name or 0, header=h_idx)

    # Sanitize column names for SQLite
    sanitized_map = {}
    for col in df.columns:
        s = re.sub(r"\W+", "_", str(col)).strip("_")
        sanitized_map[col] = s or "col"

    df_sql = df.rename(columns=sanitized_map)

    conn = sqlite3.connect(":memory:")
    try:
        df_sql.to_sql("sheet", conn, index=False)
        df_sql.to_sql("data", conn, index=False)

        # Safety caps
        max_allowed = 300 if format == "tsv" else (200 if format == "compact" else 100)
        safe_limit = max(1, min(limit, max_allowed))

        # Check if query already has a LIMIT
        q_clean = sql_query.strip().rstrip(";")
        if "limit " not in q_clean.lower():
            exec_query = f"{q_clean} LIMIT {safe_limit + 1}"
        else:
            exec_query = q_clean

        cur = conn.cursor()
        cur.execute(exec_query)
        col_names = [d[0] for d in cur.description] if cur.description else []
        rows = cur.fetchall()

        has_more = len(rows) > safe_limit
        display_rows = rows[:safe_limit]

        df_res = pd.DataFrame(display_rows, columns=col_names)
        data = _format_dataframe_output(df_res, format)

        result: Dict[str, Any] = {
            "sql_query": sql_query,
            "total_returned": len(display_rows),
            "columns": col_names,
            "available_table_columns": list(sanitized_map.values()),
            "format": format,
            "rows": data if format != "tsv" else None,
            "data": data,
        }

        if has_more:
            result["notice"] = (
                f"Showing first {safe_limit} rows. Additional rows omitted to protect LLM context window. "
                f"Use SQL WHERE or specific aggregations to narrow results."
            )

        return result
    except Exception as e:
        raise ValueError(f"SQL execution error: {str(e)}. Table columns available: {list(sanitized_map.values())}")
    finally:
        conn.close()


@mcp.tool()
def export_transformed_workbook(
    source_path: str,
    destination_path: str,
    source_sheet: Optional[Union[str, int]] = None,
    destination_sheet: str = "Sheet1",
    sql_query: Optional[str] = None,
    column_mappings: Optional[Dict[str, str]] = None,
    computed_columns: Optional[Dict[str, str]] = None,
    drop_columns: Optional[List[str]] = None,
    filter_query: Optional[str] = None,
    deduplicate_on: Optional[List[str]] = None,
    sort_by: Optional[Union[str, List[str]]] = None,
    sort_ascending: bool = True,
    format_headers: bool = True,
    header_fill_color: str = "1F497D",
    header_font_color: str = "FFFFFF",
    auto_fit_columns: bool = True,
    freeze_header: bool = True,
) -> Dict[str, Any]:
    """
    Perform high-speed in-memory pipeline transformations and export directly to a new Excel/CSV file on disk.
    Processes tens of thousands of rows (e.g. 5,000+ rows × 15 columns) in < 1 second with 0 context window bloat!

    Transformation Pipeline Order:
    1. Reads source file (.xlsx, .xls, .xlsm, .csv) into Pandas.
    2. Optional Pandas Filter Query: Filter rows using expression (e.g. "Price > 0 and Status == 'Active'").
    3. Optional SQL Query: Execute full SQLite query on in-memory table `source` (also aliased as `sheet`, `df`, `data`).
       Example: "SELECT SKU, Category, Price * 1.18 AS Price_With_Tax, UPPER(Status) AS Status FROM source WHERE Status != 'Discontinued'"
    4. Optional Computed Columns: Add computed columns via eval expressions or constant literals (e.g. {"Margin": "Price - Cost", "Source": "'ERP'"}).
    5. Optional Column Renaming: Rename columns via column_mappings dict (e.g. {"OldCol": "NewCol"}).
    6. Optional Drop Columns: Remove unwanted columns with drop_columns=["Temp_Col", "Notes"].
    7. Optional Deduplication: Drop duplicate rows on deduplicate_on=["SKU"].
    8. Optional Sorting: Sort by sort_by="Category" or sort_by=["Category", "Price"].
    9. Direct Disk Export: Writes directly to destination_path (.xlsx or .csv) with optional auto-fitted column widths, freeze pane, and styled headers.

    Parameters:
    - source_path: Path to source Excel (.xlsx, .xls, .xlsm) or CSV file.
    - destination_path: Destination path for the transformed workbook (.xlsx or .csv).
    - source_sheet: Sheet name or 0-indexed integer in source file.
    - destination_sheet: Sheet tab name in target workbook (default 'Sheet1').
    - sql_query: Optional SQL query executed on in-memory table `source`.
    - column_mappings: Optional dict to rename columns, e.g. {"old_col": "New Col"}.
    - computed_columns: Optional dict of pandas eval expressions or constant values.
    - drop_columns: Optional list of columns to remove.
    - filter_query: Optional Pandas filter query expression (e.g. "Price > 0 and Status == 'Active'").
    - deduplicate_on: Optional list of column names to deduplicate by.
    - sort_by: Column or list of columns to sort by.
    - sort_ascending: Sort direction (default True).
    - format_headers: Apply professional styling to header row (default True).
    - header_fill_color: Hex color for header background fill (default '1F497D' navy).
    - header_font_color: Hex color for header text (default 'FFFFFF' white).
    - auto_fit_columns: Automatically calculate and set column widths (default True).
    - freeze_header: Freeze top header row for smooth scrolling (default True).
    """
    if not os.path.exists(source_path):
        raise FileNotFoundError(f"Source file not found: {source_path}")

    dest_dir = os.path.dirname(os.path.abspath(destination_path))
    if dest_dir:
        os.makedirs(dest_dir, exist_ok=True)

    # 1. Read source
    if source_path.lower().endswith(".csv"):
        df = pd.read_csv(source_path)
    else:
        df = pd.read_excel(source_path, sheet_name=source_sheet if source_sheet is not None else 0)

    initial_rows = len(df)
    initial_cols = len(df.columns)

    # 2. Filter query
    if filter_query:
        try:
            df = df.query(filter_query)
        except Exception as e:
            raise ValueError(f"Filter query error: {str(e)}")

    # 3. SQL Query
    if sql_query:
        conn = sqlite3.connect(":memory:")
        try:
            sanitized_map = {}
            for col in df.columns:
                s = re.sub(r"\W+", "_", str(col)).strip("_")
                sanitized_map[col] = s or "col"
            df_sql = df.rename(columns=sanitized_map)
            df_sql.to_sql("source", conn, index=False, if_exists="replace")
            df_sql.to_sql("sheet", conn, index=False, if_exists="replace")
            df_sql.to_sql("df", conn, index=False, if_exists="replace")
            df_sql.to_sql("data", conn, index=False, if_exists="replace")

            df = pd.read_sql_query(sql_query, conn)
        except Exception as e:
            raise ValueError(f"SQL transformation error: {str(e)}")
        finally:
            conn.close()

    # 4. Computed columns
    if computed_columns:
        for col_name, expr in computed_columns.items():
            if not isinstance(expr, str):
                df[col_name] = expr
                continue
            expr_str = expr.strip()
            if (expr_str.startswith("'") and expr_str.endswith("'")) or (expr_str.startswith('"') and expr_str.endswith('"')):
                df[col_name] = expr_str[1:-1]
            else:
                try:
                    df[col_name] = df.eval(expr_str)
                except Exception:
                    df[col_name] = expr_str

    # 5. Column mappings (rename)
    if column_mappings:
        df = df.rename(columns=column_mappings)

    # 6. Drop columns
    if drop_columns:
        cols_to_drop = [c for c in drop_columns if c in df.columns]
        if cols_to_drop:
            df = df.drop(columns=cols_to_drop)

    # 7. Deduplicate
    if deduplicate_on:
        dedup_cols = [c for c in deduplicate_on if c in df.columns]
        if dedup_cols:
            df = df.drop_duplicates(subset=dedup_cols)

    # 8. Sort
    if sort_by:
        sort_cols = [sort_by] if isinstance(sort_by, str) else list(sort_by)
        valid_sort_cols = [c for c in sort_cols if c in df.columns]
        if valid_sort_cols:
            df = df.sort_values(by=valid_sort_cols, ascending=sort_ascending)

    # 9. Direct Export
    exported_rows = len(df)
    exported_cols = [str(c) for c in df.columns]

    is_csv_dest = destination_path.lower().endswith(".csv")

    if is_csv_dest:
        df.to_csv(destination_path, index=False)
    else:
        try:
            with pd.ExcelWriter(destination_path, engine="openpyxl") as writer:
                df.to_excel(writer, sheet_name=destination_sheet or "Sheet1", index=False)

            if format_headers or auto_fit_columns or freeze_header:
                wb = openpyxl.load_workbook(destination_path)
                ws = wb[destination_sheet] if destination_sheet in wb.sheetnames else wb.active

                if freeze_header:
                    ws.freeze_panes = "A2"

                # Style headers
                if format_headers:
                    norm_fill = _normalize_hex_color(header_fill_color) or "1F497D"
                    norm_font = _normalize_hex_color(header_font_color) or "FFFFFF"
                    header_fill = PatternFill(start_color=norm_fill, end_color=norm_fill, fill_type="solid")
                    header_font = Font(name="Calibri", size=11, bold=True, color=norm_font)
                    header_align = Alignment(horizontal="center", vertical="center", wrap_text=True)

                    for col_idx in range(1, len(exported_cols) + 1):
                        cell = ws.cell(row=1, column=col_idx)
                        cell.fill = header_fill
                        cell.font = header_font
                        cell.alignment = header_align

                # Auto-fit column widths
                if auto_fit_columns:
                    for col_idx, col_name in enumerate(exported_cols, start=1):
                        col_letter = get_column_letter(col_idx)
                        max_len = len(str(col_name))
                        sample_vals = df[col_name].dropna().head(50).astype(str).tolist() if col_name in df.columns else []
                        if sample_vals:
                            sample_max = max(len(v) for v in sample_vals)
                            max_len = max(max_len, sample_max)
                        ws.column_dimensions[col_letter].width = max(min(max_len + 4, 60), 10)

                _safe_save_workbook(wb, destination_path)
                wb.close()
        except Exception as e:
            raise ValueError(f"Failed writing destination Excel workbook: {str(e)}")

    file_size_bytes = os.path.getsize(destination_path) if os.path.exists(destination_path) else 0

    return {
        "status": "success",
        "source_path": source_path,
        "destination_path": destination_path,
        "destination_sheet": destination_sheet if not is_csv_dest else "N/A",
        "initial_rows": initial_rows,
        "initial_columns": initial_cols,
        "exported_rows": exported_rows,
        "exported_columns_count": len(exported_cols),
        "exported_columns": exported_cols,
        "file_size_bytes": file_size_bytes,
        "file_size_kb": round(file_size_bytes / 1024, 2),
        "sample_preview": _df_to_clean_records(df.head(3)),
    }


# ==========================================================
# 2. MULTI-KEY RECONCILIATION & DISCREPANCY ANALYSIS TOOLS
# ==========================================================

@mcp.tool()
def analyze_reconciliation_keys(
    file_path_1: str,
    file_path_2: str,
    join_keys: Union[List[str], Dict[str, str]],
    sheet_1: Optional[str] = None,
    sheet_2: Optional[str] = None,
    sample_size: Optional[int] = 10000,
) -> Dict[str, Any]:
    """
    Pre-flight diagnostic analysis BEFORE running reconciliation.
    Evaluates key compatibility, nulls, duplicates, data types, exact match rates,
    and fuzzy matching potential without modifying any files.
    """
    if not os.path.exists(file_path_1):
        raise FileNotFoundError(f"File 1 not found: {file_path_1}")
    if not os.path.exists(file_path_2):
        raise FileNotFoundError(f"File 2 not found: {file_path_2}")

    if isinstance(join_keys, list):
        key_map = {k: k for k in join_keys}
    elif isinstance(join_keys, dict):
        key_map = join_keys
    else:
        raise ValueError("join_keys must be a list of column names or a dictionary mapping {col_f1: col_f2}")

    f1_keys = list(key_map.keys())
    f2_keys = list(key_map.values())

    df1 = pd.read_excel(file_path_1, sheet_name=sheet_1 or 0, nrows=sample_size)
    df2 = pd.read_excel(file_path_2, sheet_name=sheet_2 or 0, nrows=sample_size)

    missing_in_f1 = [k for k in f1_keys if k not in df1.columns]
    missing_in_f2 = [k for k in f2_keys if k not in df2.columns]
    if missing_in_f1 or missing_in_f2:
        return {
            "valid": False,
            "error": f"Missing key columns. In File 1 missing: {missing_in_f1}. In File 2 missing: {missing_in_f2}",
        }

    total_f1 = len(df1)
    total_f2 = len(df2)

    f1_nulls = int(df1[f1_keys].isnull().any(axis=1).sum())
    f2_nulls = int(df2[f2_keys].isnull().any(axis=1).sum())

    f1_dupes = int(df1.duplicated(subset=f1_keys).sum())
    f2_dupes = int(df2.duplicated(subset=f2_keys).sum())

    dtype_mismatches = []
    for k1, k2 in key_map.items():
        dt1 = str(df1[k1].dtype)
        dt2 = str(df2[k2].dtype)
        if dt1 != dt2:
            dtype_mismatches.append({"key_file1": k1, "dtype_file1": dt1, "key_file2": k2, "dtype_file2": dt2})

    def make_raw_key(df, cols):
        return df[cols].astype(str).agg("___".join, axis=1)

    def make_clean_key(df, cols):
        return df[cols].astype(str).map(lambda v: v.strip().lower()).agg("___".join, axis=1)

    s1_raw = set(make_raw_key(df1, f1_keys))
    s2_raw = set(make_raw_key(df2, f2_keys))
    raw_matches = len(s1_raw.intersection(s2_raw))

    s1_clean = set(make_clean_key(df1, f1_keys))
    s2_clean = set(make_clean_key(df2, f2_keys))
    clean_matches = len(s1_clean.intersection(s2_clean))

    raw_match_rate = round((raw_matches / max(len(s1_raw), 1)) * 100, 2)
    clean_match_rate = round((clean_matches / max(len(s1_clean), 1)) * 100, 2)

    unmatched_f1 = list(s1_clean - s2_clean)[:50]
    unmatched_f2 = list(s2_clean - s1_clean)[:50]

    potential_fuzzy = 0
    fuzzy_samples = []
    if HAS_RAPIDFUZZ and unmatched_f1 and unmatched_f2:
        for u1 in unmatched_f1:
            best_score = 0
            best_match = None
            for u2 in unmatched_f2:
                sc = fuzz.token_sort_ratio(u1, u2)
                if sc > best_score:
                    best_score = sc
                    best_match = u2
            if best_score >= 80:
                potential_fuzzy += 1
                if len(fuzzy_samples) < 5:
                    fuzzy_samples.append({
                        "key_file1": u1.replace("___", " | "),
                        "key_file2": best_match.replace("___", " | ") if best_match else "",
                        "similarity_%": round(best_score, 1)
                    })

    recommendations = []
    if f1_dupes > 0 or f2_dupes > 0:
        recommendations.append(f"Duplicate keys found (File 1: {f1_dupes}, File 2: {f2_dupes}). Many-to-many matching might expand row count.")
    if clean_match_rate > raw_match_rate:
        diff_gain = round(clean_match_rate - raw_match_rate, 1)
        recommendations.append(f"Whitespace & case normalization increases match rate by +{diff_gain}%. Enabled by default.")
    if dtype_mismatches:
        recommendations.append("Key data types differ between files (e.g. integer vs text). Auto-string conversion recommended.")
    if potential_fuzzy > 0:
        recommendations.append(f"Detected {potential_fuzzy} additional candidates matchable via Fuzzy Matching (>=80% similarity).")

    return {
        "valid": True,
        "file1": {"path": file_path_1, "rows_inspected": total_f1, "null_keys": f1_nulls, "duplicate_keys": f1_dupes},
        "file2": {"path": file_path_2, "rows_inspected": total_f2, "null_keys": f2_nulls, "duplicate_keys": f2_dupes},
        "join_keys": key_map,
        "match_rates": {
            "raw_exact_match_pct": raw_match_rate,
            "sanitized_match_pct": clean_match_rate,
            "fuzzy_match_candidates": potential_fuzzy,
        },
        "dtype_mismatches": dtype_mismatches,
        "fuzzy_sample_candidates": fuzzy_samples,
        "sample_unmatched_file1": [k.replace("___", " | ") for k in unmatched_f1[:5]],
        "sample_unmatched_file2": [k.replace("___", " | ") for k in unmatched_f2[:5]],
        "recommendations": recommendations,
    }


@mcp.tool()
def reconcile_and_merge(
    file_path_1: str,
    file_path_2: str,
    join_keys: Union[List[str], Dict[str, str]],
    output_file_path: str,
    sheet_1: Optional[str] = None,
    sheet_2: Optional[str] = None,
    compare_columns: Optional[Union[List[str], Dict[str, str]]] = None,
    numeric_tolerance: float = 0.01,
    enable_fuzzy: bool = True,
    fuzzy_threshold: int = 85,
) -> Dict[str, Any]:
    """
    Multi-Key Reconciliation & Discrepancy Matching between two Excel workbooks.
    Matches records across 2 or 3 related columns, computes variances on compared columns,
    performs fuzzy matching for unmatched keys, and saves a 3-tab audit workbook.
    """
    if not os.path.exists(file_path_1):
        raise FileNotFoundError(f"File 1 not found: {file_path_1}")
    if not os.path.exists(file_path_2):
        raise FileNotFoundError(f"File 2 not found: {file_path_2}")

    if isinstance(join_keys, list):
        key_map = {k: k for k in join_keys}
    else:
        key_map = join_keys

    f1_keys = list(key_map.keys())
    f2_keys = list(key_map.values())

    df1 = pd.read_excel(file_path_1, sheet_name=sheet_1 or 0)
    df2 = pd.read_excel(file_path_2, sheet_name=sheet_2 or 0)

    comp_map = {}
    if compare_columns:
        if isinstance(compare_columns, list):
            comp_map = {c: c for c in compare_columns}
        elif isinstance(compare_columns, dict):
            comp_map = compare_columns

    def make_normalized_key(df, cols):
        return df[cols].astype(str).map(lambda v: v.strip().lower()).agg("___".join, axis=1)

    df1["_NORM_KEY_"] = make_normalized_key(df1, f1_keys)
    df2["_NORM_KEY_"] = make_normalized_key(df2, f2_keys)

    merged = pd.merge(
        df1,
        df2,
        on="_NORM_KEY_",
        how="outer",
        suffixes=("_FILE1", "_FILE2"),
        indicator=True
    )

    reconciled_rows = []
    unmatched_f1_rows = []
    unmatched_f2_rows = []
    fuzzy_matched_rows = []

    for _, row in merged.iterrows():
        status = row["_merge"]
        if status == "both":
            row_dict = row.drop(["_merge", "_NORM_KEY_"]).to_dict()
            variance_flags = []
            has_variance = False

            for c1, c2 in comp_map.items():
                c1_col = f"{c1}_FILE1" if f"{c1}_FILE1" in row_dict else c1
                c2_col = f"{c2}_FILE2" if f"{c2}_FILE2" in row_dict else c2
                v1 = row_dict.get(c1_col)
                v2 = row_dict.get(c2_col)
                try:
                    num1 = float(v1)
                    num2 = float(v2)
                    diff = round(num1 - num2, 4)
                    row_dict[f"DIFF_{c1}"] = diff
                    if abs(diff) > numeric_tolerance:
                        has_variance = True
                        variance_flags.append(f"{c1} diff: {diff}")
                except (ValueError, TypeError):
                    if str(v1).strip().lower() != str(v2).strip().lower():
                        has_variance = True
                        row_dict[f"DIFF_{c1}"] = f"Mismatch: '{v1}' != '{v2}'"
                        variance_flags.append(f"{c1} mismatch")

            row_dict["RECONCILE_STATUS"] = "VARIANCE_DETECTED" if has_variance else "EXACT_MATCH"
            row_dict["VARIANCE_DETAILS"] = "; ".join(variance_flags) if variance_flags else "None"
            reconciled_rows.append(row_dict)

        elif status == "left_only":
            row_dict = row.drop(["_merge"]).to_dict()
            clean_dict = {k.replace("_FILE1", ""): v for k, v in row_dict.items() if not k.endswith("_FILE2")}
            clean_dict["SOURCE"] = "ONLY_IN_FILE_1"
            unmatched_f1_rows.append(clean_dict)

        elif status == "right_only":
            row_dict = row.drop(["_merge"]).to_dict()
            clean_dict = {k.replace("_FILE2", ""): v for k, v in row_dict.items() if not k.endswith("_FILE1")}
            clean_dict["SOURCE"] = "ONLY_IN_FILE_2"
            unmatched_f2_rows.append(clean_dict)

    # Fuzzy Matching on remaining unmatched
    if enable_fuzzy and HAS_RAPIDFUZZ and unmatched_f1_rows and unmatched_f2_rows:
        still_unmatched_f1 = []
        matched_f2_indices = set()

        for r1 in unmatched_f1_rows:
            key1 = str(r1.get("_NORM_KEY_", ""))
            best_score = 0
            best_r2 = None
            best_idx = -1

            for idx2, r2 in enumerate(unmatched_f2_rows):
                if idx2 in matched_f2_indices:
                    continue
                key2 = str(r2.get("_NORM_KEY_", ""))
                score = fuzz.token_sort_ratio(key1, key2)
                if score > best_score:
                    best_score = score
                    best_r2 = r2
                    best_idx = idx2

            if best_score >= fuzzy_threshold and best_r2:
                matched_f2_indices.add(best_idx)
                fuzzy_entry = {
                    "KEY_FILE_1": key1.replace("___", " | "),
                    "KEY_FILE_2": str(best_r2.get("_NORM_KEY_", "")).replace("___", " | "),
                    "CONFIDENCE_SCORE_%": round(best_score, 1),
                }
                for k, v in r1.items():
                    if k not in ("_NORM_KEY_", "SOURCE"):
                        fuzzy_entry[f"{k}_FILE1"] = v
                for k, v in best_r2.items():
                    if k not in ("_NORM_KEY_", "SOURCE"):
                        fuzzy_entry[f"{k}_FILE2"] = v
                fuzzy_matched_rows.append(fuzzy_entry)
            else:
                r1.pop("_NORM_KEY_", None)
                still_unmatched_f1.append(r1)

        unmatched_f1_rows = still_unmatched_f1
        unmatched_f2_rows = [r for idx, r in enumerate(unmatched_f2_rows) if idx not in matched_f2_indices]
        for r in unmatched_f2_rows:
            r.pop("_NORM_KEY_", None)

    # Save to Excel with 3 dedicated sheets
    df_reconciled = pd.DataFrame(reconciled_rows) if reconciled_rows else pd.DataFrame([{"Message": "No exact matches found"}])
    df_fuzzy = pd.DataFrame(fuzzy_matched_rows) if fuzzy_matched_rows else pd.DataFrame([{"Message": "No fuzzy matches found"}])
    
    all_unmatched = []
    for r in unmatched_f1_rows:
        all_unmatched.append(r)
    for r in unmatched_f2_rows:
        all_unmatched.append(r)
    df_unmatched = pd.DataFrame(all_unmatched) if all_unmatched else pd.DataFrame([{"Message": "No unmatched exceptions"}])

    out_dir = os.path.dirname(os.path.abspath(output_file_path))
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    try:
        with pd.ExcelWriter(output_file_path, engine="openpyxl") as writer:
            df_reconciled.to_excel(writer, sheet_name="1_Reconciled_Matches", index=False)
            df_fuzzy.to_excel(writer, sheet_name="2_Probable_Fuzzy_Matches", index=False)
            df_unmatched.to_excel(writer, sheet_name="3_Unmatched_Exceptions", index=False)

            for sname in ["1_Reconciled_Matches", "2_Probable_Fuzzy_Matches", "3_Unmatched_Exceptions"]:
                ws = writer.sheets[sname]
                for col in ws.columns:
                    max_len = max(len(str(cell.value or "")) for cell in col)
                    col_letter = openpyxl.utils.get_column_letter(col[0].column)
                    ws.column_dimensions[col_letter].width = min(max(max_len + 3, 10), 45)
    except (PermissionError, OSError) as e:
        raise _handle_excel_lock(output_file_path, e) from e

    return {
        "status": "success",
        "output_file": output_file_path,
        "summary": {
            "total_file1_records": len(df1),
            "total_file2_records": len(df2),
            "exact_matched_records": len(reconciled_rows),
            "fuzzy_matched_candidates": len(fuzzy_matched_rows),
            "unmatched_file1_only": len(unmatched_f1_rows),
            "unmatched_file2_only": len(unmatched_f2_rows),
        },
        "sheets_created": ["1_Reconciled_Matches", "2_Probable_Fuzzy_Matches", "3_Unmatched_Exceptions"],
    }


# ==========================================================
# 3. NATIVE MICROSOFT EXCEL WINDOWS AUTOMATION (COM / PyWin32)
# ==========================================================

def _get_abs_path(path: str) -> str:
    return os.path.abspath(os.path.expanduser(path))


@mcp.tool()
def recalculate_and_save(file_path: str) -> Dict[str, Any]:
    """
    [Windows Native Excel] Open workbook in background Microsoft Excel,
    run full formula recalculation (Application.CalculateFull()), save, and close.
    Ensures all dynamic formulas (XLOOKUP, INDEX/MATCH, SUMIFS) are evaluated.
    """
    if not HAS_WIN32:
        raise RuntimeError("PyWin32 is not installed or Windows COM is unavailable.")

    abs_path = _get_abs_path(file_path)
    if not os.path.exists(abs_path):
        raise FileNotFoundError(f"File not found: {abs_path}")

    pythoncom.CoInitialize()
    excel = None
    wb = None
    try:
        excel = win32com.client.DispatchEx("Excel.Application")
        excel.Visible = False
        excel.DisplayAlerts = False
        try:
            wb = excel.Workbooks.Open(abs_path)
            excel.CalculateFull()
            wb.Save()
            wb.Close()
            wb = None
        except Exception as e:
            raise _handle_excel_lock(abs_path, e) from e
        return {
            "status": "success",
            "message": "Workbook formulas recalculated and saved using native Microsoft Excel.",
            "file_path": abs_path,
        }
    finally:
        if wb:
            try:
                wb.Close(False)
            except Exception:
                pass
        if excel:
            try:
                excel.Quit()
            except Exception:
                pass
        pythoncom.CoUninitialize()


@mcp.tool()
def export_to_pdf(
    file_path: str,
    output_pdf_path: str,
    sheet_name: Optional[str] = None,
) -> Dict[str, Any]:
    """
    [Windows Native Excel] Export a sheet or entire workbook to a pixel-perfect PDF
    using Microsoft Excel's native print engine.
    """
    if not HAS_WIN32:
        raise RuntimeError("PyWin32 is not installed or Windows COM is unavailable.")

    abs_input = _get_abs_path(file_path)
    abs_output = _get_abs_path(output_pdf_path)

    if not os.path.exists(abs_input):
        raise FileNotFoundError(f"Input file not found: {abs_input}")

    out_dir = os.path.dirname(abs_output)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    pythoncom.CoInitialize()
    excel = None
    wb = None
    try:
        excel = win32com.client.DispatchEx("Excel.Application")
        excel.Visible = False
        excel.DisplayAlerts = False
        wb = excel.Workbooks.Open(abs_input)
        # xlTypePDF = 0
        if sheet_name and sheet_name in [s.Name for s in wb.Sheets]:
            ws = wb.Sheets(sheet_name)
            ws.ExportAsFixedFormat(0, abs_output)
        else:
            wb.ExportAsFixedFormat(0, abs_output)

        wb.Close(False)
        wb = None
        return {
            "status": "success",
            "message": f"Successfully exported to PDF: {abs_output}",
            "pdf_path": abs_output,
        }
    finally:
        if wb:
            try:
                wb.Close(False)
            except Exception:
                pass
        if excel:
            try:
                excel.Quit()
            except Exception:
                pass
        pythoncom.CoUninitialize()


@mcp.tool()
def refresh_data_and_pivots(file_path: str) -> Dict[str, Any]:
    """
    [Windows Native Excel] Refreshes all external data connections, Power Queries,
    and PivotTables in the workbook using native Excel.
    """
    if not HAS_WIN32:
        raise RuntimeError("PyWin32 is not installed or Windows COM is unavailable.")

    abs_path = _get_abs_path(file_path)
    if not os.path.exists(abs_path):
        raise FileNotFoundError(f"File not found: {abs_path}")

    pythoncom.CoInitialize()
    excel = None
    wb = None
    try:
        excel = win32com.client.DispatchEx("Excel.Application")
        excel.Visible = False
        excel.DisplayAlerts = False
        try:
            wb = excel.Workbooks.Open(abs_path)
            wb.RefreshAll()
            excel.CalculateUntilAsyncQueriesDone()
            wb.Save()
            wb.Close()
            wb = None
        except Exception as e:
            raise _handle_excel_lock(abs_path, e) from e
        return {
            "status": "success",
            "message": "All data connections and PivotTables refreshed successfully.",
            "file_path": abs_path,
        }
    finally:
        if wb:
            try:
                wb.Close(False)
            except Exception:
                pass
        if excel:
            try:
                excel.Quit()
            except Exception:
                pass
        pythoncom.CoUninitialize()



@mcp.tool()
def run_vba_macro(
    file_path: str,
    macro_name: str,
    args: Optional[List[Any]] = None,
) -> Dict[str, Any]:
    """
    [Windows Native Excel] Run a VBA Macro in an Excel workbook (.xlsm or .xlsb).
    """
    if not HAS_WIN32:
        raise RuntimeError("PyWin32 is not installed or Windows COM is unavailable.")

    abs_path = _get_abs_path(file_path)
    if not os.path.exists(abs_path):
        raise FileNotFoundError(f"File not found: {abs_path}")

    pythoncom.CoInitialize()
    excel = None
    wb = None
    try:
        excel = win32com.client.DispatchEx("Excel.Application")
        excel.Visible = False
        excel.DisplayAlerts = False
        try:
            wb = excel.Workbooks.Open(abs_path)
            macro_args = args or []
            macro_res = excel.Application.Run(macro_name, *macro_args)
            wb.Save()
            wb.Close()
            wb = None
        except Exception as e:
            raise _handle_excel_lock(abs_path, e) from e
        return {
            "status": "success",
            "macro_name": macro_name,
            "macro_result": str(macro_res) if macro_res is not None else None,
        }
    finally:
        if wb:
            try:
                wb.Close(False)
            except Exception:
                pass
        if excel:
            try:
                excel.Quit()
            except Exception:
                pass
        pythoncom.CoUninitialize()



@mcp.tool()
def get_active_excel_window() -> Dict[str, Any]:
    """
    [Windows Native Excel] Check if Microsoft Excel is currently open on the user's
    desktop. If open, returns the active workbook name, active sheet, and selected range.
    """
    if not HAS_WIN32:
        raise RuntimeError("PyWin32 is not installed or Windows COM is unavailable.")

    pythoncom.CoInitialize()
    try:
        # Use Dispatch (not DispatchEx) to bind to running desktop instance
        excel = win32com.client.GetActiveObject("Excel.Application")
        wb = excel.ActiveWorkbook
        ws = excel.ActiveSheet
        sel = excel.Selection

        return {
            "excel_running": True,
            "active_workbook": wb.Name if wb else None,
            "active_workbook_path": wb.FullName if wb else None,
            "active_sheet": ws.Name if ws else None,
            "active_selection": sel.Address if sel else None,
        }
    except Exception:
        return {
            "excel_running": False,
            "message": "No active Excel window currently running on desktop.",
        }
    finally:
        pythoncom.CoUninitialize()


# ==========================================================
# 5. ADVANCED EXCEL AUDITING & MODIFICATION TOOLS
# ==========================================================

@mcp.tool()
def audit_formulas(
    file_path: str,
    sheet_name: Optional[str] = None,
    max_errors: int = 50,
) -> Dict[str, Any]:
    """
    Audit an Excel workbook for broken formulas, cell error values, and reference faults (#REF!, #VALUE!, #N/A, #DIV/0!, #NAME?, #NUM!, #NULL!).
    
    Args:
        file_path: Path to the Excel file.
        sheet_name: Optional sheet name to inspect. If omitted, checks all sheets.
        max_errors: Maximum error instances to return (default 50, max 200).
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    safe_max = min(max(1, max_errors), 200)
    error_tokens = {"#REF!", "#VALUE!", "#N/A", "#DIV/0!", "#NAME?", "#NUM!", "#NULL!"}

    wb_formulas = openpyxl.load_workbook(file_path, data_only=False)
    try:
        wb_values = openpyxl.load_workbook(file_path, data_only=True)
    except Exception:
        wb_values = None

    sheets_to_check = [sheet_name] if sheet_name and sheet_name in wb_formulas.sheetnames else wb_formulas.sheetnames
    errors_found = []
    total_formulas_checked = 0

    for s_name in sheets_to_check:
        ws_f = wb_formulas[s_name]
        ws_v = wb_values[s_name] if wb_values and s_name in wb_values.sheetnames else None

        for row in ws_f.iter_rows():
            for cell in row:
                f_val = cell.value
                if f_val is None:
                    continue

                f_str = str(f_val).strip()
                is_formula = f_str.startswith("=")
                if is_formula:
                    total_formulas_checked += 1

                # Check 1: Explicit error in formula itself (e.g. =SUM(#REF!))
                found_error_type = None
                for err in error_tokens:
                    if err in f_str:
                        found_error_type = err
                        break

                # Check 2: Evaluated value in data_only workbook is an error
                if not found_error_type and ws_v:
                    try:
                        v_cell = ws_v[cell.coordinate]
                        v_str = str(v_cell.value).strip() if v_cell.value is not None else ""
                        if v_str in error_tokens:
                            found_error_type = v_str
                    except Exception:
                        pass

                if found_error_type:
                    errors_found.append({
                        "sheet": s_name,
                        "cell": cell.coordinate,
                        "formula": f_str,
                        "error_type": found_error_type,
                    })
                    if len(errors_found) >= safe_max:
                        break
            if len(errors_found) >= safe_max:
                break
        if len(errors_found) >= safe_max:
            break

    wb_formulas.close()
    if wb_values:
        wb_values.close()

    res: Dict[str, Any] = {
        "file_path": file_path,
        "sheets_audited": sheets_to_check,
        "total_formulas_checked": total_formulas_checked,
        "total_errors_found": len(errors_found),
        "limit_reached": len(errors_found) >= safe_max,
        "errors": errors_found,
    }
    if len(errors_found) >= safe_max:
        res["notice"] = f"... [TRUNCATED: Showing first {safe_max} errors. Increase max_errors to see more] ..."
    return res


@mcp.tool()
def search_and_replace_cells(
    file_path: str,
    search_val: str,
    replace_val: str,
    sheet_name: Optional[str] = None,
    match_case: bool = False,
    exact_match: bool = False,
    dry_run: bool = True,
    output_path: Optional[str] = None,
    max_replacements: int = 500,
) -> Dict[str, Any]:
    """
    Search and replace text within spreadsheet cells.
    Defaults to dry_run=True to preview changes safely before modifying files.
    
    Args:
        file_path: Path to the target Excel file.
        search_val: String to search for.
        replace_val: String to replace with.
        sheet_name: Sheet name to target (default: all sheets).
        match_case: Case-sensitive matching (default False).
        exact_match: Match entire cell text instead of substring (default False).
        dry_run: If True, previews changes without saving to disk (default True).
        output_path: Optional path to save modified file. If omitted and dry_run=False, updates original file.
        max_replacements: Safety cap on replacements (default 500).
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    wb = openpyxl.load_workbook(file_path, data_only=False)
    sheets_to_process = [sheet_name] if sheet_name and sheet_name in wb.sheetnames else wb.sheetnames

    replacements = []
    flags = 0 if match_case else re.IGNORECASE
    pattern = re.compile(re.escape(search_val), flags)

    for s_name in sheets_to_process:
        ws = wb[s_name]
        for row in ws.iter_rows():
            for cell in row:
                if cell.value is None or not isinstance(cell.value, str):
                    continue

                orig_val = cell.value
                # Do not replace inside formula expressions unless requested
                if orig_val.startswith("="):
                    continue

                matched = False
                new_val = orig_val

                if exact_match:
                    if (orig_val == search_val) if match_case else (orig_val.lower() == search_val.lower()):
                        matched = True
                        new_val = replace_val
                else:
                    if pattern.search(orig_val):
                        matched = True
                        new_val = pattern.sub(replace_val, orig_val)

                if matched and new_val != orig_val:
                    replacements.append({
                        "sheet": s_name,
                        "cell": cell.coordinate,
                        "old_value": orig_val[:100],
                        "new_value": new_val[:100],
                    })
                    if not dry_run:
                        cell.value = new_val

                    if len(replacements) >= max_replacements:
                        break
            if len(replacements) >= max_replacements:
                break
        if len(replacements) >= max_replacements:
            break

    save_path = None
    if not dry_run and replacements:
        save_path = output_path or file_path
        _safe_save_workbook(wb, save_path)
    wb.close()

    return {
        "file_path": file_path,
        "saved_path": save_path,
        "dry_run": dry_run,
        "search_val": search_val,
        "replace_val": replace_val,
        "total_matches": len(replacements),
        "limit_reached": len(replacements) >= max_replacements,
        "replacements_preview": replacements[:100],
        "message": (
            f"Dry run complete: {len(replacements)} matching cells found. Set dry_run=False to apply changes."
            if dry_run
            else f"Successfully replaced {len(replacements)} cells and saved to '{save_path}'."
        ),
    }


# ============================================================================
# 8. NATIVE EXCEL TABLES, STRUCTURED MUTATIONS & WORKBOOK DIFF
# ============================================================================

@mcp.tool()
def create_table(
    file_path: str,
    range_address: str,
    table_name: str,
    sheet_name: Optional[str] = None,
    table_style: Optional[str] = "TableStyleMedium9",
    show_filter: bool = True,
    show_row_stripes: bool = True,
    output_path: Optional[str] = None
) -> Dict[str, Any]:
    """
    Convert a rectangular cell range (e.g. 'A1:F50') into a native styled Excel Table (ListObject) with auto-filters.
    
    Args:
        file_path: Path to Excel workbook.
        range_address: Rectangular range address (e.g. 'A1:H25').
        table_name: Unique table identifier (e.g. 'tbl_MaterialsSummary'). Letters, numbers, and underscores only.
        sheet_name: Target sheet name (defaults to active sheet).
        table_style: Excel table style name (e.g. 'TableStyleMedium9', 'TableStyleLight1', 'TableStyleDark2').
        show_filter: Whether to display dropdown filter arrows on header cells.
        show_row_stripes: Whether to apply alternating banded row colors.
        output_path: Optional destination path (overwrites file_path if None).
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    wb = openpyxl.load_workbook(file_path)
    ws = wb[sheet_name] if sheet_name and sheet_name in wb.sheetnames else wb.active

    # Clean table name
    clean_name = re.sub(r'[^a-zA-Z0-9_]', '_', table_name.strip())
    if not clean_name or clean_name[0].isdigit():
        clean_name = f"Tbl_{clean_name}"

    # Check for existing table name collision
    for existing_sheet in wb.worksheets:
        if clean_name in existing_sheet.tables:
            raise ValueError(f"Table name '{clean_name}' already exists in sheet '{existing_sheet.title}'.")

    # Ensure top-row headers are strings to satisfy openpyxl requirements
    min_col, min_row, max_col, max_row = range_boundaries(range_address.upper())
    for col_i in range(min_col, max_col + 1):
        c_val = ws.cell(row=min_row, column=col_i).value
        if c_val is None or not isinstance(c_val, str):
            ws.cell(row=min_row, column=col_i, value=str(c_val) if c_val is not None else f"Column_{col_i}")

    tab = Table(displayName=clean_name, ref=range_address.upper())
    if table_style:
        style = TableStyleInfo(
            name=table_style,
            showFirstColumn=False,
            showLastColumn=False,
            showRowStripes=show_row_stripes,
            showColumnStripes=False
        )
        tab.tableStyleInfo = style

    if not show_filter:
        tab.autoFilter = None

    ws.add_table(tab)

    save_path = output_path or file_path
    _safe_save_workbook(wb, save_path)
    wb.close()

    return {
        "status": "success",
        "file_path": file_path,
        "saved_path": save_path,
        "sheet_name": ws.title,
        "table_name": clean_name,
        "range": range_address.upper(),
        "table_style": table_style,
        "show_filter": show_filter
    }


@mcp.tool()
def list_tables(
    file_path: str,
    sheet_name: Optional[str] = None
) -> Dict[str, Any]:
    """
    List all native Excel Tables (ListObjects) in a workbook, including their sheet locations, range bounds, and column names.

    Args:
        file_path: Path to Excel workbook.
        sheet_name: Optional filter for a specific sheet name.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    wb = openpyxl.load_workbook(file_path, read_only=False)
    tables_found = []

    target_sheets = [wb[sheet_name]] if (sheet_name and sheet_name in wb.sheetnames) else wb.worksheets

    for ws in target_sheets:
        for t_key in list(ws.tables):
            tab = ws.tables[t_key] if isinstance(t_key, str) else t_key
            min_col, min_row, max_col, max_row = range_boundaries(tab.ref)
            headers = []
            for col_idx in range(min_col, max_col + 1):
                val = ws.cell(row=min_row, column=col_idx).value
                headers.append(str(val) if val is not None else f"Column_{col_idx}")

            tables_found.append({
                "sheet": ws.title,
                "name": getattr(tab, "name", str(t_key)),
                "displayName": getattr(tab, "displayName", str(t_key)),
                "range": tab.ref,
                "columns": headers,
                "column_count": len(headers),
                "row_count": max(0, max_row - min_row),
                "style": tab.tableStyleInfo.name if tab.tableStyleInfo else None
            })

    wb.close()

    return {
        "file_path": file_path,
        "total_tables": len(tables_found),
        "tables": tables_found
    }


@mcp.tool()
def insert_column(
    file_path: str,
    col_index: Optional[int] = None,
    col_idx: Optional[int] = None,
    sheet_name: Optional[str] = None,
    header_name: Optional[str] = None,
    header: Optional[str] = None,
    values: Optional[List[Any]] = None,
    formula_template: Optional[str] = None,
    output_path: Optional[str] = None
) -> Dict[str, Any]:
    """
    Insert a new column at a 1-indexed column position, shifting subsequent columns right.
    Optionally populates a header, row values, or formulas (e.g. '=B{row}*C{row}').

    Args:
        file_path: Path to Excel workbook.
        col_index: 1-indexed column position (e.g. 2 for Column B).
        col_idx: Alias for col_index.
        sheet_name: Sheet name or index.
        header_name: Optional header text for row 1.
        header: Alias for header_name.
        values: Optional list of values for subsequent data rows (starting at row 2).
        formula_template: Optional formula template with {row} placeholder (e.g. '=B{row}*C{row}').
        output_path: Optional destination path.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    target_col = col_index if col_index is not None else col_idx
    if target_col is None:
        raise ValueError("Either 'col_index' or 'col_idx' must be provided.")
    target_header = header_name if header_name is not None else header

    wb = openpyxl.load_workbook(file_path)
    ws = wb[sheet_name] if sheet_name and sheet_name in wb.sheetnames else wb.active

    ws.insert_cols(target_col, amount=1)

    if target_header is not None:
        ws.cell(row=1, column=target_col, value=str(target_header))

    if values:
        for idx, val in enumerate(values):
            ws.cell(row=idx + 2, column=target_col, value=_clean_val(val))

    if formula_template:
        max_r = ws.max_row
        for r in range(2, max_r + 1):
            f_str = formula_template.format(row=r)
            ws.cell(row=r, column=target_col, value=f_str)

    save_path = output_path or file_path
    _safe_save_workbook(wb, save_path)
    wb.close()

    return {
        "status": "success",
        "file_path": file_path,
        "saved_path": save_path,
        "sheet_name": ws.title,
        "column_inserted_index": target_col,
        "column_letter": get_column_letter(target_col),
        "header_name": target_header,
        "total_columns": ws.max_column
    }


@mcp.tool()
def delete_column(
    file_path: str,
    col_identifier: Union[int, str],
    sheet_name: Optional[str] = None,
    output_path: Optional[str] = None
) -> Dict[str, Any]:
    """
    Delete a column from a worksheet by 1-indexed column number, column letter ('C'), or header name.
    Subsequent columns shift left automatically.

    Args:
        file_path: Path to Excel workbook.
        col_identifier: 1-indexed column index (e.g. 3), column letter (e.g. 'C'), or header name (e.g. 'Unit Cost').
        sheet_name: Sheet name or index.
        output_path: Optional destination path.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    wb = openpyxl.load_workbook(file_path)
    ws = wb[sheet_name] if sheet_name and sheet_name in wb.sheetnames else wb.active

    target_idx = None
    if isinstance(col_identifier, int) or (isinstance(col_identifier, str) and col_identifier.isdigit()):
        target_idx = int(col_identifier)
    elif isinstance(col_identifier, str):
        c_str = col_identifier.strip()
        if len(c_str) <= 3 and c_str.isalpha():
            target_idx = column_index_from_string(c_str.upper())
        else:
            # Search row 1 headers
            for c_idx in range(1, ws.max_column + 1):
                val = ws.cell(row=1, column=c_idx).value
                if val is not None and str(val).strip().lower() == c_str.lower():
                    target_idx = c_idx
                    break

    if not target_idx or target_idx < 1 or target_idx > ws.max_column:
        wb.close()
        raise ValueError(f"Could not resolve column '{col_identifier}' in sheet '{ws.title}'.")

    col_letter_deleted = get_column_letter(target_idx)
    ws.delete_cols(target_idx, amount=1)

    save_path = output_path or file_path
    _safe_save_workbook(wb, save_path)
    wb.close()

    return {
        "status": "success",
        "file_path": file_path,
        "saved_path": save_path,
        "sheet_name": ws.title,
        "deleted_column_index": target_idx,
        "deleted_column_letter": col_letter_deleted,
        "remaining_columns": ws.max_column
    }


@mcp.tool()
def insert_rows(
    file_path: str,
    row_index: Optional[int] = None,
    row_idx: Optional[int] = None,
    amount: int = 1,
    count: Optional[int] = None,
    sheet_name: Optional[str] = None,
    data: Optional[List[List[Any]]] = None,
    rows_data: Optional[List[List[Any]]] = None,
    output_path: Optional[str] = None
) -> Dict[str, Any]:
    """
    Insert one or more blank or populated rows starting at a 1-indexed row position.
    Subsequent rows are shifted down automatically.

    Args:
        file_path: Path to Excel workbook.
        row_index: 1-indexed row position where rows will be inserted.
        row_idx: Alias for row_index.
        amount: Number of rows to insert (default 1).
        count: Alias for amount.
        sheet_name: Sheet name or index.
        data: Optional list of row lists containing values to write into inserted rows.
        rows_data: Alias for data.
        output_path: Optional destination path.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    target_row = row_index if row_index is not None else row_idx
    if target_row is None:
        raise ValueError("Either 'row_index' or 'row_idx' must be provided.")
    row_data = data or rows_data
    num_rows = len(row_data) if row_data else (count if count is not None else max(1, amount))

    wb = openpyxl.load_workbook(file_path)
    ws = wb[sheet_name] if sheet_name and sheet_name in wb.sheetnames else wb.active

    ws.insert_rows(target_row, amount=num_rows)

    if row_data:
        for r_offset, row_vals in enumerate(row_data):
            for c_idx, val in enumerate(row_vals):
                ws.cell(row=target_row + r_offset, column=c_idx + 1, value=_clean_val(val))

    save_path = output_path or file_path
    _safe_save_workbook(wb, save_path)
    wb.close()

    return {
        "status": "success",
        "file_path": file_path,
        "saved_path": save_path,
        "sheet_name": ws.title,
        "inserted_at_row": target_row,
        "rows_inserted_count": num_rows,
        "total_rows": ws.max_row
    }


@mcp.tool()
def delete_rows(
    file_path: str,
    row_index: Optional[int] = None,
    row_idx: Optional[int] = None,
    amount: int = 1,
    count: Optional[int] = None,
    sheet_name: Optional[str] = None,
    output_path: Optional[str] = None
) -> Dict[str, Any]:
    """
    Delete one or more rows from a worksheet by 1-indexed row number.
    Subsequent rows shift up automatically.

    Args:
        file_path: Path to Excel workbook.
        row_index: 1-indexed row number to delete.
        row_idx: Alias for row_index.
        amount: Number of consecutive rows to delete (default 1).
        count: Alias for amount.
        sheet_name: Sheet name or index.
        output_path: Optional destination path.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    target_row = row_index if row_index is not None else row_idx
    if target_row is None:
        raise ValueError("Either 'row_index' or 'row_idx' must be provided.")
    num_rows = count if count is not None else max(1, amount)

    wb = openpyxl.load_workbook(file_path)
    ws = wb[sheet_name] if sheet_name and sheet_name in wb.sheetnames else wb.active

    ws.delete_rows(target_row, amount=num_rows)

    save_path = output_path or file_path
    _safe_save_workbook(wb, save_path)
    wb.close()

    return {
        "status": "success",
        "file_path": file_path,
        "saved_path": save_path,
        "sheet_name": ws.title,
        "deleted_start_row": target_row,
        "deleted_rows_count": num_rows,
        "remaining_rows": ws.max_row
    }


@mcp.tool()
def merge_cells(
    file_path: str,
    range_address: str,
    sheet_name: Optional[str] = None,
    value: Optional[Any] = None,
    alignment: Optional[Dict[str, str]] = None,
    output_path: Optional[str] = None
) -> Dict[str, Any]:
    """
    Merge a rectangular cell range (e.g. 'A1:D1') with optional text and center/middle alignment.

    Args:
        file_path: Path to Excel workbook.
        range_address: Rectangular range string (e.g. 'B2:E2').
        sheet_name: Sheet name or index.
        value: Optional value to assign to the top-left merged anchor cell.
        alignment: Optional dict e.g. {'horizontal': 'center', 'vertical': 'center', 'wrap_text': True}.
        output_path: Optional destination path.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    wb = openpyxl.load_workbook(file_path)
    ws = wb[sheet_name] if sheet_name and sheet_name in wb.sheetnames else wb.active

    ws.merge_cells(range_address)
    min_col, min_row, _, _ = range_boundaries(range_address)
    top_left_cell = ws.cell(row=min_row, column=min_col)

    if value is not None:
        top_left_cell.value = value

    if alignment:
        top_left_cell.alignment = Alignment(
            horizontal=alignment.get("horizontal", "center"),
            vertical=alignment.get("vertical", "center"),
            wrap_text=alignment.get("wrap_text", False)
        )

    save_path = output_path or file_path
    _safe_save_workbook(wb, save_path)
    wb.close()

    return {
        "status": "success",
        "file_path": file_path,
        "saved_path": save_path,
        "sheet_name": ws.title,
        "merged_range": range_address.upper(),
        "anchor_cell": top_left_cell.coordinate,
        "value": value
    }


@mcp.tool()
def diff_workbooks(
    file_path_a: str,
    file_path_b: str,
    sheet_name: Optional[str] = None,
    key_column: Optional[str] = None,
    numeric_tolerance: float = 0.001,
    output_report_path: Optional[str] = None
) -> Dict[str, Any]:
    """
    Deterministically compare two Excel workbooks cell-by-cell or row-by-row on a key column.
    Reports added sheets, missing sheets, altered cell coordinates, and value diffs.

    Args:
        file_path_a: Baseline Excel file path.
        file_path_b: Comparison Excel file path.
        sheet_name: Specific sheet name to compare (if omitted, compares all shared sheets).
        key_column: Optional header column to align rows on instead of absolute coordinates.
        numeric_tolerance: Maximum numeric difference threshold considered identical (default 0.001).
        output_report_path: Optional path to write a visual styled diff workbook.
    """
    p_a = Path(file_path_a).resolve()
    p_b = Path(file_path_b).resolve()
    if not p_a.exists():
        raise FileNotFoundError(f"File not found: {p_a}")
    if not p_b.exists():
        raise FileNotFoundError(f"File not found: {p_b}")

    xl_a = pd.ExcelFile(p_a)
    xl_b = pd.ExcelFile(p_b)
    try:
        sheets_a = set(xl_a.sheet_names)
        sheets_b = set(xl_b.sheet_names)

        shared_sheets = [sheet_name] if sheet_name else [s for s in xl_a.sheet_names if s in sheets_b]
        sheets_only_in_a = list(sheets_a - sheets_b)
        sheets_only_in_b = list(sheets_b - sheets_a)

        all_diffs = []
        total_mismatches = 0

        for s in shared_sheets:
            df_a = xl_a.parse(s)
            df_b = xl_b.parse(s)

            df_a.columns = [str(c).strip() for c in df_a.columns]
            df_b.columns = [str(c).strip() for c in df_b.columns]

            if key_column and key_column in df_a.columns and key_column in df_b.columns:
                # Key-based comparison
                merged = pd.merge(df_a, df_b, on=key_column, how="outer", suffixes=("_a", "_b"), indicator=True)
                shared_cols = [c for c in df_a.columns if c in df_b.columns and c != key_column]

                for _, row in merged[merged["_merge"] == "both"].iterrows():
                    for col in shared_cols:
                        v_a = row.get(f"{col}_a")
                        v_b = row.get(f"{col}_b")
                        if pd.isna(v_a) and pd.isna(v_b):
                            continue
                        if isinstance(v_a, (int, float)) and isinstance(v_b, (int, float)) and not isinstance(v_a, bool) and not isinstance(v_b, bool):
                            if abs(float(v_a) - float(v_b)) > numeric_tolerance:
                                all_diffs.append({
                                    "sheet": s,
                                    "key": row[key_column],
                                    "field": col,
                                    "value_a": _clean_val(v_a),
                                    "value_b": _clean_val(v_b),
                                    "delta": round(float(v_b) - float(v_a), 4)
                                })
                                total_mismatches += 1
                        elif str(v_a).strip() != str(v_b).strip():
                            all_diffs.append({
                                "sheet": s,
                                "key": row[key_column],
                                "field": col,
                                "value_a": _clean_val(v_a),
                                "value_b": _clean_val(v_b),
                                "delta": None
                            })
                            total_mismatches += 1
            else:
                # Coordinate-based cell comparison
                max_r = max(len(df_a), len(df_b))
                shared_cols = [c for c in df_a.columns if c in df_b.columns]

                for r_idx in range(max_r):
                    for col in shared_cols:
                        v_a = df_a.iloc[r_idx][col] if r_idx < len(df_a) else None
                        v_b = df_b.iloc[r_idx][col] if r_idx < len(df_b) else None
                        if pd.isna(v_a) and pd.isna(v_b):
                            continue
                        if isinstance(v_a, (int, float)) and isinstance(v_b, (int, float)) and not isinstance(v_a, bool) and not isinstance(v_b, bool):
                            if abs(float(v_a) - float(v_b)) > numeric_tolerance:
                                all_diffs.append({
                                    "sheet": s,
                                    "row": r_idx + 2,
                                    "column": col,
                                    "value_a": _clean_val(v_a),
                                    "value_b": _clean_val(v_b),
                                    "delta": round(float(v_b) - float(v_a), 4)
                                })
                                total_mismatches += 1
                        elif str(v_a).strip() != str(v_b).strip():
                            all_diffs.append({
                                "sheet": s,
                                "row": r_idx + 2,
                                "column": col,
                                "value_a": _clean_val(v_a),
                                "value_b": _clean_val(v_b),
                                "delta": None
                            })
                            total_mismatches += 1

        report_path = None
        if output_report_path and all_diffs:
            out_p = Path(output_report_path).resolve()
            out_p.parent.mkdir(parents=True, exist_ok=True)
            diff_df = pd.DataFrame(all_diffs)
            with pd.ExcelWriter(out_p, engine="openpyxl") as writer:
                diff_df.to_excel(writer, sheet_name="Differences", index=False)
            report_path = str(out_p)

        return {
            "status": "success",
            "file_a": str(p_a),
            "file_b": str(p_b),
            "sheets_only_in_a": sheets_only_in_a,
            "sheets_only_in_b": sheets_only_in_b,
            "shared_sheets_audited": shared_sheets,
            "total_differences_count": total_mismatches,
            "sample_differences": all_diffs[:20],
            "diff_report_file": report_path
        }
    finally:
        try:
            xl_a.close()
        except Exception:
            pass
        try:
            xl_b.close()
        except Exception:
            pass


if __name__ == "__main__":
    mcp.run()

