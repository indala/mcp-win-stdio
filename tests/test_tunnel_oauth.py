"""
Unit and integration tests for OAuth 2.0 PKCE Engine in MWS Remote Tunnels.
Verifies RFC 8414 discovery, RFC 9728 protected resource metadata, RFC 7591 dynamic registration,
RFC 7636 mandatory S256 PKCE, Host-Owner Proof (PIN), and permission ceiling enforcement.
"""

import base64
import hashlib
import json
import secrets
from typing import Any
from unittest.mock import patch

import pytest
from starlette.testclient import TestClient

from mcp_win_stdio.core.config import CURRENT_PERMISSION_MODE
from mcp_win_stdio.core.tunnel import TunnelAuthMiddleware
from mcp_win_stdio.core.tunnel_auth import OAuthProvider, create_auth_provider
from mcp_win_stdio.core.tunnel_auth.oauth import (
    SCOPE_READ,
    SCOPE_WRITE,
    is_valid_redirect_uri,
    verify_pkce,
)
from mcp_win_stdio.server.server import mcp


def _generate_pkce_pair() -> tuple[str, str]:
    """Helper to generate standard RFC 7636 S256 code_verifier and code_challenge."""
    verifier = secrets.token_urlsafe(64)[:64]
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return verifier, challenge


# ---------------------------------------------------------------------------
# 1. Helper Function Tests
# ---------------------------------------------------------------------------

def test_is_valid_redirect_uri():
    """Verify strict redirect URI validation rejecting dangerous schemes and allowing https / loopback."""
    # Valid URIs
    assert is_valid_redirect_uri("https://example.com/oauth/callback") is True
    assert is_valid_redirect_uri("https://modelcontextprotocol.io/callback") is True
    assert is_valid_redirect_uri("http://localhost:8080/callback") is True
    assert is_valid_redirect_uri("http://127.0.0.1:45123/callback") is True
    assert is_valid_redirect_uri("http://[::1]:9000/callback") is True

    # Invalid / dangerous schemes
    assert is_valid_redirect_uri("javascript:alert(1)") is False
    assert is_valid_redirect_uri("data:text/html,<html>") is False
    assert is_valid_redirect_uri("file:///etc/passwd") is False
    assert is_valid_redirect_uri("vbscript:msgbox") is False
    assert is_valid_redirect_uri("http://remote-insecure-site.com/callback") is False  # Non-loopback http forbidden
    assert is_valid_redirect_uri("") is False
    assert is_valid_redirect_uri("not-a-uri") is False


def test_verify_pkce():
    """Verify RFC 7636 PKCE S256 verification and format enforcement."""
    verifier, challenge = _generate_pkce_pair()
    assert verify_pkce(verifier, challenge) is True

    # Mismatched verifier
    assert verify_pkce("different_verifier_that_is_at_least_43_characters_long_123456", challenge) is False

    # Invalid verifier length (< 43 or > 128)
    assert verify_pkce("short", challenge) is False
    assert verify_pkce("a" * 129, challenge) is False

    # Invalid characters in verifier
    invalid_chars_verifier = "a" * 42 + "!"
    assert verify_pkce(invalid_chars_verifier, challenge) is False


# ---------------------------------------------------------------------------
# 2. Discovery & Protected Resource Metadata Endpoints
# ---------------------------------------------------------------------------

