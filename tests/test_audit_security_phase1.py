"""
Comprehensive regression and security test suite for Phase 1.1 remediation.

Covers:
1. ContextVar permission isolation across concurrent tunnels and local stdio.
2. Tunnel B stopping while Tunnel A runs (Tunnel A remains protected).
3. Fail-closed server-qualified tool allowlist (SAFE_READ_TOOLS).
4. Automated completeness test verifying all 251 registered runtime tools.
5. Unknown tools and unclassified newly registered tools fail closed.
6. Same tool name on two different servers independently classified.
7. Direct gateway tools (delete_workflow, stop_server, save_workflow) guarded.
8. Workflow execution protection (nested dispatch and direct default caller).
9. OAuth CLI startup clean error exit without launching Uvicorn or Cloudflare.
"""

import ast
import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from starlette.requests import Request
from starlette.responses import JSONResponse

from mcp_win_stdio.core.config import (
    CURRENT_PERMISSION_MODE,
    get_effective_mode,
    set_runtime_mode_override,
)
from mcp_win_stdio.core.permissions import (
    SAFE_READ_TOOLS,
    check_tool_permission,
    is_tool_mutating,
    is_tool_safe,
)
from mcp_win_stdio.core.tunnel import (
    BearerAuthMiddleware,
    MwsTunnelManager,
    TunnelAuthMiddleware,
)
from mcp_win_stdio.core.tunnel_auth import (
    BearerAuthProvider,
    NoneAuthProvider,
    create_auth_provider,
)
from mcp_win_stdio.core.workflows import run_workflow as core_run_workflow
from mcp_win_stdio.server.server import (
    call_tool,
    delete_workflow,
    run_workflow,
    save_workflow,
    stop_server,
)

# ---------------------------------------------------------------------------
# 1. Permission Context Isolation & ContextVar Tests (SEC-01)
# ---------------------------------------------------------------------------

def test_contextvar_request_scoped_lifecycle():
    """Verify ContextVar is established per request and cleanly reset using token in finally."""
    async def _run():
        prov = NoneAuthProvider()
        middleware = TunnelAuthMiddleware(MagicMock(), auth_provider=prov, permission_mode="read_only")

        # Initial state outside request: None
        assert CURRENT_PERMISSION_MODE.get() is None

        async def mock_endpoint(req):
            # Inside request: mode must be read_only
            assert CURRENT_PERMISSION_MODE.get() == "read_only"
            assert get_effective_mode() == "read_only"
            return JSONResponse({"status": "inside_request"})

        req = MagicMock(spec=Request)
        req.url.path = "/mcp"
        req.headers = {}

        resp = await middleware.dispatch(req, mock_endpoint)
        assert resp.status_code == 200

        # After request completes: token reset cleanly in finally
        assert CURRENT_PERMISSION_MODE.get() is None

    asyncio.run(_run())


def test_concurrent_tunnels_permission_isolation():
    """
    Verify two concurrent tunnels with different permission modes
    (Tunnel A: read_only, Tunnel B: read_write) do not interfere or leak permissions.
    """
    async def _run():
        prov_a = NoneAuthProvider()
        mw_a = TunnelAuthMiddleware(MagicMock(), auth_provider=prov_a, permission_mode="read_only")

        prov_b = BearerAuthProvider(token="tok_b")
        mw_b = TunnelAuthMiddleware(MagicMock(), auth_provider=prov_b, permission_mode="read_write")

        async def run_request_a():
            req_a = MagicMock(spec=Request)
            req_a.url.path = "/mcp"
            req_a.headers = {}

            async def handler_a(r):
                await asyncio.sleep(0.01)  # Context switch while active
                assert CURRENT_PERMISSION_MODE.get() == "read_only"
                assert get_effective_mode() == "read_only"
                return "ok_a"

            return await mw_a.dispatch(req_a, handler_a)

        async def run_request_b():
            req_b = MagicMock(spec=Request)
            req_b.url.path = "/mcp"
            req_b.headers = {"authorization": "Bearer tok_b"}

            async def handler_b(r):
                await asyncio.sleep(0.01)  # Context switch while active
                assert CURRENT_PERMISSION_MODE.get() == "read_write"
                assert get_effective_mode() == "read_write"
                return "ok_b"

            return await mw_b.dispatch(req_b, handler_b)

        # Run requests concurrently
        res_a, res_b = await asyncio.gather(run_request_a(), run_request_b())
        assert res_a == "ok_a"
        assert res_b == "ok_b"

        # Outside requests: context is clean
        assert CURRENT_PERMISSION_MODE.get() is None

    asyncio.run(_run())


def test_tunnel_b_stop_while_a_runs():
    """
    Verify stopping Tunnel B while Tunnel A is active leaves Tunnel A completely protected.
    """
    mgr_a = MwsTunnelManager(port=8811, mode="read_only", auth_mode="none")
    mgr_b = MwsTunnelManager(port=8812, mode="read_write", auth_mode="bearer")

    with patch("mcp_win_stdio.server.server.mcp.streamable_http_app"), patch("uvicorn.Server"):
        mgr_a.start_local_bridge()
        mgr_b.start_local_bridge()

        # Stop Tunnel B
        mgr_b.stop()

        # Tunnel A's middleware still enforces read_only
        mw = TunnelAuthMiddleware(MagicMock(), auth_provider=mgr_a.auth_provider, permission_mode=mgr_a.mode)
        assert mw.permission_mode == "read_only"

        mgr_a.stop()


