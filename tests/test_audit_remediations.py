"""
Regression tests for Deep Audit Medium-Severity Remediations (Findings 1-4):
  1. SQL CTE mutations bypassing write guardrails & before-image side-effects.
  2. Child-process stderr pipe draining (MCPProcess & ProcessSupervisor), redaction, and fallback.
  3. Failed discovery results not cached as permanent empty catalogs.
  4. manage_context(action='list_sessions' / 'session_info') caller-only isolation & trusted identity.
"""

import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ==============================================================================
# Finding 1: SQL CTE Mutations & Before-Image Safety
# ==============================================================================


class TestCteMutationSafeguards:
    def test_cte_unfiltered_delete_blocked_by_default(self):
        from mcp_win_stdio.db.server import _check_write_policy, _parse_modifying_statement

        sql = "WITH stale AS (SELECT id FROM accounts WHERE old = true) DELETE FROM accounts;"
        parsed = _parse_modifying_statement(sql)
        assert parsed is not None
        assert parsed["operation"] == "DELETE"
        assert parsed["table"] == "accounts"
        assert parsed["where"] is None
        err = _check_write_policy(parsed, allow_unfiltered=False)
        assert err is not None
        assert "WHERE" in err or "allow_unfiltered" in err

    def test_cte_unfiltered_update_blocked_by_default(self):
        from mcp_win_stdio.db.server import _check_write_policy, _parse_modifying_statement

        sql = "WITH target AS (SELECT id FROM users) UPDATE users SET active = false;"
        parsed = _parse_modifying_statement(sql)
        assert parsed is not None
        assert parsed["operation"] == "UPDATE"
        assert parsed["where"] is None
        err = _check_write_policy(parsed, allow_unfiltered=False)
        assert err is not None

    def test_data_modifying_cte_classified_and_blocked(self):
        from mcp_win_stdio.db.server import _check_write_policy, _parse_modifying_statement

        sql = (
            "WITH removed AS (DELETE FROM old_rows WHERE id = 1 RETURNING id) "
            "UPDATE accounts SET stale = true WHERE id IN (SELECT id FROM removed);"
        )
        parsed = _parse_modifying_statement(sql)
        assert parsed is not None
        assert parsed["operation"] == "DATA_MODIFYING_CTE"
        err = _check_write_policy(parsed, allow_unfiltered=False)
        assert err is not None
        assert "DATA_MODIFYING_CTE" in err or "allow_unfiltered" in err
        assert _check_write_policy(parsed, allow_unfiltered=True) is None

    def test_capture_before_image_never_executes_for_cte(self):
        from mcp_win_stdio.db.server import _capture_before_image, _parse_modifying_statement

        sql = "WITH ids AS (SELECT nextval('seq_x') AS id) DELETE FROM items WHERE id IN (SELECT id FROM ids);"
        parsed = _parse_modifying_statement(sql)
        assert parsed is not None
        mock_cur = MagicMock()
        result = _capture_before_image(mock_cur, parsed, "postgres")
        assert result is None
        mock_cur.execute.assert_not_called()

    def test_execute_query_reports_undo_unsupported_for_cte_mutation(self, tmp_path):
        from mcp_win_stdio.db import server as db_server

        mock_cur = MagicMock()
        mock_cur.rowcount = 2
        mock_cur.statusmessage = "DELETE 2"
        mock_conn = MagicMock()
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cur)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        conn_info = {"name": "test_pg", "engine": "postgres", "mode": "read_write", "env": "dev"}
        audit_file = tmp_path / "db_connections.json"

        with (
            patch.object(db_server, "DB_CONNECTIONS_FILE", audit_file),
            patch.object(db_server, "_get_connection", return_value=conn_info),
            patch.object(db_server, "_get_pg_client", return_value=mock_conn),
        ):
            res = db_server.execute_query(
                sql="WITH target AS (SELECT id FROM items WHERE id = 1) DELETE FROM items WHERE id IN (SELECT id FROM target);",
                connection="test_pg",
            )

        assert res.get("status") == "DELETE 2"
        assert res.get("undoSupported") is False
        assert "not available" in res.get("undoNotice", "").lower()