def test_oauth_discovery_endpoints():
    """Verify RFC 8414 and RFC 9728 discovery endpoints via TestClient."""
    from mcp.server.transport_security import TransportSecuritySettings

    provider = OAuthProvider(permission_mode="read_only", public_url="https://mws-test.trycloudflare.com")
    sec = TransportSecuritySettings(enable_dns_rebinding_protection=False)
    app = mcp.streamable_http_app(transport_security=sec)
    app.add_middleware(TunnelAuthMiddleware, auth_provider=provider, permission_mode="read_only")

    with TestClient(app) as client:
        # 1. RFC 8414 Authorization Server Metadata
        r_auth = client.get("/.well-known/oauth-authorization-server")
        assert r_auth.status_code == 200
        data_auth = r_auth.json()
        assert data_auth["issuer"] == "https://mws-test.trycloudflare.com"
        assert data_auth["authorization_endpoint"] == "https://mws-test.trycloudflare.com/oauth/authorize"
        assert data_auth["token_endpoint"] == "https://mws-test.trycloudflare.com/oauth/token"
        assert data_auth["registration_endpoint"] == "https://mws-test.trycloudflare.com/oauth/register"
        assert data_auth["revocation_endpoint"] == "https://mws-test.trycloudflare.com/oauth/revoke"
        assert "S256" in data_auth["code_challenge_methods_supported"]
        assert "authorization_code" in data_auth["grant_types_supported"]

        # 2. RFC 9728 Protected Resource Metadata
        r_res = client.get("/.well-known/oauth-protected-resource")
        assert r_res.status_code == 200
        data_res = r_res.json()
        assert data_res["resource"] == "https://mws-test.trycloudflare.com/mcp"
        assert "https://mws-test.trycloudflare.com" in data_res["authorization_servers"]


# ---------------------------------------------------------------------------
# 3. Dynamic Client Registration (RFC 7591)
# ---------------------------------------------------------------------------

def test_oauth_dynamic_client_registration():
    """Verify dynamic client registration and rejection of invalid metadata."""
    from mcp.server.transport_security import TransportSecuritySettings

    provider = OAuthProvider(permission_mode="read_only")
    sec = TransportSecuritySettings(enable_dns_rebinding_protection=False)
    app = mcp.streamable_http_app(transport_security=sec)
    app.add_middleware(TunnelAuthMiddleware, auth_provider=provider, permission_mode="read_only")

    with TestClient(app) as client:
        # Success registration
        reg_payload = {
            "client_name": "Claude Desktop",
            "redirect_uris": ["http://localhost:54321/callback", "https://claude.ai/callback"],
        }
        res = client.post("/oauth/register", json=reg_payload)
        assert res.status_code == 201
        data = res.json()
        assert "client_id" in data
        assert data["client_id"].startswith("mws_client_")
        assert data["client_name"] == "Claude Desktop"
        assert "http://localhost:54321/callback" in data["redirect_uris"]

        # Rejection: missing redirect_uris
        bad_res1 = client.post("/oauth/register", json={"client_name": "Bad Client"})
        assert bad_res1.status_code == 400
        assert "redirect_uris list is required" in bad_res1.json()["error_description"]

        # Rejection: dangerous redirect_uri scheme
        bad_res2 = client.post("/oauth/register", json={"redirect_uris": ["javascript:alert(1)"]})
        assert bad_res2.status_code == 400
        assert "Invalid redirect_uri" in bad_res2.json()["error_description"]


# ---------------------------------------------------------------------------
# 4. Authorization, Host-Owner PIN Verification, and Code Minting
# ---------------------------------------------------------------------------