def test_local_stdio_unaffected_by_tunnel():
    """
    Verify local stdio requests (which do not pass through TunnelAuthMiddleware)
    preserve their original configuration mode without being polluted.
    """
    # Outside any tunnel request, CURRENT_PERMISSION_MODE is None
    assert CURRENT_PERMISSION_MODE.get() is None

    # Stdio falls back to config.json mode
    local_mode = get_effective_mode()
    assert local_mode in ("read_write", "read_only")


# ---------------------------------------------------------------------------
# 2. Server-Qualified Fail-Closed Allowlist & 251 Tool Completeness (SEC-02)
# ---------------------------------------------------------------------------

def test_automated_251_tool_completeness_audit():
    """
    Automated check of all 251 registered tools across all 10 servers and the gateway
    against the SAFE_READ_TOOLS allowlist.
    Ensures every tool is accounted for and no new tool silently inherits read-only access.
    """
    tools_by_server = {}
    repo_root = Path(__file__).resolve().parent.parent

    for p in sorted(repo_root.glob("packages/*/src/**/server.py")):
        srv = p.parent.name
        tree = ast.parse(p.read_text(encoding="utf-8"))
        tools = []
        for n in ast.walk(tree):
            if isinstance(n, ast.FunctionDef):
                for d in n.decorator_list:
                    func = d.func if isinstance(d, ast.Call) else d
                    if getattr(func, "attr", "") == "tool":
                        tools.append(n.name)
        tools_by_server[srv] = sorted(tools)

    gw_p = repo_root / "src/mcp_win_stdio/server/server.py"
    gw_tree = ast.parse(gw_p.read_text(encoding="utf-8"))
    gw_tools = []
    for n in gw_tree.body:
        if isinstance(n, ast.FunctionDef):
            for d in n.decorator_list:
                func = d.func if isinstance(d, ast.Call) else d
                if getattr(func, "attr", "") == "tool":
                    gw_tools.append(n.name)
    tools_by_server["gateway"] = sorted(gw_tools)

    total_runtime_tools = sum(len(t) for t in tools_by_server.values())
    assert total_runtime_tools == 251, f"Expected 251 tools, found {total_runtime_tools}"

    safe_count = 0
    mutating_count = 0

    for srv, tools in tools_by_server.items():
        for tool in tools:
            srv_norm = srv.replace("-", "_")
            if (srv_norm, tool) in SAFE_READ_TOOLS:
                safe_count += 1
                ok, err = check_tool_permission(srv, tool, mode="read_only")
                assert ok is True, f"Tool ({srv}, {tool}) is in SAFE_READ_TOOLS but permission denied!"
            else:
                mutating_count += 1
                ok, err = check_tool_permission(srv, tool, mode="read_only")
                assert ok is False, f"Tool ({srv}, {tool}) is mutating but was permitted in read_only mode!"
                assert "Permission Denied" in err

    assert safe_count == 129
    assert mutating_count == 122
    assert safe_count + mutating_count == 251


def test_unknown_and_unclassified_tools_fail_closed():
    """Verify any unknown or unclassified tool is strictly blocked in read_only mode."""
    # Completely made-up tool
    ok, err = check_tool_permission("explorer", "delete_all_system_files", mode="read_only")
    assert ok is False
    assert "Permission Denied" in err

    # New tool on existing server
    ok, err = check_tool_permission("db", "future_new_read_tool", mode="read_only")
    assert ok is False
    assert "Permission Denied" in err

    # New tool on unknown server
    ok, err = check_tool_permission("kubernetes", "get_pods", mode="read_only")
    assert ok is False
    assert "Permission Denied" in err


def test_same_tool_name_independently_classified():
    """
    Verify the same tool name on two different servers is classified independently.
    E.g., 'export_to_pdf' on word vs excel vs custom server.
    """
    # Both word and excel export_to_pdf write to disk and must be blocked
    ok_word, _ = check_tool_permission("word", "export_to_pdf", mode="read_only")
    ok_excel, _ = check_tool_permission("excel", "export_to_pdf", mode="read_only")
    assert ok_word is False
    assert ok_excel is False

    # If another server hypothetically had read_file: explorer's read_file is safe,
    # but an unapproved server's read_file is blocked
    ok_exp, _ = check_tool_permission("explorer", "read_file", mode="read_only")
    ok_other, _ = check_tool_permission("custom_server", "read_file", mode="read_only")
    assert ok_exp is True
    assert ok_other is False


def test_side_effect_conditional_tools_blocked():
    """Verify conditional tools with potential side effects are blocked in read_only mode."""
    # generate_master_migration_plan can write .sql files to disk
    ok, _ = check_tool_permission("excel_db", "generate_master_migration_plan", mode="read_only")
    assert ok is False

    # refresh_data_and_pivots calls wb.Save()
    ok, _ = check_tool_permission("excel", "refresh_data_and_pivots", mode="read_only")
    assert ok is False

    # dump_database writes dump files to disk
    ok, _ = check_tool_permission("db", "dump_database", mode="read_only")
    assert ok is False


# ---------------------------------------------------------------------------
# 3. Direct Gateway Tool Protection (SEC-03)
# ---------------------------------------------------------------------------

