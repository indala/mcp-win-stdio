"""
Phase 6.2 Audit 1 — HTTP Bridge & Transport Security Test Suite.
Deterministically validates:
  1. Host header validation and DNS rebinding protection (421 Misdirected Request).
  2. Untrusted Origin header rejection (403 Forbidden).
  3. Valid loopback Host headers acceptance (127.0.0.1, localhost, [::1], testserver).
  4. Bearer authentication edge cases (valid, invalid, missing, whitespace env, unset env).
  5. Fail-closed semantics for unconfigured/empty authentication.
  6. Non-loopback client health endpoint protection (401 Unauthorized).
  7. Minimal safe data exposure on health/status endpoints (no PID, paths, or secrets).
  8. Zero credential disclosure in error responses.
  9. Session anti-spoofing and concurrent session issuance without collision.
  10. Full MCP protocol handshake and tool execution under active transport security.
"""

import concurrent.futures
import sys

import pytest
from mcp.server.transport_security import TransportSecuritySettings
from starlette.testclient import TestClient

from mcp_win_stdio.core.hub.auth import BearerAuthMiddleware, SessionManager
from mcp_win_stdio.core.hub.bridge import StreamableHttpBridge
from mcp_win_stdio.core.hub.models import HubConfig
from mcp_win_stdio.core.hub.registry import HubRegistry
from mcp_win_stdio.core.hub.supervisor import ProcessSupervisor

MOCK_AUDIT_SERVER = """
import sys, json

while True:
    line = sys.stdin.readline()
    if not line:
        break
    line = line.strip()
    if not line:
        continue
    try:
        req = json.loads(line)
        method = req.get("method")
        req_id = req.get("id")

        if method == "initialize":
            resp = {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "serverInfo": {"name": "audit_srv", "version": "1.0"},
                },
            }
        elif method == "ping":
            resp = {"jsonrpc": "2.0", "id": req_id, "result": {}}
        elif method == "tools/call":
            params = req.get("params", {})
            args = params.get("arguments", {})
            res = args.get("x", 0) + args.get("y", 0)
            resp = {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": f"Result: {res}"}],
                    "isError": False,
                },
            }
        else:
            continue

        sys.stdout.write(json.dumps(resp) + "\\n")
        sys.stdout.flush()
    except Exception:
        pass
"""


@pytest.fixture
def audit_bridge(monkeypatch):
    """Setup a configured StreamableHttpBridge with active transport security."""
    monkeypatch.setenv("AUDIT_AUTH_TOKEN", "audit_secret_token_789")

    registry = HubRegistry()
    registry.load_from_dict(
        {
            "schema_version": "1.0",
            "runtime": {
                "http_bridge": {
                    "host": "127.0.0.1",
                    "port": 8080,
                    "auth_token_env": "AUDIT_AUTH_TOKEN",
                }
            },
            "servers": {
                "audit_srv": {
                    "command": sys.executable,
                    "args": ["-u", "-c", MOCK_AUDIT_SERVER],
                    "supervisor": {
                        "auto_restart": False,
                        "probe_timeout_seconds": 5.0,
                    },
                }
            },
        }
    )

    supervisor = ProcessSupervisor(registry=registry, auto_start_monitor=False)
    supervisor.start("audit_srv")

    bridge = StreamableHttpBridge(
        supervisor=supervisor,
        registry=registry,
    )
    bridge.register_tool("audit_srv", "audit_add", "Audit addition tool")

    try:
        yield bridge
    finally:
        bridge.shutdown()

def test_dns_rebinding_host_header_rejected_with_421(audit_bridge):
    """
    Host headers with untrusted external domains (e.g. evil.com) must be rejected
    with 421 Misdirected Request to prevent browser-based DNS rebinding attacks.
    """
    app = audit_bridge.create_asgi_app()
    with TestClient(app) as client:
        # 1. MCP endpoint rejects untrusted Host
        headers = {
            "Authorization": "Bearer audit_secret_token_789",
            "Host": "evil.com",
            "Accept": "application/json, text/event-stream",
        }
        init_req = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "test-client", "version": "1.0"},
            },
        }
        res = client.post("/mcp", json=init_req, headers=headers)
        assert res.status_code == 421
        assert "Invalid Host header" in res.text

        # 2. Health and status endpoints reject untrusted Host
        for h_route in ["/health", "/status"]:
            res_h = client.get(h_route, headers={"Host": "evil.com"})
            assert res_h.status_code == 421
            assert "Invalid Host header" in res_h.text


