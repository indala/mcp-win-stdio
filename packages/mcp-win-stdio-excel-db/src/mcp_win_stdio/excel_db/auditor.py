#!/usr/bin/env python3
"""
Automated Data Auditor and Reconciliation Engine for comparing Database tables against Excel spreadsheets.
"""

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import PatternFill, Font
from openpyxl.utils import get_column_letter
from sqlalchemy import create_engine, text

from mcp_win_stdio.excel_db.stream import resolve_sqlalchemy_url


def reconcile_db_vs_excel(
    sql_query: str,
    excel_path: str,
    key_columns: List[str],
    db_url_or_config: Union[str, Dict[str, Any]],
    sheet_name: Optional[Union[str, int]] = 0,
    compare_columns: Optional[List[str]] = None,
    output_report_path: Optional[str] = None
) -> Dict[str, Any]:
    """
    Compare a database query against an Excel worksheet, detecting missing records and value mismatches.
    """
    t_start = datetime.now()
    xl_file = Path(excel_path).resolve()
    if not xl_file.exists():
        raise FileNotFoundError(f"Excel file not found: {xl_file}")

    # 1. Read Database Data
    db_url = resolve_sqlalchemy_url(db_url_or_config)
    engine = create_engine(db_url)
    with engine.connect() as conn:
        df_db = pd.read_sql_query(text(sql_query), conn)

    # 2. Read Excel Data
    df_xl = pd.read_excel(xl_file, sheet_name=sheet_name)

    # Normalize column names
    df_db.columns = [c.strip() for c in df_db.columns]
    df_xl.columns = [str(c).strip() for c in df_xl.columns]

    for k in key_columns:
        if k not in df_db.columns or k not in df_xl.columns:
            raise ValueError(f"Key column '{k}' must exist in both DB query and Excel sheet.")

    # Determine columns to compare
    if not compare_columns:
        shared_cols = [c for c in df_db.columns if c in df_xl.columns and c not in key_columns]
    else:
        shared_cols = [c for c in compare_columns if c not in key_columns]

    # Perform full outer join on key columns
    merged = pd.merge(
        df_db, df_xl,
        on=key_columns,
        how="outer",
        suffixes=("_db", "_excel"),
        indicator=True
    )

    db_only = merged[merged["_merge"] == "left_only"]
    excel_only = merged[merged["_merge"] == "right_only"]
    both = merged[merged["_merge"] == "both"]

    # Detect field value mismatches in matched rows
    mismatches = []
    for _, row in both.iterrows():
        diffs = {}
        for col in shared_cols:
            val_db = row.get(f"{col}_db")
            val_xl = row.get(f"{col}_excel")

            # Compare handling NaNs
            if pd.isna(val_db) and pd.isna(val_xl):
                continue
            if str(val_db).strip() != str(val_xl).strip():
                diffs[col] = {"db": val_db, "excel": val_xl}

        if diffs:
            keys_info = {k: row[k] for k in key_columns}
            mismatches.append({"keys": keys_info, "differences": diffs})

    # Generate styled Excel Diff Report if requested
    report_file = None
    if output_report_path:
        out_p = Path(output_report_path).resolve()
        out_p.parent.mkdir(parents=True, exist_ok=True)
        
        wb = Workbook()
        ws_summary = wb.active
        ws_summary.title = "Reconciliation Summary"

        ws_summary.append(["Reconciliation Audit Report", ""])
        ws_summary.append(["Generated At", datetime.now().isoformat()])
        ws_summary.append(["DB Records", len(df_db)])
        ws_summary.append(["Excel Records", len(df_xl)])
        ws_summary.append(["Matched Keys", len(both)])
        ws_summary.append(["Missing in Excel (DB Only)", len(db_only)])
        ws_summary.append(["Missing in DB (Excel Only)", len(excel_only)])
        ws_summary.append(["Rows with Value Discrepancies", len(mismatches)])

        if mismatches:
            ws_diff = wb.create_sheet("Discrepancies")
            diff_headers = list(key_columns) + ["Field", "DB Value", "Excel Value"]
            ws_diff.append(diff_headers)
            
            fill_mismatch = PatternFill(start_color="FFF3CD", end_color="FFF3CD", fill_type="solid")
            for m in mismatches:
                for fld, vals in m["differences"].items():
                    row_vals = [m["keys"][k] for k in key_columns] + [fld, str(vals["db"]), str(vals["excel"])]
                    ws_diff.append(row_vals)

        wb.save(out_p)
        report_file = str(out_p)

    duration = (datetime.now() - t_start).total_seconds()

    return {
        "status": "success",
        "total_db_records": len(df_db),
        "total_excel_records": len(df_xl),
        "matched_keys_count": len(both),
        "missing_in_excel_count": len(db_only),
        "missing_in_db_count": len(excel_only),
        "rows_with_mismatches_count": len(mismatches),
        "discrepancies_sample": mismatches[:5],
        "diff_report_file": report_file,
        "duration_seconds": round(duration, 3)
    }