# ==============================================================================
# Finding 2: Child-Process Stderr Pipe Draining & Redaction
# ==============================================================================


class TestChildStderrDraining:
    def test_mcp_process_drains_large_stderr_without_deadlock_and_redacts(self):
        from mcp_win_stdio.server.process_pool import MCPProcess

        # Child writes >128KB to stderr (exceeding typical 4KB-64KB OS pipe buffers),
        # includes a secret, and then serves JSON-RPC initialize + ping over stdio.
        child_script = (
            "import sys, json\n"
            "for i in range(1500):\n"
            "    sys.stderr.write(f'log line {i} ' + ('x' * 90) + '\\n')\n"
            "sys.stderr.write('secret leak password=supersecretvalue123\\n')\n"
            "sys.stderr.flush()\n"
            "while True:\n"
            "    line = sys.stdin.readline()\n"
            "    if not line:\n"
            "        break\n"
            "    req = json.loads(line)\n"
            "    mid = req.get('id')\n"
            "    if mid is not None:\n"
            "        res = {'protocolVersion': '2024-11-05'} if req.get('method') == 'initialize' else {'ok': True}\n"
            "        sys.stdout.write(json.dumps({'jsonrpc': '2.0', 'id': mid, 'result': res}) + '\\n')\n"
            "        sys.stdout.flush()\n"
        )
        proc = MCPProcess("heavy_stderr_test", sys.executable, ["-u", "-c", child_script])
        try:
            proc.initialize()
            res = proc.send_request("ping", {}, timeout=10.0)
            assert res == {"ok": True}
            recent = proc.get_recent_stderr(500)
            assert "supersecretvalue123" not in recent
            assert "REDACTED" in recent
        finally:
            proc.kill_process_tree()

    def test_mcp_process_drain_continues_if_redaction_raises(self):
        from mcp_win_stdio.server.process_pool import MCPProcess

        child_script = (
            "import sys, json\n"
            "sys.stderr.write('line-before-error\\n')\n"
            "sys.stderr.write('line-after-error\\n')\n"
            "sys.stderr.flush()\n"
            "line = sys.stdin.readline()\n"
            "if line:\n"
            "    req = json.loads(line)\n"
            "    sys.stdout.write(json.dumps({'jsonrpc': '2.0', 'id': req['id'], 'result': {'protocolVersion': '2024-11-05'}}) + '\\n')\n"
            "    sys.stdout.flush()\n"
        )
        call_count = 0

        def flaky_redact(val):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ValueError("simulated redaction failure")
            return val

        with patch("mcp_win_stdio.server.process_pool.redact_sensitive_data", side_effect=flaky_redact):
            proc = MCPProcess("flaky_redact_test", sys.executable, ["-u", "-c", child_script])
            try:
                proc.initialize()
                recent = proc.get_recent_stderr(500)
                assert "[stderr redaction failed]" in recent
                assert "line-after-error" in recent
            finally:
                proc.kill_process_tree()

    def test_supervisor_drains_large_stderr_without_deadlock(self):
        from mcp_win_stdio.core.hub.models import ServerConfig, SupervisorConfig
        from mcp_win_stdio.core.hub.registry import HubRegistry
        from mcp_win_stdio.core.hub.supervisor import ProcessSupervisor

        child_script = (
            "import sys, json\n"
            "for i in range(1500):\n"
            "    sys.stderr.write(f'hub-log {i} ' + ('y' * 90) + '\\n')\n"
            "sys.stderr.write('token=hubsecret999\\n')\n"
            "sys.stderr.flush()\n"
            "while True:\n"
            "    line = sys.stdin.readline()\n"
            "    if not line:\n"
            "        break\n"
            "    req = json.loads(line)\n"
            "    mid = req.get('id')\n"
            "    if mid is not None:\n"
            "        method = req.get('method')\n"
            "        if method == 'initialize':\n"
            "            res = {'protocolVersion': '2024-11-05', 'capabilities': {}}\n"
            "        else:\n"
            "            res = {'pong': True}\n"
            "        sys.stdout.write(json.dumps({'jsonrpc': '2.0', 'id': mid, 'result': res}) + '\\n')\n"
            "        sys.stdout.flush()\n"
        )
        registry = HubRegistry()
        registry.register_server(
            ServerConfig(
                name="hub_stderr_srv",
                command=sys.executable,
                args=["-u", "-c", child_script],
                supervisor=SupervisorConfig(startup_timeout_seconds=10.0, probe_timeout_seconds=5.0),
            )
        )
        sup = ProcessSupervisor(registry=registry, auto_start_monitor=False)
        try:
            snap = sup.start("hub_stderr_srv")
            assert snap.state.value == "healthy"
            inst = sup._instances["hub_stderr_srv"]
            recent = inst.get_recent_stderr(500)
            assert "hubsecret999" not in recent
            assert "REDACTED" in recent
        finally:
            sup.shutdown()