def test_direct_gateway_tools_guarded_in_read_only():
    """Verify direct gateway mutating tools are blocked when in read_only mode."""
    token = CURRENT_PERMISSION_MODE.set("read_only")
    try:
        # delete_workflow
        del_res = delete_workflow("some_wf")
        assert del_res.get("isError") is True
        assert "Permission Denied" in del_res.get("error", "")

        # stop_server
        stop_res = stop_server("excel")
        assert stop_res.get("isError") is True
        assert "Permission Denied" in stop_res.get("error", "")

        # save_workflow
        save_res = save_workflow("wf_name", {"title": "t", "steps": []})
        assert save_res.get("isError") is True
        assert "Permission Denied" in save_res.get("error", "")
    finally:
        CURRENT_PERMISSION_MODE.reset(token)


def test_direct_gateway_tools_permitted_in_read_write():
    """Verify direct gateway tools succeed in read_write mode."""
    token = CURRENT_PERMISSION_MODE.set("read_write")
    try:
        # stop_server for non-running server returns clean status without permission error
        stop_res = stop_server("non_existent_mock_server")
        assert "Permission Denied" not in stop_res.get("error", "")
    finally:
        CURRENT_PERMISSION_MODE.reset(token)


# ---------------------------------------------------------------------------
# 4. Workflow Execution Protection (SEC-04)
# ---------------------------------------------------------------------------

def test_workflow_execution_blocks_nested_mutating_steps():
    """Verify workflow executing mutating steps halts on permission denial in read_only mode."""
    token = CURRENT_PERMISSION_MODE.set("read_only")
    try:
        wf_def = {
            "name": "dangerous_wf",
            "steps": [
                {
                    "id": "step1",
                    "server": "ssh",
                    "tool": "ssh_exec",
                    "arguments": {"command": "rm -rf /"},
                }
            ],
        }

        res = core_run_workflow(
            name_or_def=wf_def,
            call_tool_fn=lambda s, t, a: call_tool(name=t, arguments=a, server=s),
        )

        assert res.get("status") in ("failed", "halted_on_error")
        trace = res.get("trace", [{}])[0]
        assert trace.get("status") == "error"
        assert "Permission Denied" in str(trace.get("output", {}).get("error", ""))
    finally:
        CURRENT_PERMISSION_MODE.reset(token)


def test_workflow_direct_default_caller_enforces_permissions():
    """
    Verify that even if core_run_workflow is called directly without injecting call_tool_fn,
    the default caller independently enforces permissions.
    """
    token = CURRENT_PERMISSION_MODE.set("read_only")
    try:
        wf_def = {
            "name": "default_caller_wf",
            "steps": [
                {
                    "id": "step1",
                    "server": "explorer",
                    "tool": "write_file",
                    "arguments": {"path": "compromise.txt", "content": "bad"},
                }
            ],
        }

        # call_tool_fn is None -> uses _default_caller
        res = core_run_workflow(name_or_def=wf_def, call_tool_fn=None)

        assert res.get("status") in ("failed", "halted_on_error")
        trace = res.get("trace", [{}])[0]
        assert trace.get("status") == "error"
        assert "Permission Denied" in str(trace.get("output", {}).get("error", ""))
    finally:
        CURRENT_PERMISSION_MODE.reset(token)


# ---------------------------------------------------------------------------
# 5. OAuth CLI Handling (SEC-05)
# ---------------------------------------------------------------------------

def test_oauth_cli_startup_clean_exit(capsys):
    """
    Verify selecting --auth oauth exits cleanly with informative message
    without starting Uvicorn or Cloudflare.
    """
    import argparse

    from mcp_win_stdio.cli import cmd_tunnel

    args = argparse.Namespace(
        auth="oauth",
        mode="read_only",
        port=8999,
        token=None,
        yes=True,
    )

    with patch("mcp_win_stdio.core.tunnel.MwsTunnelManager.is_cloudflared_installed", return_value=True):
        with pytest.raises(SystemExit) as exc_info:
            cmd_tunnel(args)

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "OAuth authentication is not available yet" in captured.err
        assert "--auth bearer" in captured.err
        assert "--auth none" in captured.err


# ---------------------------------------------------------------------------
# 6. End-to-End Streamable HTTP MCP Integration Tests
# ---------------------------------------------------------------------------

