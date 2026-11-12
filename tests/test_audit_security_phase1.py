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
        assert "Permission Denied: read_query strictly permits" in res.get("message", "")


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