# ==============================================================================
# Finding 3: Failed Discovery Caching
# ==============================================================================


class TestCatalogDiscoveryCaching:
    def test_failed_probe_not_cached_and_recovers_automatically(self, tmp_path):
        from mcp_win_stdio.server import catalog

        cache_file = tmp_path / "server_cache.json"
        mock_proc = MagicMock()
        mock_proc.list_tools.side_effect = [
            RuntimeError("temporary spawn failure"),
            [{"name": "recovered_tool", "description": "Works now", "inputSchema": {"type": "object"}}],
        ]

        with (
            patch.object(catalog, "_IN_MEMORY_CACHE", {}),
            patch.object(catalog, "SERVER_CACHE_FILE", cache_file),
            patch.object(catalog, "_introspect_in_process", return_value=None),
            patch.object(catalog, "_introspect_from_schemas", return_value=None),
            patch.object(catalog.GLOBAL_POOL, "get_or_spawn", return_value=mock_proc),
        ):
            # 1. First probe fails -> returns [], does NOT write cache
            first = catalog.get_server_tools("transient_srv")
            assert first == []
            assert "transient-srv" not in catalog._IN_MEMORY_CACHE
            assert not cache_file.exists()

            # 2. Server recovers -> next normal read retries without force_refresh
            second = catalog.get_server_tools("transient_srv")
            assert len(second) == 1
            assert second[0]["name"] == "recovered_tool"
            assert "transient-srv" in catalog._IN_MEMORY_CACHE
            assert cache_file.exists()

    def test_failed_force_refresh_preserves_existing_cache(self, tmp_path):
        from mcp_win_stdio.server import catalog

        cache_file = tmp_path / "server_cache.json"
        existing = [{"name": "cached_tool", "description": "Previously known", "parameters": {}}]
        cache_file.write_text(json.dumps({"stable-srv": {"tools": existing, "updated_at": 100.0}}))

        mem_cache = {"stable-srv": {"tools": existing, "updated_at": 100.0}}

        with (
            patch.object(catalog, "_IN_MEMORY_CACHE", mem_cache),
            patch.object(catalog, "SERVER_CACHE_FILE", cache_file),
            patch.object(catalog, "_introspect_in_process", return_value=None),
            patch.object(catalog, "_introspect_from_schemas", return_value=None),
            patch.object(catalog.GLOBAL_POOL, "get_or_spawn", side_effect=RuntimeError("offline")),
        ):
            # force_refresh=True fails -> returns [] to caller, preserves cache
            refreshed = catalog.get_server_tools("stable_srv", force_refresh=True)
            assert refreshed == []

            # Subsequent normal read still gets preserved cache
            normal = catalog.get_server_tools("stable_srv", force_refresh=False)
            assert len(normal) == 1
            assert normal[0]["name"] == "cached_tool"

    def test_legitimate_zero_tool_server_is_cached(self, tmp_path):
        from mcp_win_stdio.server import catalog

        cache_file = tmp_path / "server_cache.json"
        mock_proc = MagicMock()
        mock_proc.list_tools.return_value = []

        with (
            patch.object(catalog, "_IN_MEMORY_CACHE", {}),
            patch.object(catalog, "SERVER_CACHE_FILE", cache_file),
            patch.object(catalog, "_introspect_in_process", return_value=None),
            patch.object(catalog, "_introspect_from_schemas", return_value=None),
            patch.object(catalog.GLOBAL_POOL, "get_or_spawn", return_value=mock_proc),
        ):
            res = catalog.get_server_tools("resource_only_srv")
            assert res == []
            assert "resource-only-srv" in catalog._IN_MEMORY_CACHE
            assert cache_file.exists()