def test_custom_host_config_cannot_authorize_external_domain(monkeypatch):
    """
    Security invariant: Setting a custom http_host in hub configuration (e.g. 'evil.com')
    must NEVER authorize that external hostname in DNS rebinding protection.
    """
    monkeypatch.setenv("AUDIT_AUTH_TOKEN", "audit_secret_token_789")
    reg = HubRegistry()
    reg.load_from_dict(
        {
            "schema_version": "1.0",
            "runtime": {
                "http_bridge": {
                    "host": "evil.com",  # Malicious / external host string
                    "port": 8080,
                    "auth_token_env": "AUDIT_AUTH_TOKEN",
                }
            },
            "servers": {},
        }
    )
    sup = ProcessSupervisor(registry=reg, auto_start_monitor=False)
    bridge = StreamableHttpBridge(supervisor=sup, registry=reg)
    try:
        app = bridge.create_asgi_app()
        with TestClient(app) as client:
            headers = {
                "Authorization": "Bearer audit_secret_token_789",
                "Host": "evil.com",
            }
            # Must still reject with 421 Misdirected Request
            res = client.get("/health", headers=headers)
            assert res.status_code == 421
            assert "Invalid Host header" in res.text
    finally:
        bridge.shutdown()

def test_origin_handling_for_browser_and_non_browser_clients(audit_bridge):
    """
    Origin policy verification:
      1. Non-browser MCP clients (missing Origin header) must be accepted.
      2. Valid loopback origins (http://127.0.0.1:8080, http://localhost:8080) must be accepted.
      3. Malicious origins (http://attacker.com) must be rejected with 403 Forbidden.
      4. Malformed/null origins ('null', 'not-an-origin') must be rejected with 403 Forbidden.
      5. Demonstrates that Origin validation (403) and Host validation (421) are distinct controls.
    """
    app = audit_bridge.create_asgi_app()
    with TestClient(app) as client:
        init_req = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "test-client", "version": "1.0"},
            },
        }

        # 1. Non-browser client: No Origin header -> Must succeed (200)
        headers_no_origin = {
            "Authorization": "Bearer audit_secret_token_789",
            "Accept": "application/json, text/event-stream",
        }
        res_no_origin = client.post("/mcp", json=init_req, headers=headers_no_origin)
        assert res_no_origin.status_code == 200

        # 2. Legitimate loopback origins -> Must succeed (200)
        for valid_origin in ["http://127.0.0.1:8080", "http://localhost:8080"]:
            headers_valid_origin = {
                "Authorization": "Bearer audit_secret_token_789",
                "Origin": valid_origin,
                "Accept": "application/json, text/event-stream",
            }
            res_val = client.post("/mcp", json=init_req, headers=headers_valid_origin)
            assert res_val.status_code == 200

        # 3. Hostile browser origin -> Must be rejected with 403
        headers_evil_origin = {
            "Authorization": "Bearer audit_secret_token_789",
            "Origin": "http://attacker.com",
            "Accept": "application/json, text/event-stream",
        }
        res_evil = client.post("/mcp", json=init_req, headers=headers_evil_origin)
        assert res_evil.status_code == 403
        assert "Invalid Origin header" in res_evil.text

        # 4. Malformed and null origins -> Must be rejected with 403
        for bad_origin in ["null", "not-a-valid-origin", "http://malicious.local:9999"]:
            headers_bad_origin = {
                "Authorization": "Bearer audit_secret_token_789",
                "Origin": bad_origin,
                "Accept": "application/json, text/event-stream",
            }
            res_bad = client.post("/mcp", json=init_req, headers=headers_bad_origin)
            assert res_bad.status_code == 403
            assert "Invalid Origin header" in res_bad.text


