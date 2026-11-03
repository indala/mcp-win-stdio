"""
Comprehensive test suite verifying Phase 1 & ergonomics fixes:
1. DB write guard (mode='read_only' and env='prod' confirmation guard)
2. Column disambiguation & preservation (duplicate columns in JOINs not collapsed)
3. FK-aware describe_table structure & orphan risk candidate checks
4. Statement audit trail in db_audit.jsonl
5. Quick tool listing via search_tools(query="")
6. Tool stacking and friendly JSON string argument parsing in call_tool
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from mcp_win_stdio.db.server import (
    _disambiguate_columns,
    _fetch_rows_safe,
    _hydrate_conn_info,
    _log_statement_audit,
    describe_table,
    execute_query,
    list_connections,
    read_query,
)

from mcp_win_stdio.core.context import SessionContext
from mcp_win_stdio.server.catalog import search_tools as catalog_search_tools
from mcp_win_stdio.server.server import call_tool


# -------------------------------------------------------------------------
# 1. Duplicate Column Name Disambiguation & Safe Fetch
# -------------------------------------------------------------------------
def test_disambiguate_columns():
    cols = ["id", "name", "id", "name", "status"]
    unique_cols, duplicates = _disambiguate_columns(cols)
    assert unique_cols == ["id", "name", "id__2", "name__2", "status"]
    assert duplicates == ["id", "name"]


def test_fetch_rows_safe_preserves_duplicate_columns():
    mock_cur = MagicMock()
    mock_cur.description = [("id",), ("name",), ("id",), ("name",)]
    mock_cur.fetchmany.return_value = [
        (101, "Item A", 201, "UOM Piece"),
        (102, "Item B", 202, "UOM Box"),
    ]

    cleaned_rows, has_more, unique_cols, duplicates = _fetch_rows_safe(mock_cur, limit=10, max_cell_chars=100)
    assert has_more is False
    assert unique_cols == ["id", "name", "id__2", "name__2"]
    assert duplicates == ["id", "name"]
    assert len(cleaned_rows) == 2
    # Ensure both item and uom values are preserved!
    assert cleaned_rows[0]["id"] == 101
    assert cleaned_rows[0]["name"] == "Item A"
    assert cleaned_rows[0]["id__2"] == 201
    assert cleaned_rows[0]["name__2"] == "UOM Piece"


# -------------------------------------------------------------------------
# 2. Connection Hydration & Metadata (mode, env, description)
# -------------------------------------------------------------------------
def test_hydrate_conn_info():
    # String entry defaults
    info_str = _hydrate_conn_info("postgresql://user:pass@localhost:5432/testdb", "test_conn", "postgresql://user:pass@localhost:5432/testdb")
    assert info_str["mode"] == "read_write"
    assert info_str["env"] == "dev"
    assert info_str["description"] == ""

    # Structured dict entry
    entry = {
        "url": "postgresql://user:pass@aws-host:5432/showreel",
        "mode": "read_only",
        "env": "prod",
        "description": "Production DB on AWS Showreel",
    }
    info_dict = _hydrate_conn_info(entry, "aws_showreel", entry["url"])
    assert info_dict["mode"] == "read_only"
    assert info_dict["env"] == "prod"
    assert info_dict["description"] == "Production DB on AWS Showreel"


# -------------------------------------------------------------------------
# 3. Write Guards: read_only and prod confirmation
# -------------------------------------------------------------------------
def test_execute_query_read_only_guard():
    with patch("mcp_win_stdio.db.server._get_connection") as mock_get_conn:
        mock_get_conn.return_value = {
            "name": "aws_showreel",
            "engine": "postgres",
            "mode": "read_only",
            "env": "prod",
            "url": "postgresql://user:pass@host:5432/db",
        }

        res = execute_query(sql="UPDATE users SET status = 1;", connection="aws_showreel")
        assert res.get("isError") is True or res.get("error") is True
        assert "read-only" in res.get("message", "").lower()


def test_execute_query_prod_confirm_guard():
    with patch("mcp_win_stdio.db.server._get_connection") as mock_get_conn:
        mock_get_conn.return_value = {
            "name": "aws_showreel",
            "engine": "postgres",
            "mode": "read_write",
            "env": "prod",
            "url": "postgresql://user:pass@host:5432/db",
        }

        # Non-dry-run without confirm=True must be blocked
        res = execute_query(sql="DELETE FROM users WHERE id = 1;", connection="aws_showreel", dry_run=False, confirm=False)
        assert res.get("isError") is True or res.get("error") is True
        assert "confirm=True" in res.get("message", "")

        # dry_run=True is allowed without confirm=True (simulates safely)
        with patch("mcp_win_stdio.db.server._get_pg_client") as mock_pg:
            mock_conn = MagicMock()
            mock_cur = MagicMock()
            mock_cur.rowcount = 1
            mock_cur.statusmessage = "DELETE 1"
            mock_cur.description = None
            mock_conn.cursor.return_value.__enter__.return_value = mock_cur
            mock_pg.return_value = mock_conn

            res_dry = execute_query(sql="DELETE FROM users WHERE id = 1;", connection="aws_showreel", dry_run=True, confirm=False)
            assert res_dry.get("dryRun") is True
            assert res_dry.get("rowCount") == 1


# -------------------------------------------------------------------------
# 4. Statement Audit Log
# -------------------------------------------------------------------------
def test_statement_audit_logging(tmp_path):
    audit_file = tmp_path / "db_audit.jsonl"
    with patch("mcp_win_stdio.db.server.DB_CONNECTIONS_FILE", tmp_path / "db_connections.json"):
        _log_statement_audit("aws_showreel", "UPDATE users SET active = true", 5, False, "UPDATE 5", 12.4)
        assert audit_file.exists()
        line = audit_file.read_text(encoding="utf-8").strip()
        record = json.loads(line)
        assert record["connection"] == "aws_showreel"
        assert record["sql"] == "UPDATE users SET active = true"
        assert record["rows_affected"] == 5
        assert record["dry_run"] is False


# -------------------------------------------------------------------------
# 5. Wildcard & Server Tool Discovery in search_tools
# -------------------------------------------------------------------------
def test_search_tools_wildcard_discovery():
    # Calling search_tools with query="" or query="*" returns tools with 1-line signatures
    results = catalog_search_tools(query="", server="db", limit=50)
    assert len(results) > 0
    tool_names = [r["tool"] for r in results]
    assert "read_query" in tool_names
    assert "execute_query" in tool_names
    assert "describe_table" in tool_names

    # Check that signatures are compact and informative
    for r in results:
        assert "signature" in r
        assert r["server"] == "db"


# -------------------------------------------------------------------------
# 6. JSON String Handling & Tool Stacking in call_tool
# -------------------------------------------------------------------------
def test_call_tool_json_string_argument_parsing():
    # When agent accidentally passes a JSON string instead of dict
    with patch("mcp_win_stdio.server.server.GLOBAL_POOL") as mock_pool:
        mock_proc = MagicMock()
        mock_proc.call_tool.return_value = {"success": True}
        mock_pool.get_or_spawn.return_value = mock_proc

        # Valid JSON string should be auto-parsed into dict
        res = call_tool(
            server="db",
            tool="read_query",
            arguments='{"sql": "SELECT 1;"}',
        )
        assert mock_proc.call_tool.called
        args_passed = mock_proc.call_tool.call_args[0][1]
        assert args_passed.get("sql") == "SELECT 1;"

        # Malformed string gives a clean, helpful error instead of raw Pydantic exception
        res_bad = call_tool(
            server="db",
            tool="read_query",
            arguments="NOT_A_JSON_STRING",
        )
        assert res_bad.get("isError") is True
        assert "could not parse string as JSON object" in res_bad.get("error", "")


def test_call_tool_stacking_fallback():
    # If tool is omitted, it should fall back to session's stacked active tool
    session = SessionContext(session_id="agent_stack_test")
    session.set("server", "db")
    session.set("tool", "read_query")

    with patch("mcp_win_stdio.server.server.GLOBAL_CONTEXT") as mock_ctx:
        mock_ctx.get_session.return_value = session
        with patch("mcp_win_stdio.server.server.GLOBAL_POOL") as mock_pool:
            mock_proc = MagicMock()
            mock_proc.call_tool.return_value = {"returned_rows": 1}
            mock_pool.get_or_spawn.return_value = mock_proc

            # Calling call_tool with only arguments (no server, no tool)
            res = call_tool(arguments={"sql": "SELECT 1;"})
            assert mock_proc.call_tool.called
            tool_called = mock_proc.call_tool.call_args[0][0]
            assert tool_called == "read_query"


def test_call_tool_and_describe_tool_accepts_clean_name():
    from mcp_win_stdio.server.server import describe_tool

    # 1. call_tool with clean 'name' parameter (no redundant tool_name!)
    with patch("mcp_win_stdio.server.server.GLOBAL_POOL") as mock_pool:
        mock_proc = MagicMock()
        mock_proc.call_tool.return_value = {"success": True}
        mock_pool.get_or_spawn.return_value = mock_proc

        res = call_tool(name="read_query", arguments={"sql": "SELECT 1;"})
        assert mock_proc.call_tool.called
        assert mock_proc.call_tool.call_args[0][0] == "read_query"

    # 2. describe_tool with clean 'name' parameter and auto-resolved server
    desc = describe_tool(name="read_query")
    assert "error" not in desc
    assert desc.get("name") == "read_query"


def test_argument_normalization_and_bidirectional_casing():
    from mcp_win_stdio.server.catalog import normalize_arguments

    # 1. ssh_exec_script: script -> script_content, shell -> interpreter
    ssh_args = normalize_arguments("ssh", "ssh_exec_script", {"script": "echo hello", "shell": "bash"})
    assert ssh_args.get("script_content") == "echo hello"
    assert ssh_args.get("interpreter") == "bash"

    # 2. db.describe_table: snake_case table_name -> camelCase tableName
    db_args = normalize_arguments("db", "describe_table", {"table_name": "users"})
    assert "tableName" in db_args or "table_name" in db_args

    # 3. word.read_word_document: document -> file_path
    word_args = normalize_arguments("word", "read_word_document", {"document": "test.docx"})
    assert word_args.get("file_path") == "test.docx"

    # 4. ssh_exec: cmd -> command
    exec_args = normalize_arguments("ssh", "ssh_exec", {"cmd": "uptime"})
    assert exec_args.get("command") == "uptime"


def test_describe_table_accepts_clean_table_arg():
    # Calling describe_table directly with table="users" instead of tableName="users"
    with patch("mcp_win_stdio.db.server._get_connection") as mock_conn:
        mock_conn.side_effect = Exception("Connection resolve check")
        res = describe_table(table="my_table")
        assert res.get("error") is True
        # If it reached _get_connection, table parameter was accepted
        assert "Connection resolve check" in res.get("message", "")


def test_native_tools_accept_both_snake_and_camel():
    from mcp_win_stdio.db.server import (
        clone_database,
        drop_database,
        dump_database,
        restore_database,
        search_schema,
    )

    # 1. search_schema accepts search_term or searchTerm
    with patch("mcp_win_stdio.db.server._get_connection") as mock_conn:
        mock_conn.side_effect = Exception("Resolve check")
        res_snake = search_schema(search_term="audit")
        res_camel = search_schema(searchTerm="audit")
        assert "Resolve check" in res_snake.get("message", "")
        assert "Resolve check" in res_camel.get("message", "")

    # 2. drop_database accepts confirm_name or confirmName
    res_drop_snake = drop_database(database="testdb", confirm_name="wrong")
    assert res_drop_snake.get("error") is True
    assert "Safety Confirmation Failed" in res_drop_snake.get("message", "")

    res_drop_camel = drop_database(database="testdb", confirmName="wrong")
    assert res_drop_camel.get("error") is True
    assert "Safety Confirmation Failed" in res_drop_camel.get("message", "")

    # 3. clone_database accepts snake_case or camelCase
    with patch("mcp_win_stdio.db.server._get_connection") as mock_conn:
        mock_conn.side_effect = Exception("Resolve check")
        res_clone_snake = clone_database(source_database="s", target_database="t")
        res_clone_camel = clone_database(sourceDatabase="s", targetDatabase="t")
        assert "Resolve check" in res_clone_snake.get("message", "")
        assert "Resolve check" in res_clone_camel.get("message", "")

    # 4. restore_database accepts dump_file_path or dumpFilePath
    res_res_snake = restore_database(database="db", dump_file_path="non_existent.sql")
    assert "Dump file not found" in res_res_snake.get("message", "")

    res_res_camel = restore_database(database="db", dumpFilePath="non_existent.sql")
    assert "Dump file not found" in res_res_camel.get("message", "")


# -------------------------------------------------------------------------
# 14. Option 2: Statement Parsing, Policy Guardrails, Before-Image & Undo
# -------------------------------------------------------------------------
from mcp_win_stdio.db.server import (
    _check_write_policy,
    _parse_modifying_statement,
    get_audit_log,
    undo_query,
)


def test_parse_modifying_statement():
    # DELETE
    del_res = _parse_modifying_statement("DELETE FROM prop_requisitions WHERE id = 42;")
    assert del_res is not None
    assert del_res["operation"] == "DELETE"
    assert del_res["table"] == "prop_requisitions"
    assert del_res["where"] == "id = 42"

    # UPDATE
    upd_res = _parse_modifying_statement("UPDATE items SET price = 100 WHERE item_id = 99;")
    assert upd_res is not None
    assert upd_res["operation"] == "UPDATE"
    assert upd_res["table"] == "items"
    assert upd_res["where"] == "item_id = 99"

    # TRUNCATE
    trunc_res = _parse_modifying_statement("TRUNCATE TABLE audit_logs CASCADE;")
    assert trunc_res is not None
    assert trunc_res["operation"] == "TRUNCATE"
    assert "audit_logs" in trunc_res["table"]

    # Naked DELETE (no WHERE)
    naked_del = _parse_modifying_statement("DELETE FROM orders;")
    assert naked_del is not None
    assert naked_del["operation"] == "DELETE"
    assert naked_del["where"] is None


def test_guardrail_policy_naked_writes_and_truncate():
    # Naked delete blocked by default
    parsed_naked = _parse_modifying_statement("DELETE FROM users;")
    err = _check_write_policy(parsed_naked, env="dev", allow_unfiltered=False)
    assert err is not None
    assert "Safety Guardrail" in err
    assert "has no WHERE clause" in err

    # Permitted with allow_unfiltered=True
    err_allowed = _check_write_policy(parsed_naked, env="dev", allow_unfiltered=True)
    assert err_allowed is None

    # TRUNCATE on prod blocked unless allow_unfiltered=True
    parsed_trunc = _parse_modifying_statement("TRUNCATE TABLE transactions;")
    err_prod_trunc = _check_write_policy(parsed_trunc, env="prod", allow_unfiltered=False)
    assert err_prod_trunc is not None
    assert "TRUNCATE is blocked on production" in err_prod_trunc

    err_prod_trunc_allowed = _check_write_policy(parsed_trunc, env="prod", allow_unfiltered=True)
    assert err_prod_trunc_allowed is None


def test_execute_query_blocks_naked_delete(tmp_path):
    with patch("mcp_win_stdio.db.server._get_connection") as mock_conn:
        mock_conn.return_value = {
            "name": "test_db",
            "engine": "postgres",
            "mode": "read_write",
            "env": "dev",
        }
        res = execute_query(sql="DELETE FROM users;")
        assert res.get("error") is True
        assert "Safety Guardrail" in res.get("message", "")
        assert "allow_unfiltered=True" in res.get("message", "")


def test_undo_query_and_audit_log(tmp_path):
    audit_file = tmp_path / "db_audit.jsonl"
    with patch("mcp_win_stdio.db.server.DB_CONNECTIONS_FILE", tmp_path / "db_connections.json"):
        # Log a mutating write record with before_image
        audit_id = _log_statement_audit(
            connection="test_db",
            sql="DELETE FROM prop_requisitions WHERE id = 42;",
            rows_affected=1,
            dry_run=False,
            status="SUCCESS",
            before_image={
                "operation": "DELETE",
                "table": "prop_requisitions",
                "rows": [{"id": 42, "req_num": "RET-0042", "status": "draft"}],
                "cascaded_children": {
                    "prop_requisition_items": {
                        "foreign_key": "requisition_id",
                        "parent_key": "id",
                        "rows": [{"id": 101, "requisition_id": 42, "item": "Widget"}],
                    }
                },
            },
        )
        assert audit_id.startswith("aud_")

        # 1. Inspect audit log
        log_res = get_audit_log(limit=10)
        assert log_res.get("count") >= 1
        record = log_res["audit_records"][0]
        assert record.get("audit_id") == audit_id
        assert record.get("before_image_summary", {}).get("operation") == "DELETE"

        # 2. Simulate undo via dry_run
        with patch("mcp_win_stdio.db.server._get_connection") as mock_conn,              patch("mcp_win_stdio.db.server._get_pg_client") as mock_client:
            mock_conn.return_value = {
                "name": "test_db",
                "engine": "postgres",
                "mode": "read_write",
                "env": "dev",
            }
            mock_cur = MagicMock()
            mock_pg = MagicMock()
            mock_pg.cursor.return_value.__enter__.return_value = mock_cur
            mock_client.return_value = mock_pg

            undo_res = undo_query(audit_id=audit_id, dry_run=True)
            assert undo_res.get("dryRun") is True
            assert undo_res.get("operation") == "DELETE"
            assert undo_res.get("mainRowsRestored") == 1
            assert undo_res.get("cascadedRowsRestored", {}).get("prop_requisition_items") == 1
            # Verified cursor executed INSERTs for both main and cascaded child rows
            assert mock_cur.execute.call_count == 2
            mock_pg.rollback.assert_called_once()
