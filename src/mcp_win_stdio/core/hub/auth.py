"""
Bearer Authentication and Server-Controlled Session Management Middleware for MCP Hub.
Enforces constant-time token comparison, strict remote-binding authentication,
fail-closed error semantics, and server-controlled session token issuance.
"""

import hmac
import ipaddress
import json
import logging
import os
import secrets
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)

# Standard health / status endpoints
DEFAULT_HEALTH_ROUTES: Set[str] = frozenset({"/health", "/status"})


class SessionManager:
    """
    Server-controlled session registry preventing client-driven session spoofing.
    Issues cryptographically secure random session tokens, manages idle expiry,
    and isolates per-client state.
    """

    def __init__(self, ttl_seconds: float = 3600.0):
        self.ttl_seconds = ttl_seconds
        self._sessions: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.RLock()

    def create_session(
        self,
        client_ip: Optional[str] = None,
        correlation_hint: Optional[str] = None,
    ) -> str:
        """Issue a fresh, cryptographically unguessable server-side session token."""
        session_id = f"mws_sess_{secrets.token_hex(16)}"
        now = time.time()
        with self._lock:
            self._sessions[session_id] = {
                "session_id": session_id,
                "client_ip": client_ip,
                "correlation_hint": correlation_hint,
                "created_at": now,
                "last_active": now,
                "data": {},
            }
        return session_id

    def get_or_create_session(
        self,
        token: Optional[str] = None,
        client_ip: Optional[str] = None,
        correlation_hint: Optional[str] = None,
    ) -> Tuple[str, bool]:
        """
        Validate existing server session token. If invalid, expired, or missing,
        generate a new server-controlled session.
        Client correlation hints are NEVER accepted as authoritative session IDs.

        Returns:
            Tuple[str, bool]: (session_id, is_new_session)
        """
        now = time.time()
        with self._lock:
            if token and token in self._sessions:
                sess = self._sessions[token]
                # Check idle TTL expiration
                if now - sess["last_active"] <= self.ttl_seconds:
                    sess["last_active"] = now
                    if correlation_hint:
                        sess["correlation_hint"] = correlation_hint
                    return token, False
                else:
                    # Expired session; purge it
                    del self._sessions[token]

        # Generate a fresh server-controlled session
        new_id = self.create_session(client_ip=client_ip, correlation_hint=correlation_hint)
        return new_id, True

    def get_session_data(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve mutable data dictionary for a valid, non-expired session."""
        now = time.time()
        with self._lock:
            sess = self._sessions.get(session_id)
            if sess:
                if now - sess["last_active"] <= self.ttl_seconds:
                    sess["last_active"] = now
                    return sess["data"]
                else:
                    del self._sessions[session_id]
            return None

    def invalidate(self, session_id: str) -> bool:
        """Explicitly destroy a server session."""
        with self._lock:
            return self._sessions.pop(session_id, None) is not None

    def cleanup_idle(self) -> int:
        """Purge all sessions that have exceeded the idle TTL."""
        now = time.time()
        purged = 0
        with self._lock:
            expired = [
                sid
                for sid, s in self._sessions.items()
                if now - s["last_active"] > self.ttl_seconds
            ]
            for sid in expired:
                del self._sessions[sid]
                purged += 1
        return purged

    def active_session_count(self) -> int:
        """Return the number of active sessions."""
        with self._lock:
            return len(self._sessions)


class BearerAuthMiddleware:
    """
    ASGI Middleware implementing strict Bearer authentication and server-controlled sessions.
    Guarantees:
      1. Mandatory authentication for non-loopback bindings before any route/tool is reached.
      2. Constant-time token comparison via hmac.compare_digest.
      3. Zero credential leakage: tokens and authorization headers are never logged or reflected.
      4. Explicit health check route policy.
      5. Fail-closed rejection with 401 Unauthorized.
      6. Server-managed session issuance and context binding.
    """

    def __init__(
        self,
        app: Callable[..., Any],
        auth_token_env: str = "MWS_HTTP_AUTH_TOKEN",
        bind_host: str = "127.0.0.1",
        allow_loopback_unauthenticated: bool = False,
        health_routes: Optional[Set[str]] = None,
        allow_loopback_health_unauthenticated: bool = True,
        session_manager: Optional[SessionManager] = None,
    ):
        self.app = app
        self.auth_token_env = auth_token_env
        self.bind_host = bind_host.strip().lower()
        self.allow_loopback_unauthenticated = allow_loopback_unauthenticated
        self.health_routes = health_routes if health_routes is not None else DEFAULT_HEALTH_ROUTES
        self.allow_loopback_health_unauthenticated = allow_loopback_health_unauthenticated
        self.session_manager = session_manager or SessionManager()

        is_loop = False
        if self.bind_host in ("localhost", "testserver"):
            is_loop = True
        else:
            try:
                is_loop = ipaddress.ip_address(self.bind_host.strip("[]")).is_loopback
            except ValueError:
                is_loop = False
        self._is_loopback_binding = is_loop
        self.allowed_hosts: Set[str] = {
            "127.0.0.1",
            "localhost",
            "::1",
            "[::1]",
            "testserver",
        }

    async def __call__(
        self,
        scope: Dict[str, Any],
        receive: Callable[..., Any],
        send: Callable[..., Any],
    ) -> None:
        # Pass ASGI lifespan events directly
        if scope["type"] == "lifespan":
            await self.app(scope, receive, send)
            return

        if scope["type"] != "http":
            # Reject unsupported protocols
            await self._send_response(
                send,
                status=400,
                message="Unsupported protocol scope.",
            )
            return

        client = scope.get("client")
        client_host = client[0] if client else None
        is_loopback_client = client_host in ("127.0.0.1", "::1", "localhost", "testclient")
        path = scope.get("path", "")

        # 0. Enforce Host header validation to defend against DNS rebinding
        host_header = self._get_header(scope, b"host")
        if host_header:
            host_str = host_header.decode("ascii", errors="replace").strip()
            clean_host = host_str.lower()
            if ":" in clean_host and not clean_host.startswith("["):
                clean_host = clean_host.split(":", 1)[0]
            elif clean_host.startswith("[") and "]" in clean_host:
                clean_host = clean_host[: clean_host.index("]") + 1]

            if clean_host not in self.allowed_hosts:
                await self._send_response(
                    send,
                    status=421,
                    message="Invalid Host header.",
                )
                return

        # 1. Determine if authentication is required for this request
        auth_required = True

        # Policy A: Health routes
        if path in self.health_routes:
            if self.allow_loopback_health_unauthenticated and is_loopback_client:
                auth_required = False

        # Policy B: Loopback binding unauthenticated exemption
        elif self._is_loopback_binding and self.allow_loopback_unauthenticated and is_loopback_client:
            auth_required = False

        # 2. Enforce authentication if required
        if auth_required:
            auth_header = self._get_header(scope, b"authorization")
            if not auth_header:
                await self._send_401(send, "Missing Authorization header.")
                return

            # Validate Bearer scheme
            parts = auth_header.strip().split(b" ", 1)
            if len(parts) != 2 or parts[0].lower() != b"bearer":
                await self._send_401(send, "Authorization header must use Bearer scheme.")
                return

            provided_token = parts[1].strip()

            # Dynamic request-time token lookup from environment
            expected_token = os.environ.get(self.auth_token_env, "").strip()

            # Fail-closed invariant: If expected token is not configured or empty, reject all requests
            if not expected_token:
                logger.warning(
                    "BearerAuthMiddleware: Expected token in '%s' is unset or empty. Rejecting request fail-closed.",
                    self.auth_token_env,
                )
                await self._send_401(send, "Authentication service is not configured.")
                return

            # Constant-time comparison to prevent timing attacks
            is_valid = hmac.compare_digest(
                provided_token,
                expected_token.encode("utf-8"),
            )
            if not is_valid:
                await self._send_401(send, "Invalid Bearer token.")
                return

        # 3. Server-Controlled Session Resolution
        cookie_header = self._get_header(scope, b"cookie")
        session_token_header = self._get_header(scope, b"x-mws-session-token") or self._get_header(
            scope, b"mws-session-token"
        )
        correlation_header = self._get_header(scope, b"x-mws-session-id")

        raw_token: Optional[str] = None
        if session_token_header:
            raw_token = session_token_header.decode("utf-8", errors="replace").strip()
        elif cookie_header:
            raw_token = self._extract_cookie(cookie_header, "mws_session")

        correlation_hint: Optional[str] = None
        if correlation_header:
            # Client-provided ID is ONLY a correlation hint, never authoritative identity
            correlation_hint = correlation_header.decode("utf-8", errors="replace").strip()

        session_id, is_new = self.session_manager.get_or_create_session(
            token=raw_token,
            client_ip=client_host,
            correlation_hint=correlation_hint,
        )

        # Inject server-verified session identity into ASGI scope
        scope["session_id"] = session_id
        scope["session_data"] = self.session_manager.get_session_data(session_id)
        scope["auth"] = {"authenticated": True, "method": "bearer" if auth_required else "loopback"}

        # 4. Intercept response to inject session token headers/cookies if newly issued
        async def custom_send(message: Dict[str, Any]) -> None:
            if is_new and message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                # Add X-MWS-Session-Token
                headers.append((b"x-mws-session-token", session_id.encode("ascii")))
                # Add Set-Cookie
                cookie_val = f"mws_session={session_id}; Path=/; HttpOnly; SameSite=Strict"
                headers.append((b"set-cookie", cookie_val.encode("ascii")))
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, custom_send)

    @staticmethod
    def _get_header(scope: Dict[str, Any], target_name: bytes) -> Optional[bytes]:
        """Extract a header by case-insensitive name from ASGI scope."""
        target_lower = target_name.lower()
        for name, value in scope.get("headers", []):
            if name.lower() == target_lower:
                return value
        return None

    @staticmethod
    def _extract_cookie(cookie_header: bytes, cookie_name: str) -> Optional[str]:
        """Parse cookie string safely without throwing exceptions."""
        try:
            cookie_str = cookie_header.decode("utf-8", errors="replace")
            for part in cookie_str.split(";"):
                part = part.strip()
                if part.startswith(f"{cookie_name}="):
                    return part[len(cookie_name) + 1 :].strip()
        except Exception:
            pass
        return None

    async def _send_401(self, send: Callable[..., Any], message: str) -> None:
        """Send a strict 401 Unauthorized response without reflecting client inputs."""
        payload = json.dumps(
            {
                "error": "Unauthorized",
                "message": message,
            }
        ).encode("utf-8")

        await send(
            {
                "type": "http.response.start",
                "status": 401,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"www-authenticate", b'Bearer realm="mws"'),
                    (b"cache-control", b"no-store"),
                    (b"content-length", str(len(payload)).encode("ascii")),
                ],
            }
        )
        await send(
            {
                "type": "http.response.body",
                "body": payload,
            }
        )

    async def _send_response(
        self,
        send: Callable[..., Any],
        status: int,
        message: str,
    ) -> None:
        """Send a generic error response."""
        payload = json.dumps({"error": message}).encode("utf-8")
        await send(
            {
                "type": "http.response.start",
                "status": status,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"cache-control", b"no-store"),
                    (b"content-length", str(len(payload)).encode("ascii")),
                ],
            }
        )
        await send(
            {
                "type": "http.response.body",
                "body": payload,
            }
        )
