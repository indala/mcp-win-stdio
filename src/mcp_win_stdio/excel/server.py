#!/usr/bin/env python3
"""
High-Performance Excel MCP Server powered by Python, Pandas, OpenPyXL,
and Native Windows Microsoft Excel (COM Automation via PyWin32).
"""

import os
import math
from typing import Any, Optional, List, Dict, Union
import pandas as pd
import openpyxl
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


def _df_to_clean_records(df: pd.DataFrame) -> List[Dict[str, Any]]:
    """Convert DataFrame to JSON-safe records, cleanly handling NaT, NaN, Timestamps, and dates."""
    clean = df.astype(object).where(pd.notnull(df), None)
    records = clean.to_dict(orient="records")
    for row in records:
        for k, v in row.items():
            if pd.isna(v):
                row[k] = None
            elif hasattr(v, "isoformat"):
                row[k] = v.isoformat()
            elif isinstance(v, (float, int)) and (math.isnan(v) or math.isinf(v)):
                row[k] = None
    return records


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
    nrows: int = 10,
) -> Dict[str, Any]:
    """
    Preview the first N rows of a sheet. Loads only the requested rows for speed.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    nrows = max(1, min(nrows, 200))
    df = pd.read_excel(file_path, sheet_name=sheet_name or 0, nrows=nrows)
    rows = _df_to_clean_records(df)

    return {
        "sheet_name": sheet_name or "First Sheet",
        "preview_row_count": len(rows),
        "columns": list(df.columns),
        "column_types": {col: str(dtype) for col, dtype in df.dtypes.items()},
        "rows": rows,
    }


@mcp.tool()
def query_rows(
    file_path: str,
    sheet_name: Optional[str] = None,
    query: Optional[str] = None,
    columns: Optional[List[str]] = None,
    limit: int = 50,
    offset: int = 0,
) -> Dict[str, Any]:
    """
    Query, filter, and paginate through Excel rows using Pandas vectorized expressions.
    Example query: "Age > 30 and Status == 'Active'" or "Department in ['Sales', 'Engineering']"
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    limit = max(1, min(limit, 500))
    offset = max(0, offset)

    df = pd.read_excel(file_path, sheet_name=sheet_name or 0, usecols=columns)

    if query:
        try:
            df = df.query(query)
        except Exception as e:
            raise ValueError(f"Invalid query expression '{query}': {str(e)}")

    total_matches = len(df)
    paginated_df = df.iloc[offset : offset + limit]
    rows = _df_to_clean_records(paginated_df)

    return {
        "total_matches": total_matches,
        "offset": offset,
        "limit": limit,
        "returned_rows": len(rows),
        "columns": list(df.columns),
        "rows": rows,
    }



@mcp.tool()
def read_range(
    file_path: str,
    sheet_name: Optional[str] = None,
    start_row: int = 1,
    end_row: int = 50,
    columns: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Read a specific slice of rows (e.g. rows 100 to 200) without loading the entire spreadsheet.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    if start_row < 1:
        start_row = 1
    if end_row < start_row:
        raise ValueError(f"end_row ({end_row}) must be >= start_row ({start_row})")

    nrows = min(end_row - start_row + 1, 1000)

    if start_row <= 1:
        df = pd.read_excel(file_path, sheet_name=sheet_name or 0, nrows=nrows, usecols=columns)
    else:
        header_df = pd.read_excel(file_path, sheet_name=sheet_name or 0, nrows=0, usecols=columns)
        df = pd.read_excel(
            file_path,
            sheet_name=sheet_name or 0,
            skiprows=range(1, start_row),
            nrows=nrows,
            names=header_df.columns,
            usecols=columns,
        )

    rows = _df_to_clean_records(df)
    return {
        "start_row": start_row,
        "end_row": start_row + len(rows) - 1,
        "row_count": len(rows),
        "columns": list(df.columns),
        "rows": rows,
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
    data: List[Dict[str, Any]],
    sheet_name: str = "Sheet1",
) -> Dict[str, Any]:
    """
    Create a new Excel file from a list of record dictionaries.
    Automatically sets up headers and adjusts column widths.
    """
    if not data:
        raise ValueError("Data list cannot be empty.")

    out_dir = os.path.dirname(os.path.abspath(file_path))
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    df = pd.DataFrame(data)
    with pd.ExcelWriter(file_path, engine="openpyxl") as writer:

        df.to_excel(writer, sheet_name=sheet_name, index=False)
        ws = writer.sheets[sheet_name]
        for col in ws.columns:
            max_len = max(len(str(cell.value or "")) for cell in col)
            col_letter = openpyxl.utils.get_column_letter(col[0].column)
            ws.column_dimensions[col_letter].width = min(max(max_len + 3, 10), 50)

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

    wb.save(file_path)
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
    wb.save(file_path)
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
    wb.save(file_path)
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
    wb.save(file_path)
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
) -> Dict[str, Any]:
    """
    Update specific cell coordinates or formulas.
    Example updates: [{"cell": "B5", "value": 1500}, {"cell": "C5", "value": "=A5*B5"}]
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    wb = openpyxl.load_workbook(file_path)
    sheet = wb[sheet_name] if sheet_name and sheet_name in wb.sheetnames else wb.active

    updated_count = 0
    for item in updates:
        coord = item.get("cell")
        val = item.get("value")
        if coord:
            sheet[coord] = val
            updated_count += 1

    wb.save(file_path)
    wb.close()

    return {
        "status": "success",
        "file_path": file_path,
        "cells_updated": updated_count,
    }


@mcp.tool()
def export_to_csv(
    file_path: str,
    output_csv_path: str,
    sheet_name: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Export an Excel sheet to a clean CSV file in chunks for fast external processing.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    out_dir = os.path.dirname(os.path.abspath(output_csv_path))
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)


    df = pd.read_excel(file_path, sheet_name=sheet_name or 0)
    df.to_csv(output_csv_path, index=False)


    return {
        "status": "success",
        "input_excel": file_path,
        "output_csv": output_csv_path,
        "rows_exported": len(df),
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
        wb = excel.Workbooks.Open(abs_path)
        excel.CalculateFull()
        wb.Save()
        wb.Close()
        wb = None
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
        wb = excel.Workbooks.Open(abs_path)
        wb.RefreshAll()
        excel.CalculateUntilAsyncQueriesDone()
        wb.Save()
        wb.Close()
        wb = None
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
        wb = excel.Workbooks.Open(abs_path)
        macro_args = args or []
        macro_res = excel.Application.Run(macro_name, *macro_args)
        wb.Save()
        wb.Close()
        wb = None
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


if __name__ == "__main__":
    mcp.run()