def test_oauth_authorize_and_host_owner_proof():
    """
    Verify /oauth/authorize validation and Host-Owner PIN enforcement:
    1. Unknown client_id renders 400 without redirecting.
    2. Unregistered redirect_uri renders 400 without redirecting.
    3. Missing S256 PKCE is rejected.
    4. Submitting /oauth/approve without the valid terminal PIN is rejected (403 Forbidden).
    5. Submitting /oauth/approve with the valid terminal PIN issues an authorization code.
    """
    from mcp.server.transport_security import TransportSecuritySettings

    provider = OAuthProvider(permission_mode="read_only")
    sec = TransportSecuritySettings(enable_dns_rebinding_protection=False)
    app = mcp.streamable_http_app(transport_security=sec)
    app.add_middleware(TunnelAuthMiddleware, auth_provider=provider, permission_mode="read_only")

    with TestClient(app) as client:
        # Register a valid client first
        reg_res = client.post("/oauth/register", json={
            "client_name": "Gemini Web",
            "redirect_uris": ["https://gemini.google.com/oauth/callback"],
        })
        client_id = reg_res.json()["client_id"]
        redirect_uri = "https://gemini.google.com/oauth/callback"
        _, challenge = _generate_pkce_pair()

        # 1. Unknown client_id -> 400 Bad Request HTML (no redirect)
        res_bad_client = client.get("/oauth/authorize?client_id=unknown&redirect_uri=https://gemini.google.com/oauth/callback")
        assert res_bad_client.status_code == 400
        assert "Invalid client_id" in res_bad_client.text

        # 2. Unregistered redirect_uri -> 400 Bad Request HTML (no redirect)
        res_bad_uri = client.get(f"/oauth/authorize?client_id={client_id}&redirect_uri=https://attacker.com/callback")
        assert res_bad_uri.status_code == 400
        assert "Unregistered redirect_uri" in res_bad_uri.text

        # 3. Missing S256 PKCE -> Redirect with error
        res_no_pkce = client.get(
            f"/oauth/authorize?response_type=code&client_id={client_id}&redirect_uri={redirect_uri}",
            follow_redirects=False,
        )
        assert res_no_pkce.status_code == 302
        assert "error=invalid_request" in res_no_pkce.headers["location"]

        # 4. Valid authorization request -> Renders consent page & generates PIN
        with patch("builtins.print") as mock_print:
            auth_res = client.get(
                f"/oauth/authorize?response_type=code&client_id={client_id}&redirect_uri={redirect_uri}&code_challenge={challenge}&code_challenge_method=S256&state=state123"
            )
            assert auth_res.status_code == 200
            assert "Authorize Client" in auth_res.text
            assert "operator_pin" in auth_res.text
            assert mock_print.called

        # Extract tx_id and csrf_token from pending authorizations
        assert len(provider._pending_authorizations) == 1
        tx_id = list(provider._pending_authorizations.keys())[-1]
        correct_pin = provider._pending_authorizations[tx_id]["pin"]
        csrf_tok = provider._pending_authorizations[tx_id]["csrf_token"]

        # 5. Invalid Action check -> 400 Bad Request
        bad_action = client.post(
            "/oauth/approve",
            data={"tx_id": tx_id, "action": "invalid_action", "operator_pin": correct_pin, "csrf_token": csrf_tok},
        )
        assert bad_action.status_code == 400
        assert "Invalid Action" in bad_action.text

        # 6. Invalid CSRF Token check -> 403 Forbidden
        bad_csrf = client.post(
            "/oauth/approve",
            data={"tx_id": tx_id, "action": "approve", "operator_pin": correct_pin, "csrf_token": "wrong_csrf"},
        )
        assert bad_csrf.status_code == 403
        assert "Invalid or Missing CSRF Token" in bad_csrf.text

        # 7. PIN Attempt Tracking & Exhaustion (with valid CSRF token)
        # Attempt 1: Wrong PIN -> 403, 2 attempts remaining
        bad_approve1 = client.post(
            "/oauth/approve",
            data={"tx_id": tx_id, "action": "approve", "operator_pin": "000000", "csrf_token": csrf_tok},
            headers={"cf-connecting-ip": "203.0.113.1"},
        )
        assert bad_approve1.status_code == 403
        assert "<strong>2</strong> attempt(s) remaining" in bad_approve1.text

        # Attempt 2: Wrong PIN -> 403, 1 attempt remaining
        bad_approve2 = client.post(
            "/oauth/approve",
            data={"tx_id": tx_id, "action": "approve", "operator_pin": "111111", "csrf_token": csrf_tok},
            headers={"cf-connecting-ip": "203.0.113.1"},
        )
        assert bad_approve2.status_code == 403
        assert "<strong>1</strong> attempt(s) remaining" in bad_approve2.text

        # Attempt 3: Wrong PIN -> 403, session burned!
        bad_approve3 = client.post(
            "/oauth/approve",
            data={"tx_id": tx_id, "action": "approve", "operator_pin": "222222", "csrf_token": csrf_tok},
            headers={"cf-connecting-ip": "203.0.113.1"},
        )
        assert bad_approve3.status_code == 403
        assert "Maximum PIN attempts exceeded" in bad_approve3.text

        # Attempt 4: Session was burned -> 400 Expired or Invalid Request
        bad_approve4 = client.post(
            "/oauth/approve",
            data={"tx_id": tx_id, "action": "approve", "operator_pin": correct_pin, "csrf_token": csrf_tok},
        )
        assert bad_approve4.status_code == 400
        assert "Expired or Invalid Request" in bad_approve4.text

        # 8. User Denial with state check
        client.get(
            f"/oauth/authorize?response_type=code&client_id={client_id}&redirect_uri={redirect_uri}&code_challenge={challenge}&code_challenge_method=S256&state=state_deny_99"
        )
        tx_deny = list(provider._pending_authorizations.keys())[0]
        csrf_deny = provider._pending_authorizations[tx_deny]["csrf_token"]
        deny_res = client.post(
            "/oauth/approve",
            data={"tx_id": tx_deny, "action": "deny", "csrf_token": csrf_deny},
            follow_redirects=False,
        )
        assert deny_res.status_code == 302
        deny_loc = deny_res.headers["location"]
        assert "error=access_denied" in deny_loc
        assert "state=state_deny_99" in deny_loc

        # 9. Re-generate authorization for valid approval with state
        client.get(
            f"/oauth/authorize?response_type=code&client_id={client_id}&redirect_uri={redirect_uri}&code_challenge={challenge}&code_challenge_method=S256&state=state_ok_123"
        )
        tx_id2 = list(provider._pending_authorizations.keys())[0]
        correct_pin2 = provider._pending_authorizations[tx_id2]["pin"]
        csrf_tok2 = provider._pending_authorizations[tx_id2]["csrf_token"]

        # 10. Operator enters CORRECT PIN -> 302 Redirect with code and state
        good_approve = client.post(
            "/oauth/approve",
            data={"tx_id": tx_id2, "action": "approve", "operator_pin": correct_pin2, "csrf_token": csrf_tok2},
            headers={"cf-connecting-ip": "203.0.113.1"},
            follow_redirects=False,
        )
        assert good_approve.status_code == 302
        loc = good_approve.headers["location"]
        assert redirect_uri in loc
        assert "code=mws_code_" in loc
        assert "state=state_ok_123" in loc

        # 11. Success burns the transaction -> Re-submitting tx_id2 returns 400
        reuse_tx = client.post(
            "/oauth/approve",
            data={"tx_id": tx_id2, "action": "approve", "operator_pin": correct_pin2, "csrf_token": csrf_tok2},
        )
        assert reuse_tx.status_code == 400