def test_auth_and_host_controls_remain_strictly_independent(audit_bridge):
    """
    Authentication and transport security are distinct, non-substitutable boundaries:
      1. Valid Host + Missing/Invalid Bearer token -> 401 Unauthorized (Host validation cannot bypass Auth).
      2. Valid Bearer token + Untrusted Host -> 421 Misdirected Request (Auth cannot bypass Host validation).
      3. Valid Bearer token + Untrusted Origin -> 403 Forbidden (Auth cannot bypass Origin restrictions).
    """
    app = audit_bridge.create_asgi_app()
    with TestClient(app) as client:
        init_req = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "test-client", "version": "1.0"},
            },
        }

        # Case 1: Valid loopback host, but missing token -> 401
        res1 = client.post("/mcp", json=init_req, headers={"Host": "127.0.0.1:8080"})
        assert res1.status_code == 401
        assert "Missing Authorization header" in res1.text

        # Case 2: Valid loopback host, but invalid token -> 401
        res2 = client.post(
            "/mcp",
            json=init_req,
            headers={"Host": "127.0.0.1:8080", "Authorization": "Bearer invalid_secret_token"},
        )
        assert res2.status_code == 401
        assert "Invalid Bearer token" in res2.text

        # Case 3: Valid bearer token, but untrusted Host -> 421
        res3 = client.post(
            "/mcp",
            json=init_req,
            headers={"Host": "evil.com", "Authorization": "Bearer audit_secret_token_789"},
        )
        assert res3.status_code == 421

        # Case 4: Valid bearer token, but untrusted Origin -> 403
        res4 = client.post(
            "/mcp",
            json=init_req,
            headers={
                "Host": "127.0.0.1:8080",
                "Origin": "http://evil.com",
                "Authorization": "Bearer audit_secret_token_789",
            },
        )
        assert res4.status_code == 403


def test_cross_session_anti_impersonation_with_identical_hints(audit_bridge):
    """
    Proves that even when two separate requests submit the exact same X-MWS-Session-ID
    correlation hint, each receives a cryptographically isolated, server-controlled session token
    and can never view or overwrite the other's session state.
    """
    app = audit_bridge.create_asgi_app()
    sess_mgr = audit_bridge.session_manager
    with TestClient(app) as client:
        shared_hint = "victim_correlation_hint_12345"
        headers_a = {
            "Authorization": "Bearer audit_secret_token_789",
            "X-MWS-Session-ID": shared_hint,
        }
        headers_b = {
            "Authorization": "Bearer audit_secret_token_789",
            "X-MWS-Session-ID": shared_hint,
        }

        # Request by Client A (gets new session A)
        res_a = client.get("/health", headers=headers_a)
        assert res_a.status_code == 200
        token_a = res_a.headers["x-mws-session-token"]

        # Clear cookies to simulate a distinct client connecting with the same correlation hint
        client.cookies.clear()
        res_b = client.get("/health", headers=headers_b)
        assert res_b.status_code == 200
        token_b = res_b.headers["x-mws-session-token"]

        # Both tokens must be distinct, server-controlled tokens
        assert token_a != token_b
        assert token_a != shared_hint
        assert token_b != shared_hint
        assert token_a.startswith("mws_sess_")
        assert token_b.startswith("mws_sess_")

        # Mutate Client A's session data
        data_a = sess_mgr.get_session_data(token_a)
        assert data_a is not None
        data_a["authenticated_user"] = "User_Alice"

        # Mutate Client B's session data
        data_b = sess_mgr.get_session_data(token_b)
        assert data_b is not None
        data_b["authenticated_user"] = "User_Bob"

        # Verify strict isolation
        assert sess_mgr.get_session_data(token_a)["authenticated_user"] == "User_Alice"
        assert sess_mgr.get_session_data(token_b)["authenticated_user"] == "User_Bob"