# ==============================================================================
# Finding 4: manage_context Session Isolation & Trusted Identity
# ==============================================================================


class TestSessionInfoIsolation:
    def _make_ctx(self, session_id: str):
        ctx = MagicMock()
        conn = MagicMock()
        conn.session_id = session_id
        sess = MagicMock()
        sess._connection = conn
        ctx.request_context.session = sess
        return ctx

    def test_session_info_and_list_sessions_are_caller_scoped(self):
        from mcp_win_stdio.core.context import GLOBAL_CONTEXT
        from mcp_win_stdio.server.server import manage_context

        GLOBAL_CONTEXT.clear()
        try:
            GLOBAL_CONTEXT.set("workspace", "/repo/alpha", session_id="alpha_sid")
            GLOBAL_CONTEXT.set("workspace", "/repo/beta", session_id="beta_sid")

            ctx_a = self._make_ctx("alpha_sid")
            for act in ("list_sessions", "session_info"):
                res = manage_context(action=act, value="beta_sid", ctx=ctx_a)
                assert res["status"] == "success"
                assert res["scope"] == "caller_only"
                assert len(res["sessions"]) == 1
                assert res["sessions"][0]["session_id"] == "alpha_sid"
                assert all(s["session_id"] != "beta_sid" for s in res["sessions"])
        finally:
            GLOBAL_CONTEXT.clear()

    def test_session_info_rejects_untrusted_spoofed_context(self):
        from mcp_win_stdio.server.server import manage_context

        class SpoofedCtx:
            session_id = "beta_sid"
            client_id = "beta_sid"

        with pytest.raises(RuntimeError, match="Unable to resolve trusted transport identity"):
            manage_context(action="session_info", ctx=SpoofedCtx())


# ==============================================================================
# Destructive-DDL Guardrails & Timeouts (db/server.py)
# ==============================================================================