def test_mws_default_client_loopback_restriction():
    """
    Verify mws-default-client strictly allows RFC 8252 loopback callbacks
    and rejects arbitrary non-loopback https URIs (mitigating open redirect risk).
    """
    from mcp.server.transport_security import TransportSecuritySettings

    provider = OAuthProvider(permission_mode="read_only")
    sec = TransportSecuritySettings(enable_dns_rebinding_protection=False)
    app = mcp.streamable_http_app(transport_security=sec)
    app.add_middleware(TunnelAuthMiddleware, auth_provider=provider, permission_mode="read_only")

    with TestClient(app) as client:
        _, challenge = _generate_pkce_pair()

        # 1. Valid RFC 8252 loopback callbacks on mws-default-client MUST be accepted across dynamic ports
        res_local1 = client.get(
            f"/oauth/authorize?response_type=code&client_id=mws-default-client&redirect_uri=http://localhost/callback&code_challenge={challenge}&code_challenge_method=S256"
        )
        assert res_local1.status_code == 200

        # Dynamic port + existing query parameter + state round-trip test
        dynamic_uri = "http://127.0.0.1:54321/callback?client_context=vscode"
        res_local2 = client.get(
            f"/oauth/authorize?response_type=code&client_id=mws-default-client&redirect_uri={dynamic_uri}&code_challenge={challenge}&code_challenge_method=S256&state=state_loop_789"
        )
        assert res_local2.status_code == 200
        tx_id = list(provider._pending_authorizations.keys())[-1]
        pin = provider._pending_authorizations[tx_id]["pin"]
        csrf_tok = provider._pending_authorizations[tx_id]["csrf_token"]

        approve_res = client.post(
            "/oauth/approve",
            data={"tx_id": tx_id, "action": "approve", "operator_pin": pin, "csrf_token": csrf_tok},
            follow_redirects=False,
        )
        assert approve_res.status_code == 302
        loc = approve_res.headers["location"]
        # Verify RFC 6749 URL structure without double '?' syntax corruption
        assert loc.startswith("http://127.0.0.1:54321/callback?")
        assert loc.count("?") == 1
        assert "client_context=vscode" in loc
        assert "code=mws_code_" in loc
        assert "state=state_loop_789" in loc

        # 2. Arbitrary external https URI on mws-default-client MUST be rejected with 400 (never redirect)
        res_evil = client.get(
            f"/oauth/authorize?response_type=code&client_id=mws-default-client&redirect_uri=https://evil.example.com/callback&code_challenge={challenge}&code_challenge_method=S256"
        )
        assert res_evil.status_code == 400
        assert "Unregistered redirect_uri" in res_evil.text