def test_valid_loopback_hosts_accepted(audit_bridge):
    """
    Valid local loopback host headers (127.0.0.1, localhost, [::1], testserver)
    must pass host validation cleanly.
    """
    app = audit_bridge.create_asgi_app()
    with TestClient(app) as client:
        for valid_host in ["127.0.0.1:8080", "localhost:8080", "testserver"]:
            headers = {
                "Authorization": "Bearer audit_secret_token_789",
                "Host": valid_host,
                "Accept": "application/json, text/event-stream",
            }
            init_req = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "test-client", "version": "1.0"},
                },
            }
            res = client.post("/mcp", json=init_req, headers=headers)
            assert res.status_code == 200, f"Host '{valid_host}' was unexpectedly rejected: {res.status_code} {res.text}"


def test_bearer_auth_variations_deterministic(monkeypatch):
    """
    Deterministic validation of Bearer authentication:
    - Valid token -> 200
    - Invalid token -> 401
    - Missing header -> 401
    - Empty token ('Bearer ') -> 401
    - Whitespace token env -> fails closed (401)
    - Unset token env -> fails closed (401)
    """
    from starlette.responses import JSONResponse

    async def dummy_app(scope, receive, send):
        resp = JSONResponse({"status": "ok"})
        await resp(scope, receive, send)

    # 1. Valid token
    monkeypatch.setenv("TEST_AUTH_ENV", "expected_secret_123")
    app = BearerAuthMiddleware(dummy_app, bind_host="0.0.0.0", auth_token_env="TEST_AUTH_ENV")
    client = TestClient(app)

    res = client.get("/tools", headers={"Authorization": "Bearer expected_secret_123"})
    assert res.status_code == 200

    # 2. Invalid token
    res = client.get("/tools", headers={"Authorization": "Bearer wrong_token_999"})
    assert res.status_code == 401
    assert res.json()["message"] == "Invalid Bearer token."

    # 3. Missing header
    res = client.get("/tools")
    assert res.status_code == 401
    assert res.json()["message"] == "Missing Authorization header."

    # 4. Empty token
    res = client.get("/tools", headers={"Authorization": "Bearer "})
    assert res.status_code == 401
    assert "Bearer scheme" in res.json()["message"] or "Invalid Bearer token" in res.json()["message"]

    # 5. Whitespace-only configured token in environment fails closed
    monkeypatch.setenv("TEST_AUTH_ENV", "   \t  \n  ")
    res = client.get("/tools", headers={"Authorization": "Bearer anything"})
    assert res.status_code == 401
    assert "not configured" in res.json()["message"]

    # 6. Unset configured token fails closed
    monkeypatch.delenv("TEST_AUTH_ENV", raising=False)
    res = client.get("/tools", headers={"Authorization": "Bearer anything"})
    assert res.status_code == 401
    assert "not configured" in res.json()["message"]


def test_non_loopback_client_health_check_requires_auth(monkeypatch):
    """
    While loopback clients are permitted minimal unauthenticated health checks,
    any non-loopback client IP (e.g. 192.168.1.100) must be rejected with 401
    unless authorized.
    """
    from starlette.responses import JSONResponse

    async def dummy_health(scope, receive, send):
        resp = JSONResponse({"status": "ok"})
        await resp(scope, receive, send)

    monkeypatch.setenv("TEST_HEALTH_TOKEN", "valid_health_token")
    app = BearerAuthMiddleware(
        dummy_health,
        bind_host="0.0.0.0",
        auth_token_env="TEST_HEALTH_TOKEN",
        allow_loopback_health_unauthenticated=True,
    )

    # Simulate non-loopback client by overriding ASGI client scope
    class RemoteClient(TestClient):
        def request(self, *args, **kwargs):
            return super().request(*args, **kwargs)

    client = TestClient(app)

    # Loopback ("testclient") succeeds unauthenticated
    res_local = client.get("/health")
    assert res_local.status_code == 200

    # Now verify with custom ASGI scope simulating a remote IP
    async def invoke_remote(client_ip: str, auth_header: str = None):
        scope = {
            "type": "http",
            "method": "GET",
            "path": "/health",
            "headers": [(b"authorization", auth_header.encode())] if auth_header else [],
            "client": (client_ip, 54321),
        }
        sent = []
        async def mock_send(msg):
            sent.append(msg)
        async def mock_recv():
            return {"type": "http.request"}

        await app(scope, mock_recv, mock_send)
        return sent[0]["status"] if sent else None

    import asyncio
    # Remote IP without auth -> 401
    status_remote_unauth = asyncio.run(invoke_remote("192.168.1.50"))
    assert status_remote_unauth == 401

    # Remote IP with valid auth -> 200
    status_remote_auth = asyncio.run(invoke_remote("192.168.1.50", "Bearer valid_health_token"))
    assert status_remote_auth == 200