class TestDestructiveDdlGuardrails:
    def test_destructive_ddl_blocked_by_default_and_string_literals_ignored(self, tmp_path):
        from mcp_win_stdio.db import server as db_server

        conn_info = {"name": "test_pg", "engine": "postgres", "mode": "read_write", "env": "dev"}
        audit_file = tmp_path / "db_connections.json"

        blocked_cases = [
            ("ALTER TABLE props_management.prop_gatepass DROP COLUMN IF EXISTS receiver_phone_number;", "DROP_COLUMN"),
            ("DROP TABLE users;", "DROP_TABLE"),
            ("DROP SCHEMA staging CASCADE;", "DROP_SCHEMA"),
            ("DROP DATABASE old_db;", "DROP_DATABASE"),
            ("DO $$ BEGIN DROP TABLE users; END $$;", "DYNAMIC_OR_AMBIGUOUS_DDL"),
        ]

        with (
            patch.object(db_server, "DB_CONNECTIONS_FILE", audit_file),
            patch.object(db_server, "_get_connection", return_value=conn_info),
            patch.object(db_server, "_get_pg_client") as mock_pg,
        ):
            for sql, expected_kind in blocked_cases:
                res = db_server.execute_query(sql=sql, connection="test_pg")
                assert res.get("error") is True
                assert res.get("destructiveDdlKind") == expected_kind
                assert res.get("undoSupported") is False
                assert "undo_query" in res.get("message", "")
            mock_pg.assert_not_called()

        # String literal containing DROP TABLE should NOT trigger destructive DDL
        assert db_server._classify_destructive_ddl("INSERT INTO logs (msg) VALUES ('DROP TABLE users');") is None

    def test_dry_run_destructive_ddl_never_executes_against_target_db(self, tmp_path):
        from mcp_win_stdio.db import server as db_server

        pg_info = {"name": "test_pg", "engine": "postgres", "mode": "read_write", "env": "dev"}
        mysql_info = {"name": "test_mysql", "engine": "mysql", "mode": "read_write", "env": "dev"}
        audit_file = tmp_path / "db_connections.json"

        with (
            patch.object(db_server, "DB_CONNECTIONS_FILE", audit_file),
            patch.object(db_server, "_get_connection", return_value=pg_info),
            patch.object(db_server, "_get_pg_client") as mock_pg,
        ):
            res = db_server.execute_query(
                sql="ALTER TABLE t DROP COLUMN c;",
                dry_run=True,
                connection="test_pg",
            )
            assert res["dryRun"] is True
            assert res["executed"] is False
            assert res["status"] == "VALIDATED (NOT EXECUTED)"
            assert res["undoSupported"] is False
            assert res["destructiveOperations"][0]["kind"] == "DROP_COLUMN"
            mock_pg.assert_not_called()

        # Any MySQL DDL (even CREATE TABLE) must not execute on dry_run=True because MySQL DDL implicitly commits
        with (
            patch.object(db_server, "DB_CONNECTIONS_FILE", audit_file),
            patch.object(db_server, "_get_connection", return_value=mysql_info),
            patch.object(db_server, "_get_mysql_client") as mock_mysql,
        ):
            res = db_server.execute_query(
                sql="CREATE TABLE new_tbl (id INT);",
                dry_run=True,
                connection="test_mysql",
            )
            assert res["dryRun"] is True
            assert res["executed"] is False
            assert res["status"] == "VALIDATED (NOT EXECUTED)"
            mock_mysql.assert_not_called()

    def test_live_postgres_ddl_applies_timeouts_and_reports_undo_unsupported(self, tmp_path):
        from mcp_win_stdio.db import server as db_server

        mock_cur = MagicMock()
        mock_cur.rowcount = -1
        mock_cur.statusmessage = "ALTER TABLE"
        mock_conn = MagicMock()
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cur)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        pg_info = {"name": "test_pg", "engine": "postgres", "mode": "read_write", "env": "dev"}
        audit_file = tmp_path / "db_connections.json"

        with (
            patch.object(db_server, "DB_CONNECTIONS_FILE", audit_file),
            patch.object(db_server, "_get_connection", return_value=pg_info),
            patch.object(db_server, "_get_pg_client", return_value=mock_conn),
        ):
            res = db_server.execute_query(
                sql="ALTER TABLE prop_gatepass DROP COLUMN receiver_phone_number;",
                allow_destructive_ddl=True,
                lock_timeout_ms=2500,
                statement_timeout_ms=15000,
                connection="test_pg",
            )
            assert res["status"] == "ALTER TABLE"
            assert res["undoSupported"] is False
            assert "undo_query" in res["undoNotice"]
            assert res["lockTimeoutMs"] == 2500
            assert res["statementTimeoutMs"] == 15000
            executed_sqls = [c.args[0] for c in mock_cur.execute.call_args_list]
            assert "SET LOCAL lock_timeout = '2500ms';" in executed_sqls
            assert "SET LOCAL statement_timeout = '15000ms';" in executed_sqls

    def test_live_mysql_ddl_restores_lock_wait_timeout_without_max_execution_time(self, tmp_path):
        from mcp_win_stdio.db import server as db_server

        mock_cur = MagicMock()
        mock_cur.rowcount = 0
        mock_cur.fetchone.return_value = {"val": 31536000}
        mock_conn = MagicMock()
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cur)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        mysql_info = {"name": "test_mysql", "engine": "mysql", "mode": "read_write", "env": "dev"}
        audit_file = tmp_path / "db_connections.json"

        with (
            patch.object(db_server, "DB_CONNECTIONS_FILE", audit_file),
            patch.object(db_server, "_get_connection", return_value=mysql_info),
            patch.object(db_server, "_get_mysql_client", return_value=mock_conn),
        ):
            res = db_server.execute_query(
                sql="DROP TABLE temp_items;",
                allow_destructive_ddl=True,
                lock_timeout_ms=4000,
                connection="test_mysql",
            )
            assert res["status"] == "SUCCESS"
            assert res["undoSupported"] is False
            assert res["lockTimeoutSeconds"] == 4
            assert "not supported for MySQL DDL" in res["lockTimeoutNote"]
            executed_sqls = [c.args[0] for c in mock_cur.execute.call_args_list]
            assert "SET SESSION lock_wait_timeout = 4;" in executed_sqls
            assert "SET SESSION lock_wait_timeout = 31536000;" in executed_sqls
            assert not any("max_execution_time" in s.lower() for s in executed_sqls)