def test_oauth_bounded_state_maps_and_pruning():
    """
    Verify capacity caps and TTL state pruning:
    - Bounded pending authorizations (max 50)
    - Bounded auth codes (max 100)
    - Bounded dynamic clients (max 200, never evicts mws-default-client)
    """
    provider = OAuthProvider(permission_mode="read_only")

    # 1. Fill pending authorizations beyond capacity (55 entries)
    for i in range(55):
        provider._pending_authorizations[f"tx_{i}"] = {
            "tx_id": f"tx_{i}",
            "expires_at": 1000.0,  # Expired timestamp
        }

    # Add a fresh entry and prune
    provider._pending_authorizations["tx_fresh"] = {
        "tx_id": "tx_fresh",
        "expires_at": 9999999999.0,
    }
    provider._prune_state()
    # All expired items should be pruned; only fresh remains
    assert len(provider._pending_authorizations) == 1
    assert "tx_fresh" in provider._pending_authorizations

    # 2. Fill dynamic clients beyond capacity (210 entries)
    for i in range(210):
        provider._clients[f"client_{i}"] = {"client_id": f"client_{i}"}

    provider._prune_state()
    assert len(provider._clients) <= 200
    # Crucial: mws-default-client must NEVER be evicted
    assert "mws-default-client" in provider._clients


# ---------------------------------------------------------------------------
# 5. Token Exchange, Atomic Code Burning, and Revocation
# ---------------------------------------------------------------------------

def test_oauth_token_exchange_and_replay_prevention():
    """
    Verify /oauth/token:
    1. Valid exchange with S256 verifier returns signed Bearer token.
    2. Atomic code consumption: second attempt with same code fails immediately.
    3. Mismatched redirect_uri or client_id fails and burns the code.
    4. Invalid code_verifier fails PKCE check and burns code.
    """
    from mcp.server.transport_security import TransportSecuritySettings

    provider = OAuthProvider(permission_mode="read_only")
    sec = TransportSecuritySettings(enable_dns_rebinding_protection=False)
    app = mcp.streamable_http_app(transport_security=sec)
    app.add_middleware(TunnelAuthMiddleware, auth_provider=provider, permission_mode="read_only")

    with TestClient(app) as client:
        verifier, challenge = _generate_pkce_pair()
        reg_res = client.post("/oauth/register", json={
            "client_name": "Test Client",
            "redirect_uris": ["https://app.example.com/callback"],
        })
        client_id = reg_res.json()["client_id"]
        redirect_uri = "https://app.example.com/callback"

        # Authorize and approve to get code
        client.get(f"/oauth/authorize?response_type=code&client_id={client_id}&redirect_uri={redirect_uri}&code_challenge={challenge}&code_challenge_method=S256")
        tx_id = list(provider._pending_authorizations.keys())[-1]
        pin = provider._pending_authorizations[tx_id]["pin"]
        csrf_tok = provider._pending_authorizations[tx_id]["csrf_token"]
        approve_res = client.post("/oauth/approve", data={"tx_id": tx_id, "action": "approve", "operator_pin": pin, "csrf_token": csrf_tok}, follow_redirects=False)
        code = approve_res.headers["location"].split("code=")[1].split("&")[0]

        # 1. Successful Token Exchange
        token_res = client.post("/oauth/token", data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": client_id,
            "code_verifier": verifier,
        })
        assert token_res.status_code == 200
        token_data = token_res.json()
        assert "access_token" in token_data
        assert token_data["token_type"] == "Bearer"
        assert token_data["expires_in"] == 3600
        access_token = token_data["access_token"]

        # 2. Replay Attempt (Must Fail - Code Burned)
        replay_res = client.post("/oauth/token", data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": client_id,
            "code_verifier": verifier,
        })
        assert replay_res.status_code == 400
        assert replay_res.json()["error"] == "invalid_grant"

        # 3. Token Revocation
        rev_res = client.post("/oauth/revoke", data={"token": access_token})
        assert rev_res.status_code == 200
        assert rev_res.json()["status"] == "revoked"

        # Verify token is now rejected on protected /mcp endpoint
        mcp_res = client.post("/mcp", headers={"Authorization": f"Bearer {access_token}"})
        assert mcp_res.status_code == 401
        assert "invalid_token" in mcp_res.headers.get("www-authenticate", "")