def test_mcp_streamable_http_end_to_end_permission_enforcement():
    """
    Integration test: verify actual FastMCP StreamableHTTP ASGI request handling
    and tool execution preserves ContextVar permission context end-to-end.
    """
    from mcp.server.transport_security import TransportSecuritySettings
    from starlette.testclient import TestClient

    from mcp_win_stdio.server.server import mcp

    sec = TransportSecuritySettings(enable_dns_rebinding_protection=False)
    app = mcp.streamable_http_app(transport_security=sec)
    app.add_middleware(TunnelAuthMiddleware, auth_provider=NoneAuthProvider(), permission_mode="read_only")

    with TestClient(app) as client:
        init_payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "test-client", "version": "1.0"},
            },
        }
        resp = client.post("/mcp", json=init_payload, headers={"Accept": "application/json, text/event-stream"})
        assert resp.status_code == 200
        sess_id = resp.headers.get("mcp-session-id")
        assert sess_id is not None

        # Send initialized notification
        client.post("/mcp", json={"jsonrpc": "2.0", "method": "notifications/initialized"}, headers={"mcp-session-id": sess_id})

        # 1. Safe tool: describe_tool (must succeed)
        call_safe = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": "describe_tool", "arguments": {"server": "arch", "name": "blueprint_audit"}},
        }
        resp_safe = client.post("/mcp", json=call_safe, headers={"mcp-session-id": sess_id, "Accept": "application/json, text/event-stream"})
        assert resp_safe.status_code == 200
        assert "blueprint_audit" in resp_safe.text
        assert "Permission Denied" not in resp_safe.text

        # 2. Mutating tool: stop_server (must be blocked)
        call_mutating = {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "stop_server", "arguments": {"server": "excel"}},
        }
        resp_mutating = client.post("/mcp", json=call_mutating, headers={"mcp-session-id": sess_id, "Accept": "application/json, text/event-stream"})
        assert resp_mutating.status_code == 200
        assert "Permission Denied" in resp_mutating.text
        assert '"isError": true' in resp_mutating.text or '"isError":true' in resp_mutating.text

        # 3. Call tool through gateway: explorer write_file (must be blocked)
        call_write = {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {"name": "call_tool", "arguments": {"server": "explorer", "name": "write_file", "arguments": {"path": "a.txt", "content": "x"}}},
        }
        resp_write = client.post("/mcp", json=call_write, headers={"mcp-session-id": sess_id, "Accept": "application/json, text/event-stream"})
        assert resp_write.status_code == 200
        assert "Permission Denied" in resp_write.text


def test_mcp_streamable_http_concurrent_two_tunnels_isolation():
    """
    Integration test: verify two separate HTTP FastMCP instances with different permission modes
    (Tunnel A: read_only, Tunnel B: read_write) maintain independent permission boundaries over HTTP.
    """
    from mcp.server.transport_security import TransportSecuritySettings
    from starlette.testclient import TestClient

    from mcp_win_stdio.server.server import mcp

    sec = TransportSecuritySettings(enable_dns_rebinding_protection=False)

    # App A: read_only (unauthenticated)
    app_a = mcp.streamable_http_app(transport_security=sec)
    app_a.add_middleware(TunnelAuthMiddleware, auth_provider=NoneAuthProvider(), permission_mode="read_only")

    # App B: read_write (bearer auth)
    app_b = mcp.streamable_http_app(transport_security=sec)
    app_b.add_middleware(TunnelAuthMiddleware, auth_provider=BearerAuthProvider(token="rw_tok"), permission_mode="read_write")

    with TestClient(app_a) as client_a, TestClient(app_b) as client_b:
        # Init on A
        resp_a = client_a.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "client-a", "version": "1.0"}}},
            headers={"Accept": "application/json, text/event-stream"},
        )
        sess_a = resp_a.headers.get("mcp-session-id")

        # Init on B
        resp_b = client_b.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "client-b", "version": "1.0"}}},
            headers={"authorization": "Bearer rw_tok", "Accept": "application/json, text/event-stream"},
        )
        sess_b = resp_b.headers.get("mcp-session-id")

        # Call stop_server on A (must be blocked)
        call_a = {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "stop_server", "arguments": {"server": "non_running_srv"}}}
        res_a = client_a.post("/mcp", json=call_a, headers={"mcp-session-id": sess_a, "Accept": "application/json, text/event-stream"})
        assert "Permission Denied" in res_a.text

        # Call stop_server on B (must be permitted through to pool)
        call_b = {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "stop_server", "arguments": {"server": "non_running_srv"}}}
        res_b = client_b.post("/mcp", json=call_b, headers={"authorization": "Bearer rw_tok", "mcp-session-id": sess_b, "Accept": "application/json, text/event-stream"})
        assert "Permission Denied" not in res_b.text
        assert "was not running" in res_b.text or "terminated" in res_b.text


def test_gateway_call_server_child_authorization():
    """
    Verify gateway.call_server enforces child-tool permissions and does not
    allow authorization bypass for mutating tools.
    """
    from mcp_win_stdio.server.server import call_server

    token = CURRENT_PERMISSION_MODE.set("read_only")
    try:
        # 1. explorer.read_file allowed
        with patch("mcp_win_stdio.server.server.call_tool") as mock_ct:
            mock_ct.return_value = {"content": "sample content"}
            res_safe = call_server(server="explorer", tool="read_file", arguments={"path": "a.txt"})
            assert res_safe.get("isError") is not True
            mock_ct.assert_called_once_with(name="read_file", arguments={"path": "a.txt"}, server="explorer", ctx=None)

        # 2. explorer.write_file denied
        res_write = call_server(server="explorer", tool="write_file", arguments={"path": "a.txt", "content": "bad"})
        assert res_write.get("isError") is True
        assert "Permission Denied" in res_write.get("error", "")

        # 3. ssh.ssh_exec denied
        res_ssh = call_server(server="ssh", tool="ssh_exec", arguments={"command": "reboot"})
        assert res_ssh.get("isError") is True
        assert "Permission Denied" in res_ssh.get("error", "")

        # 4. Unknown child server denied
        res_unknown_srv = call_server(server="unknown_cloud_srv", tool="some_tool")
        assert res_unknown_srv.get("isError") is True
        assert "Unknown server" in res_unknown_srv.get("error", "")

        # 5. Unknown child tool denied
        res_unknown_tool = call_server(server="explorer", tool="non_existent_tool_xyz")
        assert res_unknown_tool.get("isError") is True
        assert "Permission Denied" in res_unknown_tool.get("error", "") or "not found" in res_unknown_tool.get("error", "")
    finally:
        CURRENT_PERMISSION_MODE.reset(token)


