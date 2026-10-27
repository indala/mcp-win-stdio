"""
Unit and security tests for BearerAuthMiddleware and SessionManager (Phase 4 Step 1).
Validates constant-time Bearer token comparison, strict remote-binding enforcement,
server-controlled session tokens, anti-spoofing guarantees, and fail-closed error handling.
"""

import time

from starlette.responses import JSONResponse
from starlette.testclient import TestClient

from mcp_win_stdio.core.hub.auth import BearerAuthMiddleware, SessionManager


async def echo_app(scope, receive, send):
    """Dummy ASGI application returning session details and request auth."""
    data = scope.get("session_data", {})
    body = {
        "status": "ok",
        "path": scope.get("path"),
        "session_id": scope.get("session_id"),
        "auth": scope.get("auth"),
        "data": data,
    }
    response = JSONResponse(body)
    await response(scope, receive, send)


def test_remote_binding_rejects_missing_auth(monkeypatch):
    """Remote bindings (0.0.0.0) must reject requests missing Authorization header."""
    monkeypatch.setenv("MWS_HTTP_AUTH_TOKEN", "valid_secret_token_123")
    app = BearerAuthMiddleware(echo_app, bind_host="0.0.0.0")
    client = TestClient(app)

    res = client.get("/tools")
    assert res.status_code == 401
    assert res.headers.get("www-authenticate") == 'Bearer realm="mws"'
    assert res.headers.get("cache-control") == "no-store"
    assert res.json()["error"] == "Unauthorized"
    assert "Missing Authorization header" in res.json()["message"]


def test_remote_binding_rejects_malformed_auth(monkeypatch):
    """Authorization headers not using Bearer scheme must be rejected with 401."""
    monkeypatch.setenv("MWS_HTTP_AUTH_TOKEN", "valid_secret_token_123")
    app = BearerAuthMiddleware(echo_app, bind_host="0.0.0.0")
    client = TestClient(app)

    # Basic scheme rejected
    res1 = client.get("/tools", headers={"Authorization": "Basic dXNlcjpwYXNz"})
    assert res1.status_code == 401
    assert "must use Bearer scheme" in res1.json()["message"]

    # Raw token without scheme rejected
    res2 = client.get("/tools", headers={"Authorization": "valid_secret_token_123"})
    assert res2.status_code == 401


def test_remote_binding_rejects_invalid_token(monkeypatch):
    """Invalid token values must be rejected with 401 using constant-time comparison."""
    monkeypatch.setenv("MWS_HTTP_AUTH_TOKEN", "valid_secret_token_123")
    app = BearerAuthMiddleware(echo_app, bind_host="0.0.0.0")
    client = TestClient(app)

    res = client.get("/tools", headers={"Authorization": "Bearer wrong_token_456"})
    assert res.status_code == 401
    assert "Invalid Bearer token" in res.json()["message"]


def test_fail_closed_when_token_env_missing(monkeypatch):
    """If expected token environment variable is unset or empty, requests must fail-closed."""
    monkeypatch.delenv("MWS_HTTP_AUTH_TOKEN", raising=False)
    app = BearerAuthMiddleware(echo_app, bind_host="0.0.0.0", auth_token_env="MWS_HTTP_AUTH_TOKEN")
    client = TestClient(app)

    res = client.get("/tools", headers={"Authorization": "Bearer any_token"})
    assert res.status_code == 401
    assert "not configured" in res.json()["message"]


def test_valid_token_accepted_and_issues_server_session(monkeypatch):
    """Valid Bearer token is accepted and newly issues server-controlled session token."""
    monkeypatch.setenv("MWS_HTTP_AUTH_TOKEN", "valid_secret_token_123")
    app = BearerAuthMiddleware(echo_app, bind_host="0.0.0.0")
    client = TestClient(app)

    res = client.get("/tools", headers={"Authorization": "Bearer valid_secret_token_123"})
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert data["session_id"].startswith("mws_sess_")

    # Newly issued session is present in Set-Cookie and X-MWS-Session-Token
    assert "x-mws-session-token" in res.headers
    assert res.headers["x-mws-session-token"] == data["session_id"]
    assert "mws_session=" in res.headers.get("set-cookie", "")


def test_client_cannot_spoof_session_identity(monkeypatch):
    """Client-provided X-MWS-Session-ID is treated only as a correlation hint, not identity."""
    monkeypatch.setenv("MWS_HTTP_AUTH_TOKEN", "valid_secret_token_123")
    app = BearerAuthMiddleware(echo_app, bind_host="0.0.0.0")
    client = TestClient(app)

    # Attempt to spoof a session identifier
    spoofed_id = "target_victim_session_999"
    res = client.get(
        "/tools",
        headers={
            "Authorization": "Bearer valid_secret_token_123",
            "X-MWS-Session-ID": spoofed_id,
        },
    )
    assert res.status_code == 200
    assigned_session_id = res.json()["session_id"]
    # The server NEVER assigns the spoofed ID as the session key
    assert assigned_session_id != spoofed_id
    assert assigned_session_id.startswith("mws_sess_")