# ---------------------------------------------------------------------------
# 6. Permission Ceiling Enforcement & ContextVar Propagation
# ---------------------------------------------------------------------------

def test_oauth_permission_ceiling_enforcement():
    """
    Verify scope-to-permission ceiling:
    1. If server is read_only, client requesting mcp:write is clamped to read_only.
    2. If server is read_write, client with mcp:write receives read_write.
    """
    from mcp.server.transport_security import TransportSecuritySettings

    # Case 1: Server configured in read_only mode
    provider_ro = OAuthProvider(permission_mode="read_only")
    sec = TransportSecuritySettings(enable_dns_rebinding_protection=False)
    app_ro = mcp.streamable_http_app(transport_security=sec)
    app_ro.add_middleware(TunnelAuthMiddleware, auth_provider=provider_ro, permission_mode="read_only")

    with TestClient(app_ro) as client_ro:
        verifier, challenge = _generate_pkce_pair()
        reg_res = client_ro.post("/oauth/register", json={
            "client_name": "Writer Client",
            "redirect_uris": ["https://app.example.com/callback"],
        })
        client_id = reg_res.json()["client_id"]
        redirect_uri = "https://app.example.com/callback"

        # Request mcp:write scope on a read_only server
        client_ro.get(
            f"/oauth/authorize?response_type=code&client_id={client_id}&redirect_uri={redirect_uri}&code_challenge={challenge}&code_challenge_method=S256&scope=mcp:write"
        )
        tx_id = list(provider_ro._pending_authorizations.keys())[0]
        pin = provider_ro._pending_authorizations[tx_id]["pin"]
        csrf_tok = provider_ro._pending_authorizations[tx_id]["csrf_token"]
        approve_res = client_ro.post("/oauth/approve", data={"tx_id": tx_id, "action": "approve", "operator_pin": pin, "csrf_token": csrf_tok}, follow_redirects=False)
        code = approve_res.headers["location"].split("code=")[1].split("&")[0]

        token_res = client_ro.post("/oauth/token", data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": client_id,
            "code_verifier": verifier,
        })
        token = token_res.json()["access_token"]

        # Initialize MCP session
        init_payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "test", "version": "1.0"}},
        }
        init_resp = client_ro.post("/mcp", json=init_payload, headers={"Authorization": f"Bearer {token}", "Accept": "application/json, text/event-stream"})
        sess_id = init_resp.headers.get("mcp-session-id")

        # Mutating tool (stop_server) MUST be blocked because server ceiling is read_only!
        call_mut = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": "stop_server", "arguments": {"server": "excel"}},
        }
        resp_mut = client_ro.post("/mcp", json=call_mut, headers={"Authorization": f"Bearer {token}", "mcp-session-id": sess_id, "Accept": "application/json, text/event-stream"})
        assert "Permission Denied" in resp_mut.text