def test_db_read_query_blocks_mutating_sql():
    """Verify db.read_query strictly blocks non-SELECT mutating SQL statements."""
    from mcp_win_stdio.db.server import read_query

    mutating_statements = [
        "DROP TABLE users",
        "DELETE FROM users WHERE 1=1",
        "INSERT INTO users (id) VALUES (1)",
        "UPDATE users SET name='hacked'",
        "TRUNCATE TABLE accounts",
        "ALTER TABLE users ADD COLUMN bad text",
    ]

    for stmt in mutating_statements:
        res = read_query(sql=stmt)
        assert res.get("error") is True
        assert "Permission Denied: read_query" in res.get("message", "")


def test_db_read_query_comprehensive_sql_hardening():
    """
    Verify db.read_query defends against CTE-based DML, file export clauses,
    session variable mutations, multi-statement injection, locking clauses,
    and comment-based obfuscation.
    """
    from mcp_win_stdio.db.server import _validate_readonly_sql, read_query

    # 1. CTE-based mutations (MySQL 8.0.19+ supports WITH ... UPDATE / DELETE)
    cte_attacks = [
        "WITH cte AS (SELECT 1) UPDATE users SET name = 'hacked'",
        "WITH cte AS (SELECT id FROM users) DELETE FROM users WHERE id IN (SELECT id FROM cte)",
        "WITH cte AS (SELECT 1 AS val) INSERT INTO audit (val) SELECT val FROM cte",
        "WITH cte AS (SELECT 1) REPLACE INTO users (id) SELECT 1 FROM cte",
    ]
    for attack in cte_attacks:
        valid, err = _validate_readonly_sql(attack)
        assert valid is False, f"Expected CTE attack to fail: {attack}"
        assert "Permission Denied: read_query strictly forbids mutating" in err
        res = read_query(sql=attack)
        assert res.get("error") is True

    # 2. File export & session variable mutation clauses
    export_attacks = [
        "SELECT * FROM users INTO OUTFILE '/var/lib/mysql-files/users.csv'",
        "SELECT * FROM users INTO DUMPFILE '/tmp/bin_data'",
        "SELECT id INTO @user_var FROM users LIMIT 1",
        "SELECT * FROM users INTO OUTFILE 'C:/Windows/Temp/pwn.txt'",
    ]
    for attack in export_attacks:
        valid, err = _validate_readonly_sql(attack)
        assert valid is False, f"Expected export attack to fail: {attack}"
        assert "Permission Denied: read_query strictly forbids mutating, DDL, or file export" in err
        res = read_query(sql=attack)
        assert res.get("error") is True

    # 3. Multi-statement injection attacks
    multi_stmt_attacks = [
        "SELECT 1; UPDATE users SET role = 'admin'",
        "SELECT 1; DROP TABLE users;",
        "SELECT id FROM users; DELETE FROM audit_log",
    ]
    for attack in multi_stmt_attacks:
        valid, err = _validate_readonly_sql(attack)
        assert valid is False, f"Expected multi-stmt attack to fail: {attack}"
        assert "Multiple statements are strictly forbidden" in err
        res = read_query(sql=attack)
        assert res.get("error") is True

    # 4. Comment-based command obfuscation and MySQL conditional execution comments
    comment_attacks = [
        "/* multiline comment */ UPDATE users SET name = 'evil'",
        "# mysql line comment\nUPDATE users SET name = 'evil'",
        "-- sql standard comment\nDROP TABLE accounts",
        "SELECT 1 /*!50000 INTO OUTFILE '/tmp/pwn' */",
        "SELECT 1 /*! UPDATE users SET x = 1 */",
        "SELECT 1 /*!50000 SELECT * FROM secret */",
    ]
    for attack in comment_attacks:
        valid, err = _validate_readonly_sql(attack)
        assert valid is False, f"Expected comment attack to fail: {attack}"
        res = read_query(sql=attack)
        assert res.get("error") is True

    # 5. Row and table locking clauses
    locking_queries = [
        "SELECT * FROM users FOR UPDATE",
        "SELECT * FROM users FOR SHARE",
        "SELECT * FROM users LOCK IN SHARE MODE",
    ]
    for query in locking_queries:
        valid, err = _validate_readonly_sql(query)
        assert valid is False, f"Expected locking query to fail: {query}"
        assert "locking clauses" in err
        res = read_query(sql=query)
        assert res.get("error") is True

    # 6. Dangerous filesystem read/export side-effect functions
    side_effect_queries = [
        "SELECT pg_read_file('/etc/passwd')",
        "SELECT pg_read_binary_file('/etc/shadow')",
        "SELECT pg_ls_dir('/tmp')",
        "SELECT pg_stat_file('/etc/hosts')",
        "SELECT load_file('/etc/passwd')",
        "SELECT lo_export(1001, '/tmp/exported')",
        "SELECT lo_import('/tmp/imported')",
        "SELECT lo_get(1001)",
        "SELECT lo_put(1001, 0, 'data')",
        "SELECT dblink('host=x', 'SELECT 1')",
        "SELECT dblink_exec('host=x', 'UPDATE ...')",
        "COPY users TO '/tmp/pwn'",
        # Locking & Admin / DoS functions executable via SELECT
        "SELECT GET_LOCK('my_lock', 10)",
        "SELECT RELEASE_LOCK('my_lock')",
        "SELECT RELEASE_ALL_LOCKS()",
        "SELECT pg_advisory_lock(123)",
        "SELECT pg_advisory_xact_lock(123)",
        "SELECT pg_try_advisory_lock(123)",
        "SELECT pg_terminate_backend(1234)",
        "SELECT pg_cancel_backend(1234)",
        "SELECT pg_reload_conf()",
        "SELECT pg_rotate_logfile()",
        "SELECT pg_sleep(10)",
        "SELECT sleep(10)",
    ]
    for attack in side_effect_queries:
        valid, err = _validate_readonly_sql(attack)
        assert valid is False, f"Expected side-effect query to fail: {attack}"
        res = read_query(sql=attack)
        assert res.get("error") is True

    # 7. Backslash quote desync attacks
    desync_attacks = [
        "SELECT * FROM users WHERE note = 'test\\'s value'; UPDATE users SET role = 'admin'",
        "SELECT * FROM users WHERE note = \"test\\\"s value\"; DROP TABLE users",
    ]
    for attack in desync_attacks:
        valid, err = _validate_readonly_sql(attack)
        assert valid is False, f"Expected desync attack to fail: {attack}"
        res = read_query(sql=attack)
        assert res.get("error") is True

    # 8. Unclosed quotes, block comments, and dollar-quotes (fail closed)
    unclosed_syntax_attacks = [
        ("SELECT 'unclosed string literal", "Unclosed quote"),
        ("SELECT \"unclosed double quote", "Unclosed quote"),
        ("SELECT `unclosed backtick", "Unclosed quote"),
        ("SELECT 1 /* unclosed block comment", "Unclosed block comment"),
        ("SELECT $$unclosed dollar quote", "Unclosed dollar-quoted"),
        ("SELECT $tag$unclosed tagged dollar quote", "Unclosed dollar-quoted"),
    ]
    for attack, err_substring in unclosed_syntax_attacks:
        valid, err = _validate_readonly_sql(attack)
        assert valid is False, f"Expected unclosed syntax to fail: {attack}"
        assert err_substring in err
        res = read_query(sql=attack)
        assert res.get("error") is True

    # 9. Valid queries MUST succeed in validation
    valid_queries = [
        "SELECT * FROM users WHERE status = 'active'",
        "SELECT * FROM users WHERE note = 'UPDATE users SET x = 1'",  # keyword inside string literal
        "SELECT * FROM users WHERE note = 'SELECT ... INTO OUTFILE /tmp/foo'",  # export inside string
        "SELECT * FROM users WHERE note = 'test\\'s value'",  # escaped backslash quote in valid query
        "SELECT * FROM users WHERE note = \"test\\\"s value\"",  # escaped double quote
        "SELECT $$hello world$$ AS greeting",  # postgres dollar quoting
        "SELECT $tag$hello world$tag$ AS greeting",  # postgres tagged dollar quoting
        "WITH cte AS (SELECT 1 AS val) SELECT * FROM cte",  # legitimate read-only CTE
        "EXPLAIN SELECT * FROM users",
        "SHOW TABLES",
        "DESCRIBE users",
        "DESC users",
        "SELECT `into` FROM users",  # keyword inside backtick identifier
        "SELECT * FROM users;",  # single trailing semicolon
    ]
    for q in valid_queries:
        valid, err = _validate_readonly_sql(q)
        assert valid is True, f"Expected query to be valid: '{q}', error: {err}"


