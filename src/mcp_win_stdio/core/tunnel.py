"""
MWS Remote Cloudflare Tunnel Manager.
Exposes the local Streamable HTTP MCP endpoint to the public Internet via Cloudflare Tunnel (cloudflared),
enabling ChatGPT, Gemini, Claude Web, and remote agent platforms to access local mws tools securely.
"""

import json
import logging
import os
import re
import secrets
import shutil
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Tuple

import uvicorn
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from mcp_win_stdio.core.config import (
    CURRENT_PERMISSION_MODE,
    get_tunnel_config,
    load_hierarchical_config,
)
from mcp_win_stdio.core.permissions import (
    CURRENT_ALLOW_SENSITIVE_READS,
    CURRENT_AUTH_MODE,
)
from mcp_win_stdio.core.tunnel_auth import (
    AuthProvider,
    BearerAuthProvider,
    create_auth_provider,
)
from mcp_win_stdio.server.catalog import get_server_catalog
from mcp_win_stdio.server.discovery import discover_available_servers
from mcp_win_stdio.server.server import mcp

logger = logging.getLogger("mcp_win_stdio.tunnel")


class TunnelAuthMiddleware(BaseHTTPMiddleware):
    """
    Generic authentication and permission isolation middleware delegating verification to an AuthProvider.
    Bypasses authentication strictly for health and status endpoints.
    Establishes request-scoped permission context (CURRENT_PERMISSION_MODE) for the lifetime of the request.
    """

    def __init__(self, app: Any, auth_provider: AuthProvider, permission_mode: str = "read_only"):
        super().__init__(app)
        self.auth_provider = auth_provider
        if auth_provider.requires_read_only:
            self.permission_mode = "read_only"
        else:
            self.permission_mode = (permission_mode or "read_only").lower().strip()

    async def dispatch(self, request: Any, call_next: Callable[..., Any]) -> Any:
        path = request.url.path
        if path in ("/health", "/status"):
            return JSONResponse({
                "status": "ok",
                "service": "mws-tunnel",
                "auth_mode": self.auth_provider.auth_mode,
                "timestamp": time.time(),
            })

        # Intercept OAuth endpoints (discovery, registration, authorization, token, revocation)
        if hasattr(self.auth_provider, "is_oauth_path") and self.auth_provider.is_oauth_path(path):
            return await self.auth_provider.handle_oauth_request(request)

        auth_response = await self.auth_provider.authenticate(request)
        if auth_response is not None:
            return auth_response

        # Request-scoped permission context isolation: calculate effective permission bounded by server ceiling
        effective_perm = (
            self.auth_provider.get_request_permission_mode(request, default_mode=self.permission_mode)
            if hasattr(self.auth_provider, "get_request_permission_mode")
            else self.permission_mode
        )
        perm_token = CURRENT_PERMISSION_MODE.set(effective_perm)
        auth_token = CURRENT_AUTH_MODE.set(self.auth_provider.auth_mode)
        allow_sens = getattr(self.auth_provider, "allow_sensitive_reads", False)
        sens_token = CURRENT_ALLOW_SENSITIVE_READS.set(allow_sens)
        try:
            return await call_next(request)
        finally:
            CURRENT_ALLOW_SENSITIVE_READS.reset(sens_token)
            CURRENT_AUTH_MODE.reset(auth_token)
            CURRENT_PERMISSION_MODE.reset(perm_token)


class BearerAuthMiddleware(TunnelAuthMiddleware):
    """
    Backward-compatibility alias for BearerAuthMiddleware.
    """

    def __init__(self, app: Any, token: str, permission_mode: str = "read_only"):
        super().__init__(app, auth_provider=BearerAuthProvider(token=token), permission_mode=permission_mode)


