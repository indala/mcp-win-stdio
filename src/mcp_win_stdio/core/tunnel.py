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

from mcp_win_stdio.core.config import get_tunnel_config, load_hierarchical_config
from mcp_win_stdio.server.catalog import get_server_catalog
from mcp_win_stdio.server.discovery import discover_available_servers
from mcp_win_stdio.server.server import mcp

logger = logging.getLogger("mcp_win_stdio.tunnel")


class BearerAuthMiddleware(BaseHTTPMiddleware):
    """
    Mandatory Bearer token authentication middleware for the public MCP tunnel.
    Permits unauthenticated access strictly to /health and /status endpoints.
    """

    def __init__(self, app: Any, token: str):
        super().__init__(app)
        self.token = token.strip()

    async def dispatch(self, request: Any, call_next: Callable[..., Any]) -> Any:
        path = request.url.path
        if path in ("/health", "/status"):
            return JSONResponse({
                "status": "ok",
                "service": "mws-tunnel",
                "timestamp": time.time(),
            })

        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return JSONResponse(
                {
                    "error": "Unauthorized",
                    "message": "Missing or malformed Authorization header. Expected 'Bearer <token>'.",
                },
                status_code=401,
            )

        received_token = auth_header[7:].strip()
        if not secrets.compare_digest(received_token, self.token):
            return JSONResponse(
                {
                    "error": "Unauthorized",
                    "message": "Invalid Bearer token.",
                },
                status_code=401,
            )

        return await call_next(request)


class MwsTunnelManager:
    """
    Orchestrates the local uvicorn StreamableHTTP server and the cloudflared quick tunnel.
    """

    def __init__(
        self,
        port: int = 8080,
        mode: str = "read_only",
        token: Optional[str] = None,
        host: str = "127.0.0.1",
        workspace_dir: Optional[Path] = None,
    ):
        self.port = port
        self.mode = mode.lower().strip()
        self.host = host
        self.workspace_dir = workspace_dir
        self.token = token or secrets.token_urlsafe(24)

        self._uvicorn_server: Optional[uvicorn.Server] = None
        self._uvicorn_thread: Optional[threading.Thread] = None
        self._cf_proc: Optional[subprocess.Popen] = None
        self._public_url: Optional[str] = None
        self._stop_event = threading.Event()

    @staticmethod
    def is_cloudflared_installed() -> bool:
        """Check if cloudflared binary is discoverable in PATH."""
        return shutil.which("cloudflared") is not None

    def start_local_bridge(self) -> None:
        """Launch uvicorn StreamableHTTP server with Bearer auth in a worker thread."""
        from mcp.server.transport_security import TransportSecuritySettings

        # Disable DNS rebinding protections so Cloudflare proxy Host headers pass through
        sec = TransportSecuritySettings(enable_dns_rebinding_protection=False)
        base_app = mcp.streamable_http_app(transport_security=sec)
        base_app.add_middleware(BearerAuthMiddleware, token=self.token)

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
        return discovered_url

    def get_client_config(self) -> Dict[str, Any]:
        """Generate ready-to-paste client JSON configurations for ChatGPT, Gemini, Claude, Cursor."""
        mcp_endpoint = f"{self._public_url}/mcp" if self._public_url else ""
        return {
            "mcpServers": {
                "mws": {
                    "url": mcp_endpoint,
                    "headers": {
                        "Authorization": f"Bearer {self.token}",
                    },
                }
            }
        }

    def stop(self) -> None:
        """Gracefully shut down Cloudflare tunnel and local uvicorn bridge."""
        self._stop_event.set()

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