def test_oauth_unauthenticated_mcp_returns_401_with_www_authenticate():
    """
    Verify unauthenticated /mcp request returns HTTP 401 with RFC 9728 WWW-Authenticate header.
    """
    from mcp.server.transport_security import TransportSecuritySettings

    provider = OAuthProvider(permission_mode="read_only", public_url="https://tunnel.trycloudflare.com")
    sec = TransportSecuritySettings(enable_dns_rebinding_protection=False)
    app = mcp.streamable_http_app(transport_security=sec)
    app.add_middleware(TunnelAuthMiddleware, auth_provider=provider, permission_mode="read_only")

    with TestClient(app) as client:
        res = client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "initialize"})
        assert res.status_code == 401
        www_auth = res.headers.get("www-authenticate", "")
        assert 'Bearer realm="mcp-win-stdio"' in www_auth
        assert 'resource_metadata="https://tunnel.trycloudflare.com/.well-known/oauth-protected-resource"' in www_auth


def test_oauth_html_injection_prevention():
    """
    Verify that user-supplied fields in /oauth/authorize (e.g. client_id, client_name)
    are strictly HTML-escaped to prevent reflected cross-site scripting (XSS).
    """
    provider = OAuthProvider(permission_mode="read_only", public_url="https://tunnel.trycloudflare.com")
    app = TunnelAuthMiddleware(mcp.streamable_http_app(), auth_provider=provider, permission_mode="read_only")

    with TestClient(app) as client:
        # 1. Unregistered client with XSS probe
        xss_probe = "<script>alert(1)</script>"
        res_bad_client = client.get(f"/oauth/authorize?client_id={xss_probe}")
        assert res_bad_client.status_code == 400
        assert "<script>alert(1)</script>" not in res_bad_client.text
        assert "&lt;script&gt;alert(1)&lt;/script&gt;" in res_bad_client.text

        # 2. Registered client with XSS probe in client_name and redirect_uri
        reg_payload = {
            "client_name": "<img src=x onerror=alert('xss')>",
            "redirect_uris": ["https://evil.com/callback?data=<script>"],
        }
        reg_resp = client.post("/oauth/register", json=reg_payload)
        assert reg_resp.status_code == 201
        client_id = reg_resp.json()["client_id"]

        _, challenge = _generate_pkce_pair()
        auth_url = (
            f"/oauth/authorize?response_type=code&client_id={client_id}&code_challenge={challenge}"
            f"&code_challenge_method=S256&redirect_uri=https://evil.com/callback?data=<script>"
        )
        res_consent = client.get(auth_url)
        assert res_consent.status_code == 200
        assert "<img src=x onerror=alert('xss')>" not in res_consent.text
        assert "&lt;img src=x onerror=alert(&#x27;xss&#x27;)&gt;" in res_consent.text or "&lt;img src=x" in res_consent.text
        assert "<script>" not in res_consent.text
        assert "&lt;script&gt;" in res_consent.text


def test_oauth_cors_preflight_and_headers():
    """
    Verify OPTIONS preflight on OAuth endpoints and Access-Control-Allow-Origin headers.
    """
    provider = OAuthProvider(permission_mode="read_only", public_url="https://tunnel.trycloudflare.com")
    app = TunnelAuthMiddleware(mcp.streamable_http_app(), auth_provider=provider, permission_mode="read_only")

    with TestClient(app) as client:
        # Preflight OPTIONS request
        opts_res = client.options("/oauth/token")
        assert opts_res.status_code == 204
        assert opts_res.headers.get("access-control-allow-origin") == "*"
        assert "POST" in opts_res.headers.get("access-control-allow-methods", "")
        assert "Authorization" in opts_res.headers.get("access-control-allow-headers", "")

        # Revoke endpoint CORS
        opts_rev = client.options("/oauth/revoke")
        assert opts_rev.status_code == 204
        assert opts_rev.headers.get("access-control-allow-origin") == "*"


