"""
Unit tests for PostgreSQL audit_database_health improvements.
"""

from unittest.mock import MagicMock, patch
import pytest


def test_audit_database_health_defaults_to_all_schemas():
    """Verify that audit_database_health defaults to None (audits all schemas)."""
    from mcp_win_stdio.db.server import audit_database_health

    fake_conn_info = {
        "engine": "postgres",
        "name": "mock_pg",
        "database": "mock_db",
        "url": "postgresql://user:pass@localhost:5432/mock_db",
    }

    mock_cur = MagicMock()
    mock_cur.__enter__.return_value = mock_cur
    mock_conn = MagicMock()
    mock_conn.cursor.return_value = mock_cur

    # Mock cursor responses
    # Query 0: schemas
    # Query 0b: stats_reset
    # Query 1: unindexed FKs
    # Query 2: unused indexes
    # Query 3: bloated tables
    mock_cur.fetchall.side_effect = [
        [{"nspname": "public"}, {"nspname": "auth"}, {"nspname": "props_management"}],
        [],  # FKs
        [
            {
                "schemaname": "public",
                "table_name": "users",
                "index_name": "idx_users_email",
                "idx_scan": 0,
                "raw_bytes": 16384,
                "index_size": "16 kB",
            }
        ],  # Unused indexes
        [],  # Bloated tables
    ]
    mock_cur.fetchone.return_value = {"stats_reset": None, "stats_age": None}

    with (
        patch("mcp_win_stdio.db.server._get_connection", return_value=fake_conn_info),
        patch("mcp_win_stdio.db.server._get_pg_client", return_value=mock_conn),
    ):
        res = audit_database_health(connection="mock_pg")

        assert res["audited_schema"] == "all"
        assert res["available_user_schemas"] == ["public", "auth", "props_management"]
        assert res["summary"]["unused_indexes_total"] == 1
        assert res["summary"]["unused_indexes_by_schema"] == {"public": 1}
        assert "idx_users_email" in res["unused_indexes"][0]["index"]


def test_audit_database_health_error_includes_traceback_and_step():
    """Verify that unexpected exceptions capture failing_step and traceback."""
    from mcp_win_stdio.db.server import audit_database_health

    fake_conn_info = {
        "engine": "postgres",
        "name": "mock_pg",
        "database": "mock_db",
        "url": "postgresql://user:pass@localhost:5432/mock_db",
    }

    mock_conn = MagicMock()
    mock_conn.cursor.side_effect = IndexError("tuple index out of range")

    with (
        patch("mcp_win_stdio.db.server._get_connection", return_value=fake_conn_info),
        patch("mcp_win_stdio.db.server._get_pg_client", return_value=mock_conn),
    ):
        res = audit_database_health(connection="mock_pg")

        assert res["error"] is True
        assert res["error_type"] == "IndexError"
        assert "tuple index out of range" in res["message"]
        assert "failing_step" in res
        assert "traceback" in res