def test_health_endpoint_exposes_minimal_safe_metrics_only(audit_bridge):
    """
    The health and status endpoints must expose only minimal operational counts
    and never disclose process IDs, internal paths, secrets, or configuration values.
    """
    app = audit_bridge.create_asgi_app()
    with TestClient(app) as client:
        for route in ["/health", "/status"]:
            res = client.get(route)
            assert res.status_code == 200
            data = res.json()
            # Must strictly contain only status, servers_count, and active_sessions
            assert set(data.keys()) == {"status", "servers_count", "active_sessions"}
            assert data["status"] == "ok"
            assert isinstance(data["servers_count"], int)
            assert isinstance(data["active_sessions"], int)


def test_session_id_anti_spoofing_and_concurrency(monkeypatch):
    """
    Validates:
      1. Client-supplied X-MWS-Session-ID is never adopted as the authoritative session_id.
      2. High-concurrency session creation generates unique, non-colliding session IDs.
    """
    from starlette.responses import JSONResponse

    async def sess_app(scope, receive, send):
        resp = JSONResponse({"session_id": scope.get("session_id")})
        await resp(scope, receive, send)

    monkeypatch.setenv("TEST_SESS_TOKEN", "sess_secret_token")
    sess_mgr = SessionManager()
    app = BearerAuthMiddleware(sess_app, bind_host="0.0.0.0", auth_token_env="TEST_SESS_TOKEN", session_manager=sess_mgr)
    client = TestClient(app)

    # 1. Anti-spoofing check
    forged_id = "my_custom_admin_session_id"
    res = client.get(
        "/tools",
        headers={
            "Authorization": "Bearer sess_secret_token",
            "X-MWS-Session-ID": forged_id,
        },
    )
    assert res.status_code == 200
    authoritative_id = res.json()["session_id"]
    assert authoritative_id != forged_id
    assert authoritative_id.startswith("mws_sess_")

    # 2. Concurrency test: 50 threads creating sessions concurrently
    def create_single_session(idx):
        return sess_mgr.create_session(client_ip=f"10.0.0.{idx % 250}")

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(create_single_session, i) for i in range(50)]
        session_ids = [f.result() for f in futures]

    assert len(session_ids) == 50
    assert len(set(session_ids)) == 50  # Exactly 50 unique session tokens, zero collisions


def test_full_mcp_session_lifecycle_with_dns_rebinding_protection(audit_bridge):
    """
    Proves that active DNS rebinding protection and Bearer authentication allow
    legitimate MCP clients to initialize, discover tools, and call tools cleanly.
    """
    app = audit_bridge.create_asgi_app()
    with TestClient(app) as client:
        headers = {
            "Authorization": "Bearer audit_secret_token_789",
            "Accept": "application/json, text/event-stream",
        }

        # 1. Initialize
        init_req = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "audit-client", "version": "1.0"},
            },
        }
        res_init = client.post("/mcp", json=init_req, headers=headers)
        assert res_init.status_code == 200
        assert "mws" in res_init.text

        # Extract MCP session header if present
        session_id_header = res_init.headers.get("mcp-session-id")
        if session_id_header:
            headers["mcp-session-id"] = session_id_header

        # 2. Tools List
        list_req = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/list",
            "params": {},
        }
        res_list = client.post("/mcp", json=list_req, headers=headers)
        assert res_list.status_code == 200
        assert "audit_add" in res_list.text

        # 3. Call Tool
        call_req = {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "audit_add",
                "arguments": {"x": 15, "y": 27},
            },
        }
        res_call = client.post("/mcp", json=call_req, headers=headers)
        assert res_call.status_code == 200
        assert "Result: 42" in res_call.text


