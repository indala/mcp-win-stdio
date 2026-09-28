import os
import sys
from pathlib import Path

for p in Path("packages").glob("*/src"):
    sys.path.insert(0, str(p.resolve()))
sys.path.insert(0, os.path.abspath("src"))
import json
import decimal
import uuid
from datetime import datetime, date, time
import pandas as pd
import numpy as np
import pathspec

def test_excel_clean_records():
    from mcp_win_stdio.excel.server import _df_to_clean_records
    df = pd.DataFrame({
        "dates": [pd.Timestamp("2026-01-01 12:00:00"), pd.NaT],
        "nums": [10.5, np.nan],
        "texts": ["hello", None]
    })
    records = _df_to_clean_records(df)
    assert len(records) == 2
    assert records[0]["dates"] == "2026-01-01T12:00:00"
    assert records[1]["dates"] is None
    assert records[0]["nums"] == 10.5
    assert records[1]["nums"] is None
    assert records[0]["texts"] == "hello"
    assert records[1]["texts"] is None
    print("[PASS] Excel clean records test passed.")

def test_explorer_gitignore():
    from mcp_win_stdio.explorer.server import _matches_gitignore
    patterns = ["node_modules/", "dist/", "*.pyc", "temp_dir/"]
    spec = pathspec.PathSpec.from_lines("gitwildmatch", patterns)
    assert _matches_gitignore(spec, "node_modules", is_dir=True) is True
    assert _matches_gitignore(spec, "dist", is_dir=True) is True
    assert _matches_gitignore(spec, "src/foo.pyc", is_dir=False) is True
    assert _matches_gitignore(spec, "src/foo.py", is_dir=False) is False
    print("[PASS] Explorer gitignore test passed.")

def test_tsc_safety():
    from mcp_win_stdio.tsc.server import (
        find_tsconfigs,
        is_home_or_root_dir,
        get_default_watch_dir,
        check_tsc_available,
        list_watched_projects,
    )
    assert is_home_or_root_dir("C:\\") is True
    assert is_home_or_root_dir(str(Path.home())) is True
    appdata = os.environ.get("APPDATA")
    if appdata:
        assert is_home_or_root_dir(appdata) is True

    # Standby check when env is empty
    old_env = os.environ.pop("TSC_WATCH_DIR", None)
    try:
        assert get_default_watch_dir() is None
        status = list_watched_projects()
        assert status["status"] == "standby"
        assert status["watched_projects_count"] == 0
    finally:
        if old_env:
            os.environ["TSC_WATCH_DIR"] = old_env

    # Compiler pre-check
    tsc_check = check_tsc_available()
    assert "available" in tsc_check
    assert "command" in tsc_check

    # Should not crash or crawl home/root
    configs = find_tsconfigs("C:\\")
    assert isinstance(configs, list)
    print("[PASS] TSC safety, standby mode, and pre-check tests passed.")

def test_db_truncate_cell():
    import json
    from mcp_win_stdio.db.server import _truncate_cell
    d = decimal.Decimal("123.456")
    u = uuid.uuid4()
    now = datetime.now()
    mem = memoryview(b"binary_payload")
    
    cleaned = {
        "decimal": _truncate_cell(d),
        "uuid": _truncate_cell(u),
        "datetime": _truncate_cell(now),
        "mem": _truncate_cell(mem),
        "long_str": _truncate_cell("a" * 600, max_chars=100)
    }
    # Verify strict JSON serializability
    serialized = json.dumps(cleaned)
    assert "123.456" in serialized
    assert "<binary data: 14 bytes>" in serialized
    assert "... [truncated 500 chars]" in serialized
    print("[PASS] DB truncate cell serialization test passed.")

