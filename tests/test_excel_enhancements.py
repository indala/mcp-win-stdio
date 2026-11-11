from pathlib import Path

import openpyxl
import pytest
from mcp_win_stdio.excel.server import (
    _auto_detect_header_row,
    _clean_and_deduplicate_columns,
    preview_sheet,
    profile_sheet,
    query_rows,
)


def test_auto_detect_header_row(tmp_path):
    # Create workbook with row 0 = title banner, row 1 = blank, row 2 = headers
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["EXPORT REPORT 2026"])
    ws.append([])
    ws.append(["ID", "Activity Type", "Description", "Cost", "Price"])
    ws.append([1, "Rigging", "Truss Assembly", 100, 150])
    file_path = str(tmp_path / "test_banner.xlsx")
    wb.save(file_path)

    detected = _auto_detect_header_row(file_path)
    assert detected == 2


def test_clean_and_deduplicate_columns():
    cols = ["Activity", None, "Description", "Unnamed: 3", "Activity", ""]
    cleaned = _clean_and_deduplicate_columns(cols)
    assert cleaned == ["Activity", "Column_2", "Description", "Column_4", "Activity_2", "Column_6"]
    assert len(set(cleaned)) == len(cleaned)


def test_preview_sheet_no_duplicate_data_and_auto_header(tmp_path):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["BANNER TITLE"])
    ws.append(["Code", "Activity Type", None, "Price"])  # Col 3 missing header
    ws.append(["A01", "Rigging", "Set Erection", 500])
    ws.append(["A02", "Lighting", "Focusing", 300])
    file_path = str(tmp_path / "test_preview.xlsx")
    wb.save(file_path)

    res = preview_sheet(file_path=file_path)
    # Check auto header detection
    assert res.get("header_row_used") == 1
    assert "Column_3" in res.get("columns", [])
    # Check token savings: "rows" exists, but redundant "data" key is REMOVED
    assert "rows" in res
    assert "data" not in res
    assert len(res["rows"]) == 2
    assert res["rows"][0]["Column_3"] == "Set Erection"


def test_profile_sheet_safe_on_duplicate_and_missing_headers(tmp_path):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["BANNER TITLE"])
    ws.append(["Code", "Type", None, "Type", "Cost"])  # Duplicate "Type", missing col 3
    for i in range(25):
        ws.append([f"C{i}", "Staging", "Set Erection", "Staging", 100 + i])
    file_path = str(tmp_path / "test_profile.xlsx")
    wb.save(file_path)

    res = profile_sheet(file_path=file_path)
    assert res.get("total_rows") == 25
    assert res.get("total_columns") == 5
    profiles = res.get("column_profiles", {})
    assert "Column_3" in profiles
    assert profiles["Column_3"]["unique_count"] == 1
    assert "Set Erection" in profiles["Column_3"]["top_frequent"]