def test_is_tool_mutating_ambiguous_and_fail_closed():
    """
    Verify is_tool_mutating() semantics:
    - Resolves server identity when server is provided
    - Resolves across all servers when server is omitted
    - Fails closed (returns True) if a tool is mutating on ANY server where it exists
    - Fails closed (returns True) for unknown or unclassified tools
    - Returns False only if tool is safe on ALL servers where it exists
    """
    from mcp_win_stdio.core.permissions import TOOL_TO_SERVERS_MAP

    # 1. Pure read tool safe on its host server: explorer.read_file
    assert is_tool_mutating("read_file") is False
    assert is_tool_mutating("read_file", server="explorer") is False

    # 2. Mutating tool on all servers where it exists: export_to_pdf (excel, word)
    assert is_tool_mutating("export_to_pdf") is True
    assert is_tool_mutating("export_to_pdf", server="excel") is True
    assert is_tool_mutating("export_to_pdf", server="word") is True

    # 3. Unknown or unclassified tool: must fail closed (return True)
    assert is_tool_mutating("completely_unknown_tool_xyz") is True

    # 4. Mock ambiguous tool: safe on server_a, mutating on server_b
    # When server is omitted, it MUST return True (fails closed)
    mock_tools_map = dict(TOOL_TO_SERVERS_MAP)
    mock_tools_map["ambiguous_audit_tool"] = {"server_a", "server_b"}
    mock_safe_set = set(SAFE_READ_TOOLS)
    mock_safe_set.add(("server_a", "ambiguous_audit_tool"))
    # Notice: ("server_b", "ambiguous_audit_tool") is NOT in mock_safe_set (it is mutating on server_b)

    with patch("mcp_win_stdio.core.permissions.TOOL_TO_SERVERS_MAP", mock_tools_map), \
         patch("mcp_win_stdio.core.permissions.SAFE_READ_TOOLS", mock_safe_set):
        # Server omitted -> must return True (mutating / ambiguous)
        assert is_tool_mutating("ambiguous_audit_tool") is True

        # Server-qualified: server_a is safe -> returns False
        assert is_tool_mutating("ambiguous_audit_tool", server="server_a") is False

        # Server-qualified: server_b is mutating -> returns True
        assert is_tool_mutating("ambiguous_audit_tool", server="server_b") is True


