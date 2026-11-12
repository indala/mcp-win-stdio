"""
OAuth 2.0 / 2.1 PKCE Authorization Server and Provider for MWS remote tunnels.
Implements RFC 8414, RFC 7636, RFC 7591, RFC 9728, and RFC 9700.
"""

import base64
import hashlib
import hmac
import html
import json
import logging
import re
import secrets
import time
import urllib.parse
from typing import Any, Dict, List, Optional, Set, Tuple

from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, RedirectResponse, Response

from .base import AuthProvider

logger = logging.getLogger("mcp_win_stdio.tunnel.oauth")

# Standard MCP and OAuth Scopes
SCOPE_READ = "mcp:read"
SCOPE_WRITE = "mcp:write"
VALID_SCOPES = {SCOPE_READ, SCOPE_WRITE, "read", "write", "read_only", "read_write"}


def is_valid_redirect_uri(uri: str) -> bool:
    """
    Validate redirect URI per RFC 8252 and OAuth security BCP (RFC 9700).
    Allows https:// URIs, or http:// URIs on loopback addresses (127.0.0.1, localhost, [::1]).
    Rejects javascript:, data:, file:, and malformed URIs.
    """
    if not uri or not isinstance(uri, str):
        return False
    uri = uri.strip()
    lower = uri.lower()
    if any(lower.startswith(bad) for bad in ("javascript:", "data:", "file:", "vbscript:", "about:")):
        return False
    try:
        parsed = urllib.parse.urlsplit(uri)
        if not parsed.scheme or not parsed.netloc:
            return False
        if parsed.scheme == "https":
            return True
        if parsed.scheme == "http":
            hostname = (parsed.hostname or "").lower()
            if hostname in ("127.0.0.1", "localhost", "::1", "[::1]"):
                return True
        return False
    except Exception:
        return False


def is_loopback_uri(uri: str) -> bool:
    """
    Check if a URI is an RFC 8252 loopback callback on any ephemeral port (1..65535).
    Scheme must be http, host must be 127.0.0.1, localhost, ::1, or [::1].
    """
    try:
        parsed = urllib.parse.urlsplit(uri)
        if parsed.scheme != "http":
            return False
        hostname = (parsed.hostname or "").lower()
        return hostname in ("127.0.0.1", "localhost", "::1", "[::1]")
    except Exception:
        return False


def build_redirect_url(redirect_uri: str, params: Dict[str, Optional[str]]) -> str:
    """
    Safely append query parameters to a redirect URI per RFC 6749,
    preserving existing query strings and fragments without syntax corruption.
    """
    parsed = urllib.parse.urlsplit(redirect_uri)
    existing_query = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    for k, v in params.items():
        if v is not None:
            existing_query.append((k, str(v)))
    new_query = urllib.parse.urlencode(existing_query)
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path, new_query, parsed.fragment))


def verify_pkce(code_verifier: str, code_challenge: str) -> bool:
    """
    Verify RFC 7636 S256 PKCE code_verifier against code_challenge using constant-time comparison.
    """
    if not code_verifier or not code_challenge:
        return False
    if not (43 <= len(code_verifier) <= 128):
        return False
    if not re.match(r"^[A-Za-z0-9\-._~]+$", code_verifier):
        return False
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    computed = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return secrets.compare_digest(computed, code_challenge)


