"""
Unit and integration tests for Phase 1 Authentication Provider Abstraction and Gateway Permission Enforcement.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from starlette.requests import Request
from starlette.responses import JSONResponse

from mcp_win_stdio.core.config import (
    get_effective_mode,
    set_runtime_mode_override,
)
from mcp_win_stdio.core.permissions import (
    check_tool_permission,
    is_tool_mutating,
)
from mcp_win_stdio.core.tunnel import (
    BearerAuthMiddleware,
    MwsTunnelManager,
    TunnelAuthMiddleware,
)
from mcp_win_stdio.core.tunnel_auth import (
    AuthProvider,
    BearerAuthProvider,
    NoneAuthProvider,
    OAuthProvider,
    create_auth_provider,
)
from mcp_win_stdio.server.server import call_tool, save_workflow

# ---------------------------------------------------------------------------
# 1. Factory & Provider Creation
# ---------------------------------------------------------------------------

def test_create_auth_provider_bearer():
    prov = create_auth_provider("bearer")
    assert isinstance(prov, BearerAuthProvider)
    assert prov.auth_mode == "bearer"
    assert bool(prov.token)
    assert isinstance(prov.token, str)
    assert prov.requires_read_only is False

    custom_prov = create_auth_provider("bearer", token="my_secret_token_123")
    assert custom_prov.token == "my_secret_token_123"


def test_create_auth_provider_none():
    prov = create_auth_provider("none")
    assert isinstance(prov, NoneAuthProvider)
    assert prov.auth_mode == "none"
    assert getattr(prov, "token", None) is None
    assert prov.requires_read_only is True


def test_create_auth_provider_oauth():
    prov = create_auth_provider("oauth", permission_mode="read_only")
    assert isinstance(prov, OAuthProvider)
    assert prov.auth_mode == "oauth"
    assert prov.permission_mode == "read_only"


def test_create_auth_provider_unknown():
    with pytest.raises(ValueError) as exc_info:
        create_auth_provider("invalid_auth")
    assert "Unknown auth_mode" in str(exc_info.value)


# ---------------------------------------------------------------------------
# 2. BearerAuthProvider Tests
# ---------------------------------------------------------------------------

def test_bearer_provider_authenticate_success():
    prov = BearerAuthProvider(token="secret_key_456")

    # Mock starlette Request with valid header
    req = MagicMock(spec=Request)
    req.headers = {"authorization": "Bearer secret_key_456"}

    res = asyncio.run(prov.authenticate(req))
    assert res is None  # None indicates authentication accepted


def test_bearer_provider_authenticate_failures():
    prov = BearerAuthProvider(token="secret_key_456")

    # Missing header
    req_missing = MagicMock(spec=Request)
    req_missing.headers = {}
    res = asyncio.run(prov.authenticate(req_missing))
    assert isinstance(res, JSONResponse)
    assert res.status_code == 401
    assert "Missing or malformed Authorization header" in res.body.decode()

    # Wrong scheme
    req_wrong_scheme = MagicMock(spec=Request)
    req_wrong_scheme.headers = {"authorization": "Basic dXNlcjpwYXNz"}
    res = asyncio.run(prov.authenticate(req_wrong_scheme))
    assert isinstance(res, JSONResponse)
    assert res.status_code == 401
    assert "Missing or malformed Authorization header" in res.body.decode()

    # Wrong token
    req_wrong_tok = MagicMock(spec=Request)
    req_wrong_tok.headers = {"authorization": "Bearer wrong_key_999"}
    res = asyncio.run(prov.authenticate(req_wrong_tok))
    assert isinstance(res, JSONResponse)
    assert res.status_code == 401
    assert "Invalid Bearer token" in res.body.decode()


def test_bearer_provider_client_config():
    prov = BearerAuthProvider(token="test_tok_abc")
    cfg = prov.get_client_config("https://example.trycloudflare.com")
    assert cfg["mcpServers"]["mws"]["url"] == "https://example.trycloudflare.com/mcp"
    assert cfg["mcpServers"]["mws"]["headers"]["Authorization"] == "Bearer test_tok_abc"


# ---------------------------------------------------------------------------
# 3. NoneAuthProvider Tests
# ---------------------------------------------------------------------------

def test_none_provider_authenticate():
    prov = NoneAuthProvider()
    assert prov.requires_read_only is True

    req = MagicMock(spec=Request)
    req.headers = {}
    res = asyncio.run(prov.authenticate(req))
    assert res is None


def test_none_provider_client_config():
    prov = NoneAuthProvider()
    cfg = prov.get_client_config("https://unauthenticated.trycloudflare.com")
    assert cfg["mcpServers"]["mws"]["url"] == "https://unauthenticated.trycloudflare.com/mcp"
    assert "headers" not in cfg["mcpServers"]["mws"]


# ---------------------------------------------------------------------------
# 4. TunnelAuthMiddleware Tests
# ---------------------------------------------------------------------------

def test_tunnel_auth_middleware_health_status_bypass():
    mock_app = MagicMock()
    prov = BearerAuthProvider(token="guard_token")
    middleware = TunnelAuthMiddleware(mock_app, auth_provider=prov)

    call_next = AsyncMock()

    # /health request without header
    req_health = MagicMock(spec=Request)
    req_health.url.path = "/health"
    resp = asyncio.run(middleware.dispatch(req_health, call_next))
    assert isinstance(resp, JSONResponse)
    assert resp.status_code == 200
    assert b"mws-tunnel" in resp.body
    call_next.assert_not_called()

    # /status request without header
    req_status = MagicMock(spec=Request)
    req_status.url.path = "/status"
    resp = asyncio.run(middleware.dispatch(req_status, call_next))
    assert isinstance(resp, JSONResponse)
    assert resp.status_code == 200
    assert b"mws-tunnel" in resp.body
    call_next.assert_not_called()


def test_tunnel_auth_middleware_protected_endpoints():
    mock_app = MagicMock()
    prov = BearerAuthProvider(token="guard_token")
    middleware = TunnelAuthMiddleware(mock_app, auth_provider=prov)

    # Protected path without auth
    req_mcp = MagicMock(spec=Request)
    req_mcp.url.path = "/mcp"
    req_mcp.headers = {}

    call_next = AsyncMock()
    resp = asyncio.run(middleware.dispatch(req_mcp, call_next))
    assert isinstance(resp, JSONResponse)
    assert resp.status_code == 401
    call_next.assert_not_called()

    # Protected path with valid auth
    req_mcp.headers = {"authorization": "Bearer guard_token"}
    expected_response = JSONResponse({"mcp": "ok"})
    call_next.return_value = expected_response

    resp = asyncio.run(middleware.dispatch(req_mcp, call_next))
    assert resp == expected_response
    call_next.assert_called_once_with(req_mcp)


def test_bearer_middleware_backward_compatibility():
    mock_app = MagicMock()
    legacy_mw = BearerAuthMiddleware(mock_app, token="legacy_123")
    assert isinstance(legacy_mw.auth_provider, BearerAuthProvider)
    assert legacy_mw.auth_provider.token == "legacy_123"


# ---------------------------------------------------------------------------
# 5. MwsTunnelManager Auth Integration & Session Isolation
# ---------------------------------------------------------------------------

def test_tunnel_manager_modes():
    # 1. Bearer mode
    mgr_bearer = MwsTunnelManager(port=8993, mode="read_only", auth_mode="bearer", token="tok1")
    assert mgr_bearer.auth_mode == "bearer"
    assert mgr_bearer.token == "tok1"
    assert mgr_bearer.mode == "read_only"

    # 2. None mode forces read_only
    mgr_none = MwsTunnelManager(port=8994, mode="read_write", auth_mode="none")
    assert mgr_none.auth_mode == "none"
    assert mgr_none.token is None
    assert mgr_none.mode == "read_only"  # Forced to read_only

    # 3. Session isolation: multiple instances have distinct providers and tokens
    mgr_a = MwsTunnelManager(port=8995, auth_mode="bearer")
    mgr_b = MwsTunnelManager(port=8996, auth_mode="bearer")
    assert mgr_a.token != mgr_b.token
    assert mgr_a.auth_provider is not mgr_b.auth_provider


def test_tunnel_manager_request_scoped_middleware_configuration():
    set_runtime_mode_override(None)
    initial_mode = get_effective_mode()

    mgr = MwsTunnelManager(port=8997, mode="read_only", auth_mode="none")
    with patch("mcp_win_stdio.server.server.mcp.streamable_http_app") as mock_app_factory, \
         patch("uvicorn.Server"):
        mock_app = MagicMock()
        mock_app_factory.return_value = mock_app

        mgr.start_local_bridge()
        try:
            # Process-global mode remains unaffected by tunnel startup
            assert get_effective_mode() == initial_mode
            # Middleware was registered with request-scoped permission_mode="read_only"
            mock_app.add_middleware.assert_called_once_with(
                TunnelAuthMiddleware,
                auth_provider=mgr.auth_provider,
                permission_mode="read_only",
            )
        finally:
            mgr.stop()

    assert get_effective_mode() == initial_mode


# ---------------------------------------------------------------------------
# 6. Tool Permission Enforcement Tests
# ---------------------------------------------------------------------------

def test_permissions_is_tool_mutating():
    # Explicitly listed mutating tools
    assert is_tool_mutating("ssh_exec") is True
    assert is_tool_mutating("write_file") is True
    assert is_tool_mutating("update_cells") is True
    assert is_tool_mutating("git_commit") is True
    assert is_tool_mutating("execute_query") is True
    assert is_tool_mutating("create_document") is True
    assert is_tool_mutating("run_workflow") is True

    # Pattern matches
    assert is_tool_mutating("create_custom_entity") is True
    assert is_tool_mutating("delete_record") is True
    assert is_tool_mutating("insert_row") is True

    # Pure read tools
    assert is_tool_mutating("read_file") is False
    assert is_tool_mutating("read_query") is False
    assert is_tool_mutating("preview_sheet") is False
    assert is_tool_mutating("git_status") is False
    assert is_tool_mutating("grep_search") is False
    assert is_tool_mutating("get_document_outline") is False


def test_permissions_check_tool_permission():
    # In read_write mode, everything passes
    ok, err = check_tool_permission("ssh", "ssh_exec", mode="read_write")
    assert ok is True
    assert err is None

    # In read_only mode, mutating tools are blocked
    ok, err = check_tool_permission("ssh", "ssh_exec", mode="read_only")
    assert ok is False
    assert "Permission Denied" in err
    assert "ssh_exec" in err

    # In read_only mode, read tools pass
    ok, err = check_tool_permission("explorer", "read_file", mode="read_only")
    assert ok is True
    assert err is None


def test_gateway_call_tool_permission_guard():
    try:
        # Force read_only runtime mode
        set_runtime_mode_override("read_only")

        # Mutating tool: should be blocked immediately at gateway level without spawning/touching child server
        res_blocked = call_tool(server="ssh", name="ssh_exec", arguments={"command": "ls"})
        assert isinstance(res_blocked, dict)
        assert res_blocked.get("isError") is True
        assert "Permission Denied" in res_blocked.get("error", "")

        # Also test with explorer write_file
        res_blocked_file = call_tool(server="explorer", name="write_file", arguments={"path": "test.txt", "content": "hi"})
        assert isinstance(res_blocked_file, dict)
        assert res_blocked_file.get("isError") is True
        assert "Permission Denied" in res_blocked_file.get("error", "")
    finally:
        set_runtime_mode_override(None)


def test_gateway_save_workflow_permission_guard():
    try:
        set_runtime_mode_override("read_only")

        wf_def = {
            "title": "Test WF",
            "steps": [{"server": "explorer", "tool": "read_file", "arguments": {"path": "a.txt"}}],
        }
        res = save_workflow(name="test_wf", definition=wf_def)
        assert isinstance(res, dict)
        assert res.get("isError") is True
        assert "Permission Denied" in res.get("error", "")
    finally:
        set_runtime_mode_override(None)