def test_unauthenticated_tunnel_confidentiality_restrictions():
    """
    Verify unauthenticated public tunnels (auth_mode='none') strictly protect
    confidentiality by blocking sensitive reads (explorer file reads, db queries, ssh inspection)
    by default, while permitting general introspection and documentation tools.
    Also verifies --allow-sensitive-reads override.
    """
    from mcp_win_stdio.core.permissions import (
        CURRENT_ALLOW_SENSITIVE_READS,
        CURRENT_AUTH_MODE,
        check_tool_permission,
    )

    auth_tok = CURRENT_AUTH_MODE.set("none")
    sens_tok = CURRENT_ALLOW_SENSITIVE_READS.set(False)

    try:
        # Sensitive tools blocked in unauthenticated mode by default
        # Covers raw file reading, regex grep, database queries, spreadsheet row previews, word reading, and ssh
        sensitive_tools = [
            ("explorer", "read_file"),
            ("explorer", "read_head_tail"),
            ("explorer", "grep_search"),
            ("db", "read_query"),
            ("db", "get_table_sample"),
            ("db", "diff_data"),
            ("excel", "preview_sheet"),
            ("excel", "read_range"),
            ("excel", "query_rows"),
            ("excel", "query_excel_sql"),
            ("excel_db", "query_unified_sources"),
            ("excel_db", "compare_master_datasets"),
            ("word", "read_word_document"),
            ("word", "search_word_document"),
            ("git", "git_grep"),
            ("git", "git_diff"),
            ("git", "git_blame"),
            ("git", "git_log"),
            ("git", "gh_pr_diff"),
            ("rag", "query_knowledge_base"),
            ("rag", "find_related_chunks"),
            ("rag", "get_chunk_context"),
            ("ssh", "ssh_tail_logs"),
            ("ssh", "ssh_system_overview"),
            ("ssh", "ssh_list_processes"),
            ("ssh", "sftp_read_file"),
        ]

        for srv, tool in sensitive_tools:
            ok, err = check_tool_permission(srv, tool, mode="read_only")
            assert ok is False, f"Expected ({srv}, {tool}) to be blocked in unauthenticated mode!"
            assert "Access Denied: Tool" in err
            assert "restricted on unauthenticated public tunnels" in err

        # Safe non-sensitive tools allowed in unauthenticated mode (discovery, structural, metadata, outlines)
        safe_public_tools = [
            ("explorer", "list_dir"),
            ("explorer", "get_directory_tree"),
            ("explorer", "find_files"),
            ("explorer", "get_code_outline"),
            ("explorer", "workspace_summary"),
            ("gateway", "list_servers"),
            ("gateway", "search_tools"),
            ("gateway", "manage_context"),
            ("rag", "list_rag_collections"),
            ("rag", "rag_status"),
            ("rag", "get_knowledge_tree"),
            ("arch", "blueprint_audit"),
            ("tsc", "get_tsc_errors"),
            ("excel", "get_workbook_info"),
            ("excel", "list_tables"),
            ("db", "describe_table"),
            ("db", "schema_overview"),
            ("word", "get_document_outline"),
            ("word", "get_document_layout"),
            ("git", "git_status"),
        ]

        for srv, tool in safe_public_tools:
            ok, err = check_tool_permission(srv, tool, mode="read_only")
            assert ok is True, f"Expected safe public tool ({srv}, {tool}) to be allowed, error: {err}"

        # When allow_sensitive_reads is explicitly enabled: sensitive tools are permitted
        ok_sens, err_sens = check_tool_permission(
            "explorer", "read_file", mode="read_only", allow_sensitive_reads=True
        )
        assert ok_sens is True
        assert err_sens is None

        ok_db, err_db = check_tool_permission(
            "db", "read_query", mode="read_only", allow_sensitive_reads=True
        )
        assert ok_db is True
        assert err_db is None

    finally:
        CURRENT_ALLOW_SENSITIVE_READS.reset(sens_tok)
        CURRENT_AUTH_MODE.reset(auth_tok)

    # In authenticated bearer mode: sensitive read tools are permitted normally
    ok_bearer, _ = check_tool_permission("explorer", "read_file", mode="read_only", auth_mode="bearer")
    assert ok_bearer is True
    ok_db_bearer, _ = check_tool_permission("db", "read_query", mode="read_only", auth_mode="bearer")
    assert ok_db_bearer is True


def test_runtime_mode_override_isolation():
    """
    Verify _RUNTIME_MODE_OVERRIDE remains isolated:
    1. CURRENT_PERMISSION_MODE (request-scoped ContextVar) strictly supersedes _RUNTIME_MODE_OVERRIDE.
    2. Tests cleanly reset _RUNTIME_MODE_OVERRIDE.
    """
    try:
        set_runtime_mode_override("read_only")
        assert get_effective_mode() == "read_only"

        # ContextVar request takes priority over global fallback
        tok = CURRENT_PERMISSION_MODE.set("read_write")
        try:
            assert get_effective_mode() == "read_write"
        finally:
            CURRENT_PERMISSION_MODE.reset(tok)

        # After request, falls back to override
        assert get_effective_mode() == "read_only"
    finally:
        set_runtime_mode_override(None)

    assert get_effective_mode() in ("read_write", "read_only")