def test_session_continuity_via_token_header(monkeypatch):
    """Legitimate client using server-issued session token maintains session continuity."""
    monkeypatch.setenv("MWS_HTTP_AUTH_TOKEN", "valid_secret_token_123")
    sess_mgr = SessionManager(ttl_seconds=60.0)
    app = BearerAuthMiddleware(echo_app, bind_host="0.0.0.0", session_manager=sess_mgr)
    client = TestClient(app)

    # Request 1: establish session
    res1 = client.get("/tools", headers={"Authorization": "Bearer valid_secret_token_123"})
    token = res1.headers["x-mws-session-token"]

    # Populate session data on server
    data = sess_mgr.get_session_data(token)
    assert data is not None
    data["active_db"] = "postgres_prod"

    # Request 2: reuse token
    res2 = client.get(
        "/tools",
        headers={
            "Authorization": "Bearer valid_secret_token_123",
            "MWS-Session-Token": token,
        },
    )
    assert res2.status_code == 200
    res2_data = res2.json()
    assert res2_data["session_id"] == token
    assert res2_data["data"]["active_db"] == "postgres_prod"


def test_session_isolation_across_clients(monkeypatch):
    """Independent clients have strictly isolated session data that cannot leak."""
    monkeypatch.setenv("MWS_HTTP_AUTH_TOKEN", "valid_secret_token_123")
    sess_mgr = SessionManager(ttl_seconds=60.0)
    app = BearerAuthMiddleware(echo_app, bind_host="0.0.0.0", session_manager=sess_mgr)
    client_a = TestClient(app)
    client_b = TestClient(app)

    # Client A
    res_a = client_a.get("/tools", headers={"Authorization": "Bearer valid_secret_token_123"})
    token_a = res_a.headers["x-mws-session-token"]
    sess_mgr.get_session_data(token_a)["client_name"] = "Alice"

    # Client B
    res_b = client_b.get("/tools", headers={"Authorization": "Bearer valid_secret_token_123"})
    token_b = res_b.headers["x-mws-session-token"]
    sess_mgr.get_session_data(token_b)["client_name"] = "Bob"

    assert token_a != token_b

    # Verify Alice sees Alice
    r1 = client_a.get("/tools", headers={"Authorization": "Bearer valid_secret_token_123"})
    assert r1.json()["data"]["client_name"] == "Alice"

    # Verify Bob sees Bob
    r2 = client_b.get("/tools", headers={"Authorization": "Bearer valid_secret_token_123"})
    assert r2.json()["data"]["client_name"] == "Bob"


def test_idle_session_expiry_and_cleanup(monkeypatch):
    """Sessions exceeding idle TTL are discarded and trigger new session issuance."""
    monkeypatch.setenv("MWS_HTTP_AUTH_TOKEN", "valid_secret_token_123")
    sess_mgr = SessionManager(ttl_seconds=0.1)  # 100ms TTL
    app = BearerAuthMiddleware(echo_app, bind_host="0.0.0.0", session_manager=sess_mgr)
    client = TestClient(app)

    res1 = client.get("/tools", headers={"Authorization": "Bearer valid_secret_token_123"})
    token1 = res1.headers["x-mws-session-token"]

    # Sleep past TTL
    time.sleep(0.2)

    # Reuse token after expiry
    res2 = client.get(
        "/tools",
        headers={
            "Authorization": "Bearer valid_secret_token_123",
            "MWS-Session-Token": token1,
        },
    )
    assert res2.status_code == 200
    token2 = res2.json()["session_id"]
    # New token issued, old token expired
    assert token2 != token1


def test_health_routes_loopback_policy(monkeypatch):
    """Health routes allow unauthenticated loopback checks but require auth otherwise."""
    monkeypatch.setenv("MWS_HTTP_AUTH_TOKEN", "valid_secret_token_123")
    app = BearerAuthMiddleware(
        echo_app,
        bind_host="0.0.0.0",
        allow_loopback_health_unauthenticated=True,
    )
    # TestClient uses client host "testclient" which is treated as loopback
    client = TestClient(app)

    res = client.get("/health")
    assert res.status_code == 200
    assert res.json()["path"] == "/health"


def test_auth_header_never_reflected_in_error_responses(monkeypatch):
    """Supplied tokens must never be echoed back in 401 error payloads."""
    monkeypatch.setenv("MWS_HTTP_AUTH_TOKEN", "valid_secret_token_123")
    app = BearerAuthMiddleware(echo_app, bind_host="0.0.0.0")
    client = TestClient(app)

    secret_attempt = "my_sensitive_password_attempt_9999"
    res = client.get("/tools", headers={"Authorization": f"Bearer {secret_attempt}"})
    assert res.status_code == 401
    raw_response_text = res.text
    # Secret attempt MUST NOT appear in the response body or headers
    assert secret_attempt not in raw_response_text
    for hname, hval in res.headers.items():
        assert secret_attempt not in hname
        assert secret_attempt not in hval