# ==============================================================================
# Pre-Publish Audit Blockers (Tunnel Pipe Draining & publish_safe.py)
# ==============================================================================


class TestPrePublishBlockers:
    def test_tunnel_provider_drains_large_logs_after_discovery_without_blocking(self):
        import subprocess
        from mcp_win_stdio.core.tunnel import MwsTunnelManager

        # Fake provider writes URL, then floods both stdout and stderr (>128KB each)
        # while staying alive until terminated. Blocking pipe = child stalls and won't exit cleanly.
        provider_script = (
            "import sys, time\n"
            "sys.stdout.write('{\"lvl\":\"info\",\"url\":\"https://fake-tunnel-drain.ngrok.app\"}\\n')\n"
            "sys.stdout.flush()\n"
            "for i in range(1500):\n"
            "    sys.stdout.write(f'out {i} ' + ('a' * 90) + '\\n')\n"
            "    sys.stderr.write(f'err {i} ' + ('b' * 90) + '\\n')\n"
            "sys.stdout.write('password=tunnel_secret_xyz\\n')\n"
            "sys.stdout.flush()\n"
            "sys.stderr.flush()\n"
            "time.sleep(0.2)\n"
        )
        real_proc = subprocess.Popen(
            [sys.executable, "-u", "-c", provider_script],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            stdin=subprocess.DEVNULL,
        )
        mgr = MwsTunnelManager(port=8999, mode="read_only", auth_mode="bearer", token="tok", provider="ngrok")
        try:
            with (
                patch("mcp_win_stdio.core.tunnel.MwsTunnelManager.is_ngrok_installed", return_value=True),
                patch("mcp_win_stdio.core.tunnel.subprocess.Popen", return_value=real_proc),
            ):
                url = mgr.start_ngrok_tunnel(timeout=10.0)
                assert url == "https://fake-tunnel-drain.ngrok.app"
                # Wait for subprocess to finish writing all 270KB+ without blocking
                rc = real_proc.wait(timeout=10.0)
                assert rc == 0
                # Ring buffers stay bounded at maxlen=200
                assert len(mgr._proc_stdout_buffer) <= 200
                assert len(mgr._proc_stderr_buffer) <= 200
                logs = mgr._collect_provider_logs(real_proc)
                assert "tunnel_secret_xyz" not in logs
        finally:
            mgr.stop()

    def test_direct_mode_enables_dns_rebinding_protection(self):
        from mcp_win_stdio.core.tunnel import MwsTunnelManager

        captured = {}

        def fake_app(transport_security=None):
            captured["sec"] = transport_security
            app = MagicMock()
            return app

        mgr = MwsTunnelManager(
            port=8998,
            mode="read_only",
            auth_mode="bearer",
            token="tok",
            provider="direct",
            public_url="https://10.0.0.5:8998",
        )
        try:
            with (
                patch("mcp_win_stdio.core.tunnel.mcp.streamable_http_app", side_effect=fake_app),
                patch("mcp_win_stdio.core.tunnel.uvicorn.Server") as mock_srv_cls,
            ):
                mock_srv = MagicMock()
                mock_srv.started = True
                mock_srv_cls.return_value = mock_srv
                mgr.start_local_bridge()
                sec = captured["sec"]
                assert sec.enable_dns_rebinding_protection is True
                assert "10.0.0.5" in sec.allowed_hosts
                assert "127.0.0.1:*" in sec.allowed_hosts
        finally:
            mgr.stop()

    def test_publish_safe_exact_version_matching_and_dry_run_summary(self, tmp_path):
        import importlib.util

        spec = importlib.util.spec_from_file_location("publish_safe", Path("scripts/publish_safe.py"))
        assert spec and spec.loader
        pub = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(pub)

        # Create real 0.5.5 artifacts alongside stale 0.5.50 and differently named subpackage artifacts
        (tmp_path / "mcp_win_stdio-0.5.5-py3-none-any.whl").write_bytes(b"w1")
        (tmp_path / "mcp_win_stdio-0.5.5.tar.gz").write_bytes(b"s1")
        (tmp_path / "mcp_win_stdio-0.5.50-py3-none-any.whl").write_bytes(b"stale")
        (tmp_path / "mcp_win_stdio-0.5.50.tar.gz").write_bytes(b"stale")
        (tmp_path / "mcp_win_stdio_db-0.5.5-py3-none-any.whl").write_bytes(b"w2")
        (tmp_path / "mcp_win_stdio_db-0.5.5.tar.gz").write_bytes(b"s2")

        with patch.object(pub, "DIST_DIR", tmp_path):
            root_files = pub.get_artifacts_for_package("mcp_win_stdio", "0.5.5")
            assert sorted(f.name for f in root_files) == [
                "mcp_win_stdio-0.5.5-py3-none-any.whl",
                "mcp_win_stdio-0.5.5.tar.gz",
            ]
            db_files = pub.get_artifacts_for_package("mcp_win_stdio_db", "0.5.5")
            assert sorted(f.name for f in db_files) == [
                "mcp_win_stdio_db-0.5.5-py3-none-any.whl",
                "mcp_win_stdio_db-0.5.5.tar.gz",
            ]

        # Test dry-run summary output
        import io
        from contextlib import redirect_stdout

        buf = io.StringIO()
        with (
            patch.object(pub, "DIST_DIR", tmp_path),
            patch.object(pub, "check_is_published", return_value=False),
            patch.object(sys, "argv", ["publish_safe.py", "--dry-run", "--only", "mcp-win-stdio-db", "--version", "0.5.5"]),
            redirect_stdout(buf),
        ):
            pub.main()
        out = buf.getvalue()
        assert "No packages were uploaded to PyPI" in out
        assert "live on PyPI!" not in out

        # Verify --token CLI option is removed
        with patch.object(sys, "argv", ["publish_safe.py", "--token", "secret123"]):
            with pytest.raises(SystemExit):
                pub.main()