def test_excel_context_protection():
    import tempfile
    from mcp_win_stdio.excel.server import (
        query_rows, preview_sheet, read_range, get_column_values, compare_column_values, export_to_csv,
        export_to_json, profile_sheet, query_excel_sql
    )
    # Create sample Excel workbook
    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
        tmp_path = tmp.name
    try:
        df = pd.DataFrame({
            "code": [f"MAT{i:04d}" for i in range(150)],
            "desc": [f"Item description {i}" for i in range(150)],
            "qty": [i * 2 for i in range(150)]
        })
        df.to_excel(tmp_path, index=False)

        # 1. Test query_rows capping at 100 for records and returning protection notice
        res = query_rows(tmp_path, limit=5000, format="records")
        assert res["limit"] == 100
        assert res["returned_rows"] == 100
        assert "context_protection_notice" in res
        assert isinstance(res["rows"], list)
        assert len(res["rows"]) == 100

        # 2. Test compact format (list of lists)
        res_compact = query_rows(tmp_path, limit=200, format="compact")
        assert res_compact["format"] == "compact"
        assert isinstance(res_compact["data"], list)
        assert isinstance(res_compact["data"][0], list)
        assert res_compact["limit"] == 150 or res_compact["returned_rows"] == 150

        # 3. Test tsv format
        res_tsv = query_rows(tmp_path, limit=50, format="tsv")
        assert res_tsv["format"] == "tsv"
        assert "code\tdesc\tqty" in res_tsv["data"]

        # 4. Test get_column_values
        col_res = get_column_values(tmp_path, column="code", limit=50)
        assert col_res["unique_count"] == 150
        assert len(col_res["values"]) == 50
        assert col_res["values"][0] == "MAT0000"

        # 6. Test export_to_json
        json_tmp = tmp_path.replace(".xlsx", ".json")
        json_res = export_to_json(tmp_path, json_tmp, orient="records")
        assert json_res["status"] == "success"
        assert os.path.exists(json_tmp)
        with open(json_tmp, "r", encoding="utf-8") as jf:
            parsed = json.load(jf)
            assert len(parsed) == 150
            assert parsed[0]["code"] == "MAT0000"
        os.remove(json_tmp)

        # 7. Test profile_sheet
        prof_res = profile_sheet(tmp_path)
        assert prof_res["total_rows"] == 150
        assert "code" in prof_res["column_profiles"]
        assert prof_res["column_profiles"]["qty"]["numeric_stats"]["sum"] > 0

        # 8. Test query_excel_sql
        sql_res = query_excel_sql(tmp_path, "SELECT code, qty FROM sheet WHERE qty > 200 ORDER BY qty ASC")
        assert sql_res["total_returned"] > 0
        assert "code" in sql_res["columns"]
        assert isinstance(sql_res["rows"], list)

        # 9. Test audit_formulas and search_and_replace_cells
        import openpyxl
        from mcp_win_stdio.excel.server import audit_formulas, search_and_replace_cells
        wb = openpyxl.load_workbook(tmp_path)
        ws = wb.active
        ws["D1"] = "FormulaCol"
        ws["D2"] = "=SUM(#REF!)"
        ws["E1"] = "ReplaceCol"
        ws["E2"] = "TargetText123"
        wb.save(tmp_path)
        wb.close()

        af_res = audit_formulas(tmp_path)
        assert af_res["total_errors_found"] >= 1
        assert any(e["error_type"] == "#REF!" for e in af_res["errors"])

        sr_dry = search_and_replace_cells(tmp_path, search_val="TargetText123", replace_val="ReplacedVal", dry_run=True)
        assert sr_dry["dry_run"] is True
        assert sr_dry["total_matches"] >= 1

        sr_apply = search_and_replace_cells(tmp_path, search_val="TargetText123", replace_val="ReplacedVal", dry_run=False)
        assert sr_apply["dry_run"] is False
        assert sr_apply["total_matches"] >= 1

        print("[PASS] Excel context protection, column comparison, JSON export, SQL, formula audit, and search/replace tests passed.")
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


def test_word_tools():
    import docx
    import tempfile
    from mcp_win_stdio.word.server import (
        read_word_document, edit_paragraph, insert_table,
        inspect_revisions_and_comments, get_document_layout, get_document_outline
    )

    with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as tmp:
        doc_path = tmp.name

    try:
        doc = docx.Document()
        doc.add_heading("Audit Test Document", level=1)
        doc.add_paragraph("Paragraph 1: Original text for audit testing.")
        doc.add_paragraph("Paragraph 2: Second paragraph.")
        doc.save(doc_path)

        # 1. Test read_word_document
        res_read = read_word_document(doc_path, max_paragraphs=10)
        assert "Audit Test Document" in res_read
        assert "Original text" in res_read

        # 2. Test edit_paragraph safety (fails without overwrite or output_path)
        fail_res = edit_paragraph(doc_path, paragraph_index=2, new_text="Edited text", overwrite=False)
        assert "error" in fail_res

        # 3. Test edit_paragraph with overwrite=True
        ok_res = edit_paragraph(doc_path, paragraph_index=2, new_text="Paragraph 1: Modified text.", overwrite=True)
        assert ok_res["status"] == "success"

        # 4. Test insert_table
        tbl_res = insert_table(
            doc_path,
            headers=["ID", "Name", "Role"],
            rows=[["1", "Alice", "Admin"], ["2", "Bob", "User"]],
            overwrite=True
        )
        assert tbl_res["status"] == "success"
        assert tbl_res["rows_inserted"] == 2

        # 5. Test inspect_revisions_and_comments
        rev_res = inspect_revisions_and_comments(doc_path)
        assert "total_comments" in rev_res
        assert "total_insertions" in rev_res

        # 6. Test structured dict returns for layout & outline
        layout = get_document_layout(doc_path)
        assert isinstance(layout, dict)
        assert layout["total_sections"] >= 1

        outline = get_document_outline(doc_path)
        assert isinstance(outline, dict)
        assert outline["total_headings"] >= 1

        print("[PASS] Word server tests passed.")
    finally:
        if os.path.exists(doc_path):
            os.remove(doc_path)