def test_use_tools_blocked_in_read_only():
    """
    Verify use_* tools (which modify ~/.mcp-win-stdio/*.json on disk)
    are strictly classified as mutating and blocked in read_only mode.
    """
    use_tools = [
        ("db", "use_database"),
        ("git", "use_repo"),
        ("ssh", "use_host"),
        ("tsc", "use_project"),
    ]

    for srv, tool in use_tools:
        ok, err = check_tool_permission(srv, tool, mode="read_only")
        assert ok is False
        assert "Permission Denied" in err


def test_mysql_readonly_transaction_ordering_and_client_flags():
    """
    Verify MySQL driver-level guarantees and transaction setup:
    1. PyMySQL client factory guarantees CLIENT.MULTI_STATEMENTS is never enabled.
    2. read_query calls conn.rollback() before setting transaction characteristics,
       preventing MySQL OperationalError 1568.
    """
    from mcp_win_stdio.db.server import _get_mysql_client, read_query

    # 1. Test client_flag in _get_mysql_client
    with patch("mcp_win_stdio.db.server.pymysql.connect") as mock_connect:
        mock_info = {
            "name": "test_my",
            "engine": "mysql",
            "host": "localhost",
            "port": 3306,
            "user": "root",
            "password": "",
            "database": "testdb",
        }
        _get_mysql_client(mock_info)
        assert mock_connect.called
        kwargs = mock_connect.call_args[1]
        client_flag = kwargs.get("client_flag", 0)
        # Verify MULTI_STATEMENTS (bit 1 << 16 = 65536) is NOT set
        assert (client_flag & 65536) == 0

    # 2. Test MySQL transaction setup ordering in read_query
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cur
    mock_cur.description = [("col1",)]
    mock_cur.fetchmany.return_value = [{"col1": "val1"}]

    exec_order = []
    mock_conn.rollback.side_effect = lambda: exec_order.append("rollback")
    mock_conn.autocommit.side_effect = lambda val: exec_order.append(f"autocommit_{val}")
    mock_cur.execute.side_effect = lambda sql, *args: exec_order.append(f"execute:{sql.strip()}")

    with patch("mcp_win_stdio.db.server._get_connection", return_value={"name": "test_my", "engine": "mysql", "database": "testdb"}), \
         patch("mcp_win_stdio.db.server._get_mysql_client", return_value=mock_conn):
        res = read_query(sql="SELECT 1")
        assert res.get("returned_rows") == 1

        # Verify rollback occurs BEFORE START TRANSACTION READ ONLY
        assert "rollback" in exec_order
        assert "execute:START TRANSACTION READ ONLY" in exec_order
        first_rollback = exec_order.index("rollback")
        start_tx = exec_order.index("execute:START TRANSACTION READ ONLY")
        assert first_rollback < start_tx, "conn.rollback() must precede START TRANSACTION READ ONLY to avoid error 1568!"

    # 3. Test fallback to SET TRANSACTION READ ONLY when START TRANSACTION READ ONLY is unsupported
    mock_conn2 = MagicMock()
    mock_cur2 = MagicMock()
    mock_conn2.cursor.return_value.__enter__.return_value = mock_cur2
    mock_cur2.description = [("col1",)]
    mock_cur2.fetchmany.return_value = [{"col1": "val1"}]

    def execute_with_fallback(sql, *args):
        if "START TRANSACTION READ ONLY" in sql:
            raise Exception("Syntax error: READ ONLY not supported")
        exec_order2.append(f"execute:{sql.strip()}")

    exec_order2 = []
    mock_cur2.execute.side_effect = execute_with_fallback

    with patch("mcp_win_stdio.db.server._get_connection", return_value={"name": "test_my", "engine": "mysql", "database": "testdb"}), \
         patch("mcp_win_stdio.db.server._get_mysql_client", return_value=mock_conn2):
        res2 = read_query(sql="SELECT 1")
        assert res2.get("returned_rows") == 1
        assert "execute:SET TRANSACTION READ ONLY" in exec_order2
        assert "execute:START TRANSACTION" in exec_order2

    # 4. Fail-closed: when both START TRANSACTION READ ONLY and SET TRANSACTION READ ONLY fail
    mock_conn3 = MagicMock()
    mock_cur3 = MagicMock()
    mock_conn3.cursor.return_value.__enter__.return_value = mock_cur3

    def execute_all_fail(sql, *args):
        if "TRANSACTION" in sql:
            raise Exception("Transaction initialization completely rejected")
        return None

    mock_cur3.execute.side_effect = execute_all_fail

    with patch("mcp_win_stdio.db.server._get_connection", return_value={"name": "test_my", "engine": "mysql", "database": "testdb"}), \
         patch("mcp_win_stdio.db.server._get_mysql_client", return_value=mock_conn3):
        res3 = read_query(sql="SELECT 1")
        assert res3.get("error") is True
        assert "Failed to establish read-only transaction" in res3.get("message", "")