class MwsTunnelManager:
    """
    Orchestrates the local uvicorn StreamableHTTP server, auth provider, and cloudflared quick tunnel.
    """

    def __init__(
        self,
        port: int = 8080,
        mode: str = "read_only",
        token: Optional[str] = None,
        auth_mode: str = "bearer",
        host: str = "127.0.0.1",
        workspace_dir: Optional[Path] = None,
        allow_sensitive_reads: bool = False,
    ):
        self.port = port
        self.mode = mode.lower().strip()
        self.auth_mode = (auth_mode or "bearer").lower().strip()
        self.host = host
        self.workspace_dir = workspace_dir
        self.allow_sensitive_reads = bool(allow_sensitive_reads)

        # Initialize modular AuthProvider
        self.auth_provider = create_auth_provider(
            self.auth_mode,
            token=token,
            permission_mode=self.mode,
            allow_sensitive_reads=self.allow_sensitive_reads,
        )

        # Enforce read_only if auth provider requires it (e.g. unauthenticated 'none' mode)
        if self.auth_provider.requires_read_only and self.mode != "read_only":
            logger.warning("Auth mode '%s' mandates 'read_only' permissions. Overriding mode to 'read_only'.", self.auth_mode)
            self.mode = "read_only"

        # Expose token property for backward compatibility (None in 'none' mode)
        self.token = getattr(self.auth_provider, "token", None)

        self._uvicorn_server: Optional[uvicorn.Server] = None
        self._uvicorn_thread: Optional[threading.Thread] = None
        self._cf_proc: Optional[subprocess.Popen] = None
        self._public_url: Optional[str] = None
        self._stop_event = threading.Event()

    @staticmethod
    def is_cloudflared_installed() -> bool:
        """Check if cloudflared binary is discoverable in PATH."""
        return shutil.which("cloudflared") is not None

    @staticmethod
    def get_cloudflared_version() -> Optional[str]:
        """Return the installed cloudflared version string, or None if not found."""
        if not MwsTunnelManager.is_cloudflared_installed():
            return None
        try:
            res = subprocess.run(
                ["cloudflared", "--version"],
                capture_output=True,
                text=True,
                timeout=3.0,
            )
            if res.returncode == 0:
                first_line = res.stdout.strip().split("\n")[0]
                return first_line.replace("cloudflared version ", "v").split(" (")[0].strip()
        except Exception:
            pass
        return "Installed"

    @staticmethod
    def try_install_cloudflared() -> bool:
        """Attempt to install cloudflared using system package manager (winget on Windows, brew on macOS)."""
        if sys.platform == "win32":
            if shutil.which("winget"):
                try:
                    res = subprocess.run(
                        [
                            "winget",
                            "install",
                            "--id",
                            "Cloudflare.cloudflared",
                            "-e",
                            "--accept-source-agreements",
                            "--accept-package-agreements",
                        ],
                        timeout=180.0,
                    )
                    return res.returncode == 0
                except Exception:
                    return False
        elif sys.platform == "darwin":
            if shutil.which("brew"):
                try:
                    res = subprocess.run(["brew", "install", "cloudflared"], timeout=180.0)
                    return res.returncode == 0
                except Exception:
                    return False
        return False

    def start_local_bridge(self) -> None:
        """Launch uvicorn StreamableHTTP server with configured auth provider in a worker thread."""
        from mcp.server.transport_security import TransportSecuritySettings

        # Disable DNS rebinding protections so Cloudflare proxy Host headers pass through
        sec = TransportSecuritySettings(enable_dns_rebinding_protection=False)
        base_app = mcp.streamable_http_app(transport_security=sec)
        base_app.add_middleware(
            TunnelAuthMiddleware,
            auth_provider=self.auth_provider,
            permission_mode=self.mode,
        )

        config = uvicorn.Config(
            app=base_app,
            host=self.host,
            port=self.port,
            log_level="warning",
            access_log=False,
        )
        self._uvicorn_server = uvicorn.Server(config)

        def _runner():
            try:
                self._uvicorn_server.run()
            except Exception as e:
                logger.error("Uvicorn tunnel bridge exited with error: %s", e)

        self._uvicorn_thread = threading.Thread(target=_runner, name="mws-tunnel-bridge", daemon=True)
        self._uvicorn_thread.start()

        # Wait for listener to bind
        deadline = time.time() + 3.0
        while time.time() < deadline:
            if getattr(self._uvicorn_server, "started", False):
                break
            time.sleep(0.05)

        if not getattr(self._uvicorn_server, "started", False):
            raise RuntimeError(
                f"Failed to bind local tunnel bridge on {self.host}:{self.port} "
                "(port may already be in use by another application)."
            )

    def start_cloudflare_tunnel(self, timeout: float = 15.0) -> str:
        """
        Spawn cloudflared quick tunnel and parse the generated public trycloudflare.com URL.
        """
        if not self.is_cloudflared_installed():
            raise FileNotFoundError(
                "cloudflared binary not found in PATH. "
                "Please install Cloudflare Tunnel CLI from: https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/"
            )

        local_target = f"http://{self.host}:{self.port}"
        cmd = ["cloudflared", "tunnel", "--url", local_target]

        self._cf_proc = subprocess.Popen(
            cmd,
            stderr=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=True,
            bufsize=1,
            stdin=subprocess.DEVNULL,
        )

        discovered_url = None
        deadline = time.time() + timeout
        output_lines = []

        while time.time() < deadline:
            if self._cf_proc.poll() is not None:
                err_text = self._cf_proc.stderr.read() if self._cf_proc.stderr else ""
                raise RuntimeError(f"cloudflared process terminated unexpectedly: {err_text}")

            line = self._cf_proc.stderr.readline() if self._cf_proc.stderr else ""
            if line:
                output_lines.append(line.strip())
                m = re.search(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com", line)
                if m:
                    discovered_url = m.group(0)
                    break
            else:
                time.sleep(0.1)

        if not discovered_url:
            self.stop()
            recent_logs = "\n".join(output_lines[-8:])
            raise TimeoutError(
                f"cloudflared did not produce a trycloudflare.com URL within {timeout}s.\nRecent logs:\n{recent_logs}"
            )

        self._public_url = discovered_url
        if hasattr(self.auth_provider, "set_public_url"):
            self.auth_provider.set_public_url(discovered_url)
        return discovered_url

    def get_client_config(self) -> Dict[str, Any]:
        """Generate ready-to-paste client JSON configurations for ChatGPT, Gemini, Claude, Cursor."""
        return self.auth_provider.get_client_config(self._public_url or "")

    def stop(self) -> None:
        """Gracefully shut down Cloudflare tunnel, local uvicorn bridge, and auth provider."""
        self._stop_event.set()

        # Shutdown auth provider
        try:
            import asyncio
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(self.auth_provider.shutdown())
            except RuntimeError:
                asyncio.run(self.auth_provider.shutdown())
        except Exception:
            pass

        if self._cf_proc:
            try:
                self._cf_proc.terminate()
                self._cf_proc.wait(timeout=3)
            except Exception:
                try:
                    self._cf_proc.kill()
                except Exception:
                    pass
            self._cf_proc = None

        if self._uvicorn_server:
            try:
                self._uvicorn_server.should_exit = True
            except Exception:
                pass
            self._uvicorn_server = None

        if self._uvicorn_thread and self._uvicorn_thread.is_alive():
            self._uvicorn_thread.join(timeout=2)
            self._uvicorn_thread = None

    def wait(self) -> None:
        """Block until interrupted or stopped."""
        try:
            while not self._stop_event.is_set():
                time.sleep(0.5)
        except (KeyboardInterrupt, SystemExit):
            pass
        finally:
            self.stop()