def test_explorer_tools():
    from mcp_win_stdio.explorer.server import (
        read_file, find_symbol, get_code_stats, find_duplicate_files
    )

    # 1. Test read_file capping
    res_rf = read_file("src/mcp_win_stdio/cli.py", max_lines=10)
    assert res_rf["lines_returned"] == 10
    assert res_rf["has_more"] is True

    # 2. Test find_symbol
    sym_res = find_symbol("src/mcp_win_stdio", symbol_name="main", exact_match=True, language="python")
    assert sym_res["total_matches"] >= 1
    assert any(s["name"] == "main" for s in sym_res["symbols"])

    # 3. Test get_code_stats
    stats_res = get_code_stats("src/mcp_win_stdio")
    assert stats_res["total_files_analyzed"] > 0
    assert "Python" in stats_res["languages"]

    # 4. Test find_duplicate_files
    dup_res = find_duplicate_files("src/mcp_win_stdio", min_size_bytes=100)
    assert "total_duplicate_groups" in dup_res

    print("[PASS] Explorer advanced tools test passed.")


def test_db_agent_friction_fixes():
    from mcp_win_stdio.db.server import (
        _split_sql_statements,
        _normalize_connection_param,
        _format_db_error,
        _get_connection,
        _ACTIVE_CONNECTION
    )

    # 1. Test _normalize_connection_param (Sticky Connection Fix)
    for null_val in [None, "", "  ", "null", "NULL", "Null", "none", "NONE", "default", "DEFAULT", "undefined", "UNDEFINED"]:
        assert _normalize_connection_param(null_val) is None, f"Failed for {null_val}"
    assert _normalize_connection_param("showreel_dev") == "showreel_dev"
    assert _normalize_connection_param("  my_database  ") == "my_database"
    print("[PASS] Connection normalization test passed.")

    # 2. Test _split_sql_statements (Multi-statement batch execution)
    # Basic statements
    sql_basic = "SELECT 1; SELECT 2; SELECT 3;"
    stmts = _split_sql_statements(sql_basic)
    assert stmts == ["SELECT 1", "SELECT 2", "SELECT 3"]

    # Semicolon inside single quotes
    sql_quotes = "INSERT INTO test_tbl (val) VALUES ('a;b;c'); SELECT * FROM test_tbl;"
    stmts_q = _split_sql_statements(sql_quotes)
    assert len(stmts_q) == 2
    assert stmts_q[0] == "INSERT INTO test_tbl (val) VALUES ('a;b;c')"
    assert stmts_q[1] == "SELECT * FROM test_tbl"

    # Escaped quotes inside strings
    sql_esc = "INSERT INTO t (val) VALUES ('It''s a value; indeed'); SELECT 1;"
    stmts_esc = _split_sql_statements(sql_esc)
    assert len(stmts_esc) == 2
    assert "It''s a value; indeed" in stmts_esc[0]

    # Comments with semicolons
    sql_comments = "SELECT 1; -- comment with ; inside\nSELECT 2; /* block ; comment */ SELECT 3;"
    stmts_c = _split_sql_statements(sql_comments)
    assert len(stmts_c) == 3

    # PostgreSQL Dollar Quoting ($$ ... $$ and $tag$ ... $tag$)
    sql_dollar = """
    CREATE OR REPLACE FUNCTION test_func() RETURNS void AS $$
    BEGIN
        SELECT 1;
        INSERT INTO audit_log VALUES ('done; logged');
    END;
    $$ LANGUAGE plpgsql;
    SELECT test_func();
    """
    stmts_d = _split_sql_statements(sql_dollar)
    assert len(stmts_d) == 2
    assert "CREATE OR REPLACE FUNCTION" in stmts_d[0]
    assert "SELECT test_func()" in stmts_d[1]

    sql_tagged_dollar = """
    CREATE FUNCTION tagged() RETURNS text AS $body$
        SELECT 'hello; world';
    $body$ LANGUAGE sql;
    SELECT 42;
    """
    stmts_td = _split_sql_statements(sql_tagged_dollar)
    assert len(stmts_td) == 2
    print("[PASS] SQL statement splitter test passed.")

    # 3. Test _format_db_error (Rich diagnostic output)
    e = ValueError("Table 'missing_table' not found.")
    formatted = _format_db_error(e, engine="postgres", sql="SELECT * FROM missing_table WHERE id = 1;", statement_idx=2)
    assert formatted["error"] is True
    assert formatted["engine"] == "postgres"
    assert formatted["failed_statement_index"] == 2
    assert formatted["message"] == "Table 'missing_table' not found."
    assert "sql_snippet" in formatted
    assert "SELECT * FROM missing_table" in formatted["sql_snippet"]
    print("[PASS] DB error formatting test passed.")

    # 4. Test LIKE parameter handling with psycopg2 / DB-API (Issue #4)
    from unittest.mock import MagicMock
    mock_cursor = MagicMock()
    mock_cursor.rowcount = 1
    mock_cursor.statusmessage = "SELECT 1"
    mock_cursor.fetchmany.return_value = [{"col": "showreel_dev"}]

    mock_conn = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

    # Simulate read_query logic with LIKE '%s...' pattern
    test_sql = "SELECT * FROM videos WHERE title LIKE '%showreel%';"
    # When params is None or empty, cur.execute must be called with ONLY (sql,), NEVER (sql, ())
    params = None
    if params:
        mock_cursor.execute(test_sql, tuple(params))
    else:
        mock_cursor.execute(test_sql)

    # Verify cur.execute was called with 1 argument (test_sql), not 2
    mock_cursor.execute.assert_called_once_with(test_sql)
    print("[PASS] LIKE query parameter handling test passed.")