class OAuthProvider(AuthProvider):
    """
    Complete OAuth 2.0 PKCE Authorization Server and Resource Server Provider.
    Enforces Host-Owner Proof (Terminal PIN) on consent approval, bounded in-memory state,
    RFC 7591 dynamic client registration, RFC 7636 S256 PKCE, and permission ceilings.
    """

    OAUTH_PATHS = {
        "/.well-known/oauth-authorization-server",
        "/.well-known/oauth-protected-resource",
        "/oauth/register",
        "/oauth/authorize",
        "/oauth/approve",
        "/oauth/token",
        "/oauth/revoke",
    }

    def __init__(
        self,
        permission_mode: str = "read_only",
        public_url: Optional[str] = None,
        token_ttl_seconds: int = 3600,
        auth_code_ttl_seconds: int = 300,
        **kwargs: Any,
    ):
        super().__init__(auth_mode="oauth")
        self.permission_mode = (permission_mode or "read_only").lower().strip()
        self._public_url = (public_url or "").rstrip("/") if public_url else None
        self.token_ttl_seconds = token_ttl_seconds
        self.auth_code_ttl_seconds = auth_code_ttl_seconds

        # Cryptographic signing key for HMAC-SHA256 access tokens
        self._signing_key: bytes = secrets.token_bytes(32)

        # In-memory storage for clients, auth codes, tokens, and pending approvals
        # Pre-configured default client strictly permits only RFC 8252 loopback callbacks
        self._clients: Dict[str, Dict[str, Any]] = {
            "mws-default-client": {
                "client_id": "mws-default-client",
                "client_name": "Default MCP Client",
                "redirect_uris": [
                    "http://localhost/callback",
                    "http://127.0.0.1/callback",
                ],
                "grant_types": ["authorization_code"],
                "response_types": ["code"],
                "token_endpoint_auth_method": "none",
            }
        }
        self._pending_authorizations: Dict[str, Dict[str, Any]] = {}
        self._auth_codes: Dict[str, Dict[str, Any]] = {}
        self._active_tokens: Dict[str, Dict[str, Any]] = {}
        self._revoked_tokens: Set[str] = set()

    def _prune_state(self) -> None:
        """Evict expired items and enforce capacity bounds on in-memory state maps."""
        now = time.time()
        # 1. Prune pending authorizations (TTL ~300s, max 50)
        expired_auths = [k for k, v in self._pending_authorizations.items() if now > v.get("expires_at", 0)]
        for k in expired_auths:
            self._pending_authorizations.pop(k, None)
        while len(self._pending_authorizations) >= 50:
            oldest_k = next(iter(self._pending_authorizations))
            self._pending_authorizations.pop(oldest_k, None)

        # 2. Prune auth codes (TTL ~300s, max 100)
        expired_codes = [k for k, v in self._auth_codes.items() if now > v.get("expires_at", 0)]
        for k in expired_codes:
            self._auth_codes.pop(k, None)
        while len(self._auth_codes) >= 100:
            oldest_k = next(iter(self._auth_codes))
            self._auth_codes.pop(oldest_k, None)

        # 3. Prune active tokens (max 500)
        expired_tokens = [k for k, v in self._active_tokens.items() if now > v.get("exp", 0)]
        for k in expired_tokens:
            self._active_tokens.pop(k, None)
        while len(self._active_tokens) >= 500:
            oldest_k = next(iter(self._active_tokens))
            self._active_tokens.pop(oldest_k, None)

        # 4. Prune dynamically registered clients (max 200)
        while len(self._clients) >= 200:
            evictable = [k for k in self._clients if k != "mws-default-client"]
            if not evictable:
                break
            self._clients.pop(evictable[0], None)

        # 5. Prune revoked tokens (max 1000)
        if len(self._revoked_tokens) > 1000:
            self._revoked_tokens = set(list(self._revoked_tokens)[500:])

    def set_public_url(self, public_url: str) -> None:
        """Update public URL once discovered by Cloudflare Tunnel."""
        self._public_url = (public_url or "").rstrip("/")

    def is_oauth_path(self, path: str) -> bool:
        """Check if incoming request path belongs to OAuth protocol endpoints."""
        return path in self.OAUTH_PATHS

    def _get_base_url(self, request: Request) -> str:
        """Resolve external base URL: public tunnel URL if known, else Host header."""
        if self._public_url:
            return self._public_url
        host = request.headers.get("host") or "127.0.0.1"
        scheme = "https" if request.headers.get("x-forwarded-proto") == "https" else "http"
        return f"{scheme}://{host}"

    def _mint_token(self, payload: Dict[str, Any]) -> str:
        """Mint a cryptographically signed HMAC-SHA256 Bearer access token."""
        payload_bytes = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode("utf-8")).rstrip(b"=")
        sig = hmac.new(self._signing_key, payload_bytes, hashlib.sha256).digest()
        sig_str = base64.urlsafe_b64encode(sig).decode("ascii").rstrip("=")
        return f"{payload_bytes.decode('ascii')}.{sig_str}"

    def _verify_token(self, token: str) -> Tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
        """
        Verify signed HMAC-SHA256 Bearer access token.
        Returns (is_valid, payload, error_description).
        """
        if not token or "." not in token:
            return False, None, "Malformed token structure"
        parts = token.split(".")
        if len(parts) != 2:
            return False, None, "Malformed token parts"
        payload_part, sig_part = parts[0], parts[1]

        # Constant-time signature verification
        expected_sig = hmac.new(self._signing_key, payload_part.encode("ascii"), hashlib.sha256).digest()
        expected_sig_str = base64.urlsafe_b64encode(expected_sig).decode("ascii").rstrip("=")
        if not secrets.compare_digest(sig_part, expected_sig_str):
            return False, None, "Invalid token signature"

        # Decode payload
        try:
            padded_payload = payload_part + "=" * (-len(payload_part) % 4)
            payload = json.loads(base64.urlsafe_b64decode(padded_payload).decode("utf-8"))
        except Exception:
            return False, None, "Invalid token payload encoding"

        jti = payload.get("jti")
        if not jti or jti in self._revoked_tokens:
            return False, None, "Token has been revoked"

        exp = payload.get("exp", 0)
        if time.time() > exp:
            return False, None, "Token has expired"

        return True, payload, None

    # ---------------------------------------------------------------------------
    # OAuth Protocol Endpoint Handlers
    # ---------------------------------------------------------------------------

    async def handle_oauth_request(self, request: Request) -> Response:
        """Dispatch incoming request to appropriate OAuth endpoint handler."""
        if request.method == "OPTIONS":
            return Response(
                status_code=204,
                headers={
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
                    "Access-Control-Allow-Headers": "Content-Type, Authorization",
                },
            )

        path = request.url.path
        if path == "/.well-known/oauth-authorization-server":
            return self._handle_discovery_server(request)
        elif path == "/.well-known/oauth-protected-resource":
            return self._handle_discovery_resource(request)
        elif path == "/oauth/register":
            return await self._handle_register(request)
        elif path == "/oauth/authorize":
            return self._handle_authorize(request)
        elif path == "/oauth/approve":
            return await self._handle_approve(request)
        elif path == "/oauth/token":
            return await self._handle_token(request)
        elif path == "/oauth/revoke":
            return await self._handle_revoke(request)
        return JSONResponse({"error": "not_found"}, status_code=404)

    def _handle_discovery_server(self, request: Request) -> JSONResponse:
        """RFC 8414 Authorization Server Metadata endpoint."""
        base_url = self._get_base_url(request)
        metadata = {
            "issuer": base_url,
            "authorization_endpoint": f"{base_url}/oauth/authorize",
            "token_endpoint": f"{base_url}/oauth/token",
            "registration_endpoint": f"{base_url}/oauth/register",
            "revocation_endpoint": f"{base_url}/oauth/revoke",
            "response_types_supported": ["code"],
            "response_modes_supported": ["query"],
            "grant_types_supported": ["authorization_code"],
            "code_challenge_methods_supported": ["S256"],
            "token_endpoint_auth_methods_supported": ["none"],
            "scopes_supported": [SCOPE_READ, SCOPE_WRITE],
        }
        return JSONResponse(metadata, headers={"Access-Control-Allow-Origin": "*"})

    def _handle_discovery_resource(self, request: Request) -> JSONResponse:
        """RFC 9728 Protected Resource Metadata endpoint."""
        base_url = self._get_base_url(request)
        metadata = {
            "resource": f"{base_url}/mcp",
            "authorization_servers": [base_url],
            "scopes_supported": [SCOPE_READ, SCOPE_WRITE],
            "bearer_methods_supported": ["header"],
        }
        return JSONResponse(metadata, headers={"Access-Control-Allow-Origin": "*"})

    async def _handle_register(self, request: Request) -> Response:
        """
        RFC 7591 Dynamic Client Registration endpoint.
        Issues generated client_id bound to approved redirect_uris.
        """
        if request.method != "POST":
            return JSONResponse({"error": "invalid_request", "error_description": "POST required"}, status_code=405)

        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"error": "invalid_request", "error_description": "Valid JSON body required"}, status_code=400)

        redirect_uris = body.get("redirect_uris")
        if not redirect_uris or not isinstance(redirect_uris, list):
            return JSONResponse(
                {"error": "invalid_client_metadata", "error_description": "redirect_uris list is required"},
                status_code=400,
            )

        validated_uris = []
        for uri in redirect_uris:
            if not is_valid_redirect_uri(uri):
                return JSONResponse(
                    {
                        "error": "invalid_redirect_uri",
                        "error_description": f"Invalid redirect_uri: '{uri}'. Must be https:// or http:// loopback.",
                    },
                    status_code=400,
                )
            validated_uris.append(uri.strip())

        client_name = str(body.get("client_name") or "Registered MCP Client").strip()
        client_id = f"mws_client_{secrets.token_hex(8)}"

        client_record = {
            "client_id": client_id,
            "client_name": client_name,
            "redirect_uris": validated_uris,
            "grant_types": body.get("grant_types", ["authorization_code"]),
            "response_types": body.get("response_types", ["code"]),
            "token_endpoint_auth_method": body.get("token_endpoint_auth_method", "none"),
            "created_at": time.time(),
        }
        self._prune_state()
        self._clients[client_id] = client_record

        return JSONResponse(client_record, status_code=201, headers={"Access-Control-Allow-Origin": "*"})

    def _handle_authorize(self, request: Request) -> Response:
        """
        RFC 7636 Authorization Endpoint with mandatory S256 PKCE.
        Renders HTML consent page and prints Operator Approval PIN to terminal.
        """
        qp = request.query_params
        response_type = qp.get("response_type")
        client_id = qp.get("client_id")
        redirect_uri = qp.get("redirect_uri")
        code_challenge = qp.get("code_challenge")
        code_challenge_method = qp.get("code_challenge_method")
        scope = qp.get("scope", SCOPE_READ)
        state = qp.get("state")

        # RFC 9700 Security BCP: If client_id or redirect_uri is invalid, NEVER redirect
        if not client_id or client_id not in self._clients:
            safe_client_id = html.escape(str(client_id or ""))
            return HTMLResponse(
                f"<h2>400 Bad Request: Invalid client_id</h2><p>Client '{safe_client_id}' is not registered.</p>",
                status_code=400,
            )

        client = self._clients[client_id]
        client_name = client.get("client_name", client_id)

        if not redirect_uri or not is_valid_redirect_uri(redirect_uri):
            return HTMLResponse(
                "<h2>400 Bad Request: Invalid redirect_uri</h2><p>The redirect URI is invalid or malformed.</p>",
                status_code=400,
            )

        # Exact matching against registered redirect URIs (or prefix match if loopback port dynamic)
        is_registered_uri = False
        parsed_req_uri = urllib.parse.urlsplit(redirect_uri)

        # RFC 8252 §7.3 loopback port allowance for native desktop clients on mws-default-client
        if client_id == "mws-default-client" and is_loopback_uri(redirect_uri):
            is_registered_uri = True
        else:
            for reg_uri in client.get("redirect_uris", []):
                if reg_uri == redirect_uri:
                    is_registered_uri = True
                    break
                # RFC 8252 loopback port allowance for registered loopback clients
                parsed_reg = urllib.parse.urlsplit(reg_uri)
                if (
                    parsed_reg.scheme == parsed_req_uri.scheme == "http"
                    and (parsed_reg.hostname or "").lower() == (parsed_req_uri.hostname or "").lower() in ("127.0.0.1", "localhost", "::1")
                    and parsed_reg.path == parsed_req_uri.path
                ):
                    is_registered_uri = True
                    break

        if not is_registered_uri:
            return HTMLResponse(
                "<h2>400 Bad Request: Unregistered redirect_uri</h2><p>URI is not registered for this client.</p>",
                status_code=400,
            )

        # Validate response_type
        if response_type != "code":
            params = {
                "error": "unsupported_response_type",
                "error_description": "Only response_type=code is supported",
            }
            if state:
                params["state"] = state
            return RedirectResponse(build_redirect_url(redirect_uri, params), status_code=302)

        # Validate mandatory S256 PKCE
        if not code_challenge or code_challenge_method != "S256":
            params = {
                "error": "invalid_request",
                "error_description": "Mandatory PKCE with code_challenge_method=S256 required",
            }
            if state:
                params["state"] = state
            return RedirectResponse(build_redirect_url(redirect_uri, params), status_code=302)

        # Scope ceiling check: requested vs server ceiling
        requested_scope = SCOPE_WRITE if "write" in scope.lower() else SCOPE_READ
        effective_mode = "read_write" if (self.permission_mode == "read_write" and requested_scope == SCOPE_WRITE) else "read_only"

        # Generate high-entropy transaction ID, CSRF token, and Host-Owner Approval PIN
        tx_id = secrets.token_urlsafe(32)
        csrf_token = secrets.token_urlsafe(32)
        pin = "".join(secrets.choice("0123456789") for _ in range(6))
        dest_host = parsed_req_uri.netloc or redirect_uri

        self._prune_state()
        self._pending_authorizations[tx_id] = {
            "tx_id": tx_id,
            "csrf_token": csrf_token,
            "pin": pin,
            "client_id": client_id,
            "client_name": client_name,
            "redirect_uri": redirect_uri,
            "dest_host": dest_host,
            "scope": requested_scope,
            "effective_mode": effective_mode,
            "code_challenge": code_challenge,
            "state": state,
            "attempts": 0,
            "expires_at": time.time() + self.auth_code_ttl_seconds,
        }

        # Prominently print Host-Owner PIN and target destination to operator terminal
        print("\n" + "=" * 64)
        print(" 🔐  MWS REMOTE TUNNEL: OAUTH AUTHORIZATION REQUEST")
        print("=" * 64)
        print(f" • Client:        {client_name} ({client_id})")
        print(f" • Target Host:   {dest_host}")
        print(f" • Requested:     {requested_scope} (Effective Mode: {effective_mode.upper()})")
        print(f" • Redirect URI:  {redirect_uri}")
        print(f" 👉 Operator Approval PIN: [ {pin} ]")
        print("    (Enter this 6-digit PIN in your browser to approve connection)")
        print("=" * 64 + "\n", flush=True)

        # Render HTML Consent Page
        safe_client_name = html.escape(client_name)
        safe_client_id = html.escape(client_id)
        safe_dest_host = html.escape(dest_host)
        safe_requested_scope = html.escape(requested_scope)
        safe_effective_mode = html.escape(effective_mode)
        safe_redirect_uri = html.escape(redirect_uri)
        safe_tx_id = html.escape(tx_id)
        safe_csrf_token = html.escape(csrf_token)

        html_body = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Authorize MCP Client — MWS</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #0f172a; color: #f8fafc; display: flex; align-items: center; justify-content: center; min-height: 100vh; margin: 0; }}
        .card {{ background: #1e293b; border-radius: 12px; box-shadow: 0 10px 25px rgba(0,0,0,0.5); padding: 32px; width: 100%; max-width: 480px; border: 1px solid #334155; }}
        h1 {{ font-size: 22px; margin-top: 0; color: #38bdf8; }}
        .badge {{ display: inline-block; padding: 4px 10px; border-radius: 9999px; font-size: 12px; font-weight: 600; background: #0369a1; color: #e0f2fe; margin-bottom: 16px; }}
        .badge.read_write {{ background: #b45309; color: #fef3c7; }}
        p {{ font-size: 14px; line-height: 1.5; color: #94a3b8; }}
        .info {{ background: #0f172a; border-radius: 8px; padding: 12px 16px; margin: 16px 0; border: 1px solid #334155; font-size: 13px; }}
        .info div {{ margin-bottom: 6px; }}
        .info strong {{ color: #cbd5e1; }}
        .target-host {{ color: #38bdf8; font-weight: 600; }}
        .pin-box {{ margin: 20px 0; }}
        .pin-box label {{ display: block; font-size: 13px; font-weight: 600; color: #38bdf8; margin-bottom: 8px; }}
        .pin-box input {{ width: 100%; box-sizing: border-box; padding: 12px; font-size: 20px; letter-spacing: 4px; text-align: center; border-radius: 6px; border: 2px solid #38bdf8; background: #0f172a; color: #fff; }}
        .actions {{ display: flex; gap: 12px; margin-top: 24px; }}
        button {{ flex: 1; padding: 12px; border-radius: 6px; font-size: 14px; font-weight: 600; cursor: pointer; border: none; }}
        .btn-approve {{ background: #0284c7; color: white; }}
        .btn-approve:hover {{ background: #0369a1; }}
        .btn-deny {{ background: #334155; color: #94a3b8; }}
        .btn-deny:hover {{ background: #475569; color: white; }}
    </style>
</head>
<body>
    <div class="card">
        <h1>Authorize Client</h1>
        <div class="badge {safe_effective_mode}">PERMISSION CEILING: {safe_effective_mode.upper()}</div>
        <p><strong>{safe_client_name}</strong> is requesting access to execute tools through your MWS remote tunnel.</p>
        
        <div class="info">
            <div><strong>Client ID:</strong> <code>{safe_client_id}</code></div>
            <div><strong>Target Host:</strong> <span class="target-host">{safe_dest_host}</span></div>
            <div><strong>Requested Scope:</strong> <code>{safe_requested_scope}</code></div>
            <div><strong>Effective Mode:</strong> <code>{safe_effective_mode}</code></div>
            <div><strong>Redirect URI:</strong> <code>{safe_redirect_uri}</code></div>
        </div>

        <form method="POST" action="/oauth/approve">
            <input type="hidden" name="tx_id" value="{safe_tx_id}">
            <input type="hidden" name="csrf_token" value="{safe_csrf_token}">
            <div class="pin-box">
                <label for="operator_pin">Enter 6-digit Operator PIN from your MWS terminal:</label>
                <input type="text" id="operator_pin" name="operator_pin" maxlength="6" pattern="[0-9]{{6}}" required autofocus placeholder="123456" autocomplete="off">
            </div>
            <div class="actions">
                <button type="submit" name="action" value="deny" class="btn-deny">Deny</button>
                <button type="submit" name="action" value="approve" class="btn-approve">Approve Access</button>
            </div>
        </form>
    </div>
</body>
</html>"""
        return HTMLResponse(html_body)

    async def _handle_approve(self, request: Request) -> Response:
        """
        Processes consent approval form with Host-Owner Proof (Terminal PIN) and CSRF protection.
        Allows up to 3 PIN attempts before burning the session; burns session on success.
        """
        if request.method != "POST":
            return JSONResponse({"error": "invalid_request", "error_description": "POST required"}, status_code=405)

        form = await request.form()
        tx_id = str(form.get("tx_id", "")).strip()
        action = str(form.get("action", "")).strip().lower()
        operator_pin = str(form.get("operator_pin", "")).strip()
        csrf_token = str(form.get("csrf_token", "")).strip()

        # 1. Action whitelist check
        if action not in ("approve", "deny"):
            return HTMLResponse(
                "<h2>400 Bad Request: Invalid Action</h2><p>Action must be 'approve' or 'deny'.</p>",
                status_code=400,
            )

        # 2. Lookup pending authorization transaction
        tx = self._pending_authorizations.get(tx_id)
        if not tx or time.time() > tx["expires_at"]:
            self._pending_authorizations.pop(tx_id, None)
            return HTMLResponse(
                "<h2>400 Bad Request: Expired or Invalid Request</h2><p>This authorization transaction has expired or already been consumed. Please retry from your client.</p>",
                status_code=400,
            )

        redirect_uri = tx["redirect_uri"]
        state = tx.get("state")

        # 3. CSRF token validation before performing any action
        expected_csrf = tx.get("csrf_token", "")
        if not expected_csrf or not secrets.compare_digest(csrf_token, expected_csrf):
            return HTMLResponse(
                "<h2>403 Forbidden: Invalid or Missing CSRF Token</h2><p>Cross-site request forgery verification failed.</p>",
                status_code=403,
            )

        # 4. Handle user denial
        if action == "deny":
            self._pending_authorizations.pop(tx_id, None)
            params = {
                "error": "access_denied",
                "error_description": "User denied authorization",
            }
            if state:
                params["state"] = state
            return RedirectResponse(build_redirect_url(redirect_uri, params), status_code=302)

        # 5. Mandatory Host-Owner Proof Verification
        pin_matched = secrets.compare_digest(operator_pin, tx["pin"])
        if not pin_matched:
            tx["attempts"] += 1
            remaining = 3 - tx["attempts"]
            if remaining <= 0:
                self._pending_authorizations.pop(tx_id, None)
                return HTMLResponse(
                    "<h2>403 Forbidden: Too Many Failed PIN Attempts</h2><p>Maximum PIN attempts exceeded. This authorization session has been terminated.</p>",
                    status_code=403,
                )
            return HTMLResponse(
                f"<h2>403 Forbidden: Invalid Operator PIN</h2>"
                f"<p>The entered PIN was incorrect. You have <strong>{remaining}</strong> attempt(s) remaining.</p>"
                f"<p><a href='javascript:history.back()'>Click here to return and try again</a></p>",
                status_code=403,
            )

        # 6. PIN matched successfully: burn transaction session & mint single-use authorization code
        self._pending_authorizations.pop(tx_id, None)
        code = f"mws_code_{secrets.token_urlsafe(32)}"
        self._prune_state()
        self._auth_codes[code] = {
            "code": code,
            "client_id": tx["client_id"],
            "redirect_uri": redirect_uri,
            "code_challenge": tx["code_challenge"],
            "scope": tx["scope"],
            "effective_mode": tx["effective_mode"],
            "expires_at": time.time() + self.auth_code_ttl_seconds,
        }

        params = {"code": code}
        if state:
            params["state"] = state
        success_url = build_redirect_url(redirect_uri, params)

        print(f"✅ OAuth authorization approved for {tx['client_name']} (Mode: {tx['effective_mode']})", flush=True)
        return RedirectResponse(success_url, status_code=302)

    async def _handle_token(self, request: Request) -> JSONResponse:
        """
        RFC 7636 Token Endpoint with atomic single-use code consumption and S256 PKCE verification.
        """
        cors_headers = {"Access-Control-Allow-Origin": "*"}
        if request.method != "POST":
            return JSONResponse(
                {"error": "invalid_request", "error_description": "POST required"},
                status_code=405,
                headers=cors_headers,
            )

        # Parse form or JSON body
        content_type = request.headers.get("content-type", "")
        if "application/json" in content_type:
            try:
                body = await request.json()
            except Exception:
                body = {}
        else:
            body = await request.form()

        grant_type = body.get("grant_type")
        code = body.get("code")
        redirect_uri = body.get("redirect_uri")
        client_id = body.get("client_id")
        code_verifier = body.get("code_verifier")

        if grant_type != "authorization_code":
            return JSONResponse(
                {"error": "unsupported_grant_type", "error_description": "grant_type must be 'authorization_code'"},
                status_code=400,
                headers=cors_headers,
            )

        if not code:
            return JSONResponse(
                {"error": "invalid_request", "error_description": "code is required"},
                status_code=400,
                headers=cors_headers,
            )

        # ATOMIC SINGLE-USE CODE CONSUMPTION & REPLAY DETECTION
        # The authorization code is popped immediately; failure on any subsequent check leaves it burned.
        auth_record = self._auth_codes.pop(code, None)
        if not auth_record:
            return JSONResponse(
                {
                    "error": "invalid_grant",
                    "error_description": "Authorization code is invalid, expired, or has already been used.",
                },
                status_code=400,
                headers=cors_headers,
            )

        if time.time() > auth_record["expires_at"]:
            return JSONResponse(
                {"error": "invalid_grant", "error_description": "Authorization code has expired."},
                status_code=400,
                headers=cors_headers,
            )

        # Exact client_id verification (RFC 6749 §4.1.3: required for public clients)
        if not client_id or auth_record["client_id"] != client_id:
            return JSONResponse(
                {"error": "invalid_grant", "error_description": "client_id mismatch or missing."},
                status_code=400,
                headers=cors_headers,
            )

        # Exact redirect_uri verification
        if not redirect_uri or auth_record["redirect_uri"] != redirect_uri:
            return JSONResponse(
                {"error": "invalid_grant", "error_description": "redirect_uri mismatch."},
                status_code=400,
                headers=cors_headers,
            )

        # RFC 7636 S256 PKCE verification
        if not code_verifier or not verify_pkce(code_verifier, auth_record["code_challenge"]):
            return JSONResponse(
                {"error": "invalid_grant", "error_description": "PKCE verification failed."},
                status_code=400,
                headers=cors_headers,
            )

        # Mint signed Bearer Access Token
        jti = secrets.token_hex(16)
        exp = int(time.time()) + self.token_ttl_seconds
        scope = auth_record["scope"]
        effective_mode = auth_record["effective_mode"]

        token_payload = {
            "sub": auth_record["client_id"],
            "scope": scope,
            "mode": effective_mode,
            "exp": exp,
            "jti": jti,
        }
        access_token = self._mint_token(token_payload)
        self._prune_state()
        self._active_tokens[jti] = token_payload

        resp_data = {
            "access_token": access_token,
            "token_type": "Bearer",
            "expires_in": self.token_ttl_seconds,
            "scope": scope,
        }
        return JSONResponse(
            resp_data,
            headers={
                "Cache-Control": "no-store",
                "Pragma": "no-cache",
                "Access-Control-Allow-Origin": "*",
            },
        )

    async def _handle_revoke(self, request: Request) -> JSONResponse:
        """RFC 7009 Token Revocation endpoint with HMAC signature verification."""
        if request.method != "POST":
            return JSONResponse(
                {"error": "invalid_request"},
                status_code=405,
                headers={"Access-Control-Allow-Origin": "*"},
            )

        content_type = request.headers.get("content-type", "")
        if "application/json" in content_type:
            try:
                body = await request.json()
            except Exception:
                body = {}
        else:
            body = await request.form()

        token = body.get("token")
        if token and isinstance(token, str):
            is_valid, payload, _ = self._verify_token(token)
            if is_valid and payload:
                jti = payload.get("jti")
                if jti:
                    self._revoked_tokens.add(jti)
                    self._active_tokens.pop(jti, None)
        return JSONResponse({"status": "revoked"}, headers={"Access-Control-Allow-Origin": "*"})

    # ---------------------------------------------------------------------------
    # MCP Protected Endpoint Authentication & Permission Management
    # ---------------------------------------------------------------------------

    async def authenticate(self, request: Any) -> Optional[Any]:
        """
        Validate Bearer access token on protected MCP endpoints.
        Returns None if accepted, or JSONResponse 401 with WWW-Authenticate header.
        """
        path = getattr(getattr(request, "url", None), "path", "")
        if self.is_oauth_path(path):
            return None

        auth_header = ""
        if hasattr(request, "headers") and request.headers is not None:
            for k, v in request.headers.items():
                if k.lower() == "authorization":
                    auth_header = v or ""
                    break

        base_url = self._get_base_url(request)
        resource_metadata_url = f"{base_url}/.well-known/oauth-protected-resource"

        if not auth_header.startswith("Bearer "):
            headers = {
                "WWW-Authenticate": f'Bearer realm="mcp-win-stdio", resource_metadata="{resource_metadata_url}"'
            }
            return JSONResponse(
                {
                    "error": "unauthorized",
                    "message": "Authentication required. Please authenticate via OAuth 2.0 PKCE.",
                },
                status_code=401,
                headers=headers,
            )

        token = auth_header[7:].strip()
        is_valid, payload, err_desc = self._verify_token(token)

        if not is_valid or not payload:
            headers = {
                "WWW-Authenticate": f'Bearer error="invalid_token", error_description="{err_desc or "Invalid token"}", resource_metadata="{resource_metadata_url}"'
            }
            return JSONResponse(
                {
                    "error": "unauthorized",
                    "message": f"Authentication failed: {err_desc or 'Invalid access token'}.",
                },
                status_code=401,
                headers=headers,
            )

        # Attach claims to request state for request-scoped permission resolution
        if hasattr(request, "state"):
            setattr(request.state, "oauth_claims", payload)

        return None

    def get_request_permission_mode(self, request: Any, default_mode: str = "read_only") -> str:
        """
        Compute effective permission mode for request bounded by server ceiling.
        effective_mode = min(server_configured_mode, token_scope_mode)
        """
        claims = getattr(getattr(request, "state", None), "oauth_claims", None)
        if not claims or not isinstance(claims, dict):
            return default_mode

        token_mode = claims.get("mode") or ("read_write" if claims.get("scope") == SCOPE_WRITE else "read_only")
        if default_mode == "read_only" or token_mode != "read_write":
            return "read_only"
        return "read_write"

    def get_client_config(self, public_url: str) -> Dict[str, Any]:
        """Generate client configuration dictionary and setup guide for OAuth."""
        base_url = (public_url or "").rstrip("/")
        mcp_endpoint = f"{base_url}/mcp" if base_url else ""
        return {
            "mcpServers": {
                "mws": {
                    "url": mcp_endpoint,
                }
            },
            "auth": {
                "type": "oauth2",
                "authorization_server": base_url,
                "discovery_url": f"{base_url}/.well-known/oauth-authorization-server",
                "protected_resource_url": f"{base_url}/.well-known/oauth-protected-resource",
            },
        }

    async def shutdown(self) -> None:
        """Clean up active sessions and revoked tokens upon tunnel termination."""
        self._pending_authorizations.clear()
        self._auth_codes.clear()
        self._active_tokens.clear()
        self._revoked_tokens.clear()