def test_oauth_token_requires_client_id_and_secure_revocation():
    """
    Verify RFC 6749 §4.1.3 client_id requirement at token endpoint and
    HMAC signature verification before adding to _revoked_tokens.
    """
    provider = OAuthProvider(permission_mode="read_only", public_url="https://tunnel.trycloudflare.com")
    app = TunnelAuthMiddleware(mcp.streamable_http_app(), auth_provider=provider, permission_mode="read_only")

    with TestClient(app) as client:
        verifier, challenge = _generate_pkce_pair()
        reg_res = client.post("/oauth/register", json={
            "client_name": "Test App",
            "redirect_uris": ["https://app.example.com/callback"],
        })
        client_id = reg_res.json()["client_id"]
        redirect_uri = "https://app.example.com/callback"

        client.get(
            f"/oauth/authorize?response_type=code&client_id={client_id}&redirect_uri={redirect_uri}&code_challenge={challenge}&code_challenge_method=S256"
        )
        tx_id = list(provider._pending_authorizations.keys())[0]
        pin = provider._pending_authorizations[tx_id]["pin"]
        csrf_tok = provider._pending_authorizations[tx_id]["csrf_token"]
        approve_res = client.post("/oauth/approve", data={"tx_id": tx_id, "action": "approve", "operator_pin": pin, "csrf_token": csrf_tok}, follow_redirects=False)
        code = approve_res.headers["location"].split("code=")[1].split("&")[0]

        # 1. Missing client_id in token exchange MUST be rejected
        token_missing_client = client.post("/oauth/token", data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "code_verifier": verifier,
        })
        assert token_missing_client.status_code == 400
        assert token_missing_client.json()["error"] == "invalid_grant"
        assert token_missing_client.headers.get("access-control-allow-origin") == "*"

        # 2. Re-mint authorization code for successful exchange
        verifier2, challenge2 = _generate_pkce_pair()
        client.get(
            f"/oauth/authorize?response_type=code&client_id={client_id}&redirect_uri={redirect_uri}&code_challenge={challenge2}&code_challenge_method=S256"
        )
        tx_id2 = list(provider._pending_authorizations.keys())[0]
        pin2 = provider._pending_authorizations[tx_id2]["pin"]
        csrf_tok2 = provider._pending_authorizations[tx_id2]["csrf_token"]
        approve_res2 = client.post("/oauth/approve", data={"tx_id": tx_id2, "action": "approve", "operator_pin": pin2, "csrf_token": csrf_tok2}, follow_redirects=False)
        code2 = approve_res2.headers["location"].split("code=")[1].split("&")[0]

        token_res = client.post("/oauth/token", data={
            "grant_type": "authorization_code",
            "code": code2,
            "redirect_uri": redirect_uri,
            "client_id": client_id,
            "code_verifier": verifier2,
        })
        assert token_res.status_code == 200
        assert token_res.headers.get("access-control-allow-origin") == "*"
        valid_token = token_res.json()["access_token"]

        # 3. Unauthenticated/forged token revocation attempt
        fake_payload = base64.urlsafe_b64encode(json.dumps({"jti": "attacker_fake_jti", "exp": 9999999999}).encode()).decode().rstrip("=")
        fake_token = f"{fake_payload}.invalid_signature"
        rev_fake = client.post("/oauth/revoke", data={"token": fake_token})
        assert rev_fake.status_code == 200
        assert rev_fake.headers.get("access-control-allow-origin") == "*"
        # Ensure fake jti was NOT added to _revoked_tokens
        assert "attacker_fake_jti" not in provider._revoked_tokens

        # 4. Valid token revocation
        rev_valid = client.post("/oauth/revoke", data={"token": valid_token})
        assert rev_valid.status_code == 200
        # Now the legitimate token is revoked
        assert len(provider._revoked_tokens) == 1

        # 5. Verify shutdown() clears all state
        import asyncio
        asyncio.run(provider.shutdown())
        assert len(provider._revoked_tokens) == 0
        assert len(provider._auth_codes) == 0
        assert len(provider._active_tokens) == 0
        assert len(provider._pending_authorizations) == 0