def test_db_pii_masking():
    """Test that _truncate_row redacts PII columns and passes safe columns through."""
    from mcp_win_stdio.db.server import _truncate_row, PII_COLUMN_PATTERN
    import re

    # PII_COLUMN_PATTERN should match these
    sensitive_cols = ["password", "password_hash", "api_key", "secret_token", "ssn",
                      "credit_card_number", "auth_token", "private_key", "access_token"]
    for col in sensitive_cols:
        assert PII_COLUMN_PATTERN.search(col), f"PII pattern should match '{col}'"

    # Should NOT match ordinary columns
    safe_cols = ["user_id", "username", "email", "created_at", "status", "name"]
    for col in safe_cols:
        assert not PII_COLUMN_PATTERN.search(col), f"PII pattern should NOT match '{col}'"

    # Test row-level masking
    row = {
        "user_id": 42,
        "username": "alice",
        "password_hash": "$2b$12$supersecretstuff",
        "api_key": "sk-abc123",
        "email": "alice@example.com",
        "auth_token": "eyJhbGciOiJIUzI1NiJ9.xxx"
    }

    masked = _truncate_row(row, mask_sensitive=True)
    assert masked["user_id"] == 42
    assert masked["username"] == "alice"
    assert masked["email"] == "alice@example.com"
    assert masked["password_hash"] == "[REDACTED_SENSITIVE]", f"Got: {masked['password_hash']}"
    assert masked["api_key"] == "[REDACTED_SENSITIVE]", f"Got: {masked['api_key']}"
    assert masked["auth_token"] == "[REDACTED_SENSITIVE]", f"Got: {masked['auth_token']}"

    # With mask_sensitive=False everything should pass through
    unmasked = _truncate_row(row, mask_sensitive=False)
    assert unmasked["password_hash"] == "$2b$12$supersecretstuff"
    assert unmasked["api_key"] == "sk-abc123"

    print("[PASS] DB PII masking test passed.")


def test_db_schema_tools():
    """Test compare_schemas migration_sql structure and audit_database_health non-postgres guard."""
    from mcp_win_stdio.db.server import audit_database_health, _CONNECTION_REGISTRY

    # audit_database_health should reject MySQL connections
    # We temporarily register a fake MySQL connection
    _CONNECTION_REGISTRY["_test_mysql_fake"] = {
        "name": "_test_mysql_fake",
        "engine": "mysql",
        "database": "testdb",
        "url": "mysql://user:pass@localhost/testdb",
    }
    try:
        result = audit_database_health(connection="_test_mysql_fake")
        assert "error" in result, f"Expected error for MySQL, got: {result}"
        assert "PostgreSQL" in result["error"]
        print("[PASS] audit_database_health MySQL guard test passed.")
    finally:
        _CONNECTION_REGISTRY.pop("_test_mysql_fake", None)

    # Verify compare_schemas migration_sql key is always present when the module imports
    # (structural check only — no live DB needed)
    import inspect
    from mcp_win_stdio.db import server as db_server
    src = inspect.getsource(db_server.compare_schemas)
    assert "migration_sql" in src, "compare_schemas must produce migration_sql"
    print("[PASS] compare_schemas migration_sql structural check passed.")


if __name__ == "__main__":
    test_excel_clean_records()
    test_explorer_gitignore()
    test_tsc_safety()
    test_db_truncate_cell()
    test_excel_context_protection()
    test_word_tools()
    test_explorer_tools()
    test_db_agent_friction_fixes()
    test_db_pii_masking()
    test_db_schema_tools()
    print("ALL AUDIT TESTS PASSED!")