class TestArtifactLifecycleAndIsolation:
    def test_production_spill_and_reap_enforce_ttl_and_size_cap_even_without_new_writes(self, tmp_path, monkeypatch):
        import os
        import time as pytime
        import mcp_win_stdio.core.artifacts as artifacts
        from mcp_win_stdio.server.process_pool import ProcessPool

        art_dir = tmp_path / "artifacts"
        art_dir.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(artifacts, "ARTIFACTS_DIR", art_dir)
        monkeypatch.setattr(artifacts, "PRUNE_INTERVAL_SECONDS", 0.0)
        monkeypatch.setattr(artifacts, "MAX_DIR_BYTES", 200)
        artifacts._LAST_PRUNE_AT_BY_DIR.clear()

        now = pytime.time()
        expired_file = art_dir / "art_20250101_deadbeef.json"
        expired_file.write_text('{"rows": ["expired"]}', encoding="utf-8")
        os.utime(expired_file, (now - 25 * 3600, now - 25 * 3600))

        older_overcap = art_dir / "art_20250102_11112222.json"
        older_overcap.write_text("{" + '"x":"' + ("a" * 160) + '"}', encoding="utf-8")
        os.utime(older_overcap, (now - 3600, now - 3600))

        newer_file = art_dir / "art_20250103_33334444.json"
        newer_file.write_text("{" + '"x":"' + ("b" * 100) + '"}', encoding="utf-8")
        os.utime(newer_file, (now - 60, now - 60))

        # Small non-spilling payload still invokes periodic pruning -> expired & over-cap oldest files removed
        spilled, payload = artifacts.maybe_spill_to_artifact({"ok": True}, threshold_bytes=4096)
        assert spilled is False
        assert payload == {"ok": True}
        assert not expired_file.exists()
        assert not older_overcap.exists()
        assert newer_file.exists()

        # Re-add an expired artifact and verify ProcessPool.reap_idle() also triggers pruning
        expired2 = art_dir / "art_20250104_cafebabe.json"
        expired2.write_text('{"rows": ["stale"]}', encoding="utf-8")
        os.utime(expired2, (now - 26 * 3600, now - 26 * 3600))

        pool = ProcessPool()
        pool.reap_idle()
        assert not expired2.exists()

    def test_active_read_refreshes_ttl_while_expired_artifact_is_pruned(self, tmp_path, monkeypatch):
        import os
        import time as pytime
        import mcp_win_stdio.core.artifacts as artifacts

        art_dir = tmp_path / "artifacts"
        art_dir.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(artifacts, "ARTIFACTS_DIR", art_dir)
        monkeypatch.setattr(artifacts, "PRUNE_INTERVAL_SECONDS", 0.0)
        artifacts._LAST_PRUNE_AT_BY_DIR.clear()

        now = pytime.time()
        active_file = art_dir / "art_20250105_aaaa1111.json"
        active_file.write_text('{"rows": [{"id": 1}, {"id": 2}]}', encoding="utf-8")
        # 23 hours old: not yet expired; reading refreshes mtime
        os.utime(active_file, (now - 23 * 3600, now - 23 * 3600))

        stale_file = art_dir / "art_20250105_bbbb2222.json"
        stale_file.write_text('{"rows": [{"id": 99}]}', encoding="utf-8")
        os.utime(stale_file, (now - 25 * 3600, now - 25 * 3600))

        # Reading active artifact refreshes its mtime AND prunes already-expired stale artifact
        active_res = artifacts.read_artifact_payload("art_20250105_aaaa1111")
        assert active_res["total_items"] == 2
        assert active_file.stat().st_mtime >= now - 5
        assert not stale_file.exists()

        # Attempting to read an expired handle prunes it and reports expired/not found
        expired_res = artifacts.read_artifact_payload("art_20250105_bbbb2222")
        assert expired_res["isError"] is True
        assert "expired" in expired_res["error"].lower()

    def test_background_reaper_thread_lifecycle_and_periodic_reap(self, tmp_path, monkeypatch):
        import time as pytime
        import mcp_win_stdio.core.artifacts as artifacts
        from mcp_win_stdio.server.process_pool import ProcessPool

        art_dir = tmp_path / "artifacts"
        art_dir.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(artifacts, "ARTIFACTS_DIR", art_dir)
        monkeypatch.setattr(artifacts, "PRUNE_INTERVAL_SECONDS", 0.0)
        artifacts._LAST_PRUNE_AT_BY_DIR.clear()

        now = pytime.time()
        expired_file = art_dir / "art_20250106_99998888.json"
        expired_file.write_text('{"rows": ["stale"]}', encoding="utf-8")
        import os
        os.utime(expired_file, (now - 25 * 3600, now - 25 * 3600))

        pool = ProcessPool()
        try:
            assert pool._reaper_thread is None
            pool.start_background_reaper(check_interval_seconds=0.1)
            assert pool._reaper_thread is not None
            assert pool._reaper_thread.is_alive()

            # Wait briefly for background loop iteration
            deadline = pytime.time() + 2.0
            while pytime.time() < deadline:
                if not expired_file.exists():
                    break
                pytime.sleep(0.05)

            assert not expired_file.exists(), "Background reaper failed to prune expired artifact"
        finally:
            pool.shutdown_all()
            assert pool._reaper_thread is None