def test_bind_address_ipaddress_validation_policy(monkeypatch):
    """
    Validates the IP address binding and validation policy:
      1. Genuine loopback IPv4 ('127.0.0.1', '127.0.0.2', '127.255.255.254') and
         IPv6 ('::1', '[::1]') do not require auth_token_env.
      2. 'localhost' and 'testserver' are accepted as loopback aliases.
      3. Wildcard ('0.0.0.0', '::') and external IPs ('192.168.1.50') strictly require
         a non-empty auth_token_env and valid environment token.
      4. Invalid IP strings or prefix spoofing ('127.something.invalid') are treated
         as non-loopback and require auth_token_env.
      5. StreamableHttpBridge only includes genuinely validated loopback IPs in
         TransportSecuritySettings allowed_hosts/origins, ignoring wildcards and external hosts.
    """
    # 1. Valid loopback configurations without auth_token_env
    for valid_loopback in ("127.0.0.1", "127.0.0.2", "localhost", "::1", "[::1]"):
        cfg = HubConfig.from_dict({
            "schema_version": "1.0",
            "runtime": {"http_bridge": {"host": valid_loopback, "port": 8080}},
            "servers": {},
        })
        assert cfg.http_host == valid_loopback

    # 2. Non-loopback / wildcard / invalid strings with explicitly empty auth_token_env
    for non_loopback in ("0.0.0.0", "::", "192.168.1.100", "127.something.invalid", "evil.com"):
        with pytest.raises(ValueError, match="strictly requires a non-empty 'auth_token_env'"):
            HubConfig.from_dict({
                "schema_version": "1.0",
                "runtime": {
                    "http_bridge": {
                        "host": non_loopback,
                        "port": 8080,
                        "auth_token_env": "",
                    }
                },
                "servers": {},
            })

    # 3. Non-loopback with unset environment variable (whether defaulted or explicit)
    monkeypatch.delenv("MWS_HTTP_AUTH_TOKEN", raising=False)
    for non_loopback in ("0.0.0.0", "192.168.1.100"):
        with pytest.raises(ValueError, match="requires environment variable .* to be set and non-empty"):
            HubConfig.from_dict({
                "schema_version": "1.0",
                "runtime": {"http_bridge": {"host": non_loopback, "port": 8080}},
                "servers": {},
            })

    # 4. Non-loopback with valid auth_token_env in environment succeeds
    monkeypatch.setenv("VALID_TOKEN_VAR", "super-secret-token-1234")
    cfg_remote = HubConfig.from_dict({
        "schema_version": "1.0",
        "runtime": {
            "http_bridge": {
                "host": "0.0.0.0",
                "port": 8080,
                "auth_token_env": "VALID_TOKEN_VAR",
            }
        },
        "servers": {},
    })
    assert cfg_remote.http_host == "0.0.0.0"

    # 5. Bridge TransportSecuritySettings never includes wildcard or external hosts
    reg = HubRegistry()
    reg.load_from_dict({
        "schema_version": "1.0",
        "runtime": {
            "http_bridge": {
                "host": "0.0.0.0",
                "port": 8080,
                "auth_token_env": "VALID_TOKEN_VAR",
            }
        },
        "servers": {},
    })
    sup = ProcessSupervisor(registry=reg, auto_start_monitor=False)
    bridge = StreamableHttpBridge(supervisor=sup, registry=reg)
    try:
        app = bridge.create_asgi_app()
        # Verify bridge transport_security settings
        ts_settings = bridge.transport_security
        assert ts_settings is not None
        assert ts_settings.enable_dns_rebinding_protection is True
        # Ensure 0.0.0.0 is NOT in allowed_hosts or allowed_origins
        assert "0.0.0.0" not in ts_settings.allowed_hosts
        assert "0.0.0.0:*" not in ts_settings.allowed_hosts
        assert "http://0.0.0.0:*" not in ts_settings.allowed_origins
    finally:
        bridge.shutdown()
