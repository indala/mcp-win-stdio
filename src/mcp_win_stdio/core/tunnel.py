"""
MWS Remote Tunnel Manager.
Exposes the local Streamable HTTP MCP endpoint to the public Internet via Cloudflare Tunnel (cloudflared),
ngrok, or direct HTTP/HTTPS binding, enabling ChatGPT, Gemini, Claude Web, and remote agent platforms
to access local mws tools securely.
"""

import collections
import json
import logging
import os
import queue
import re
import secrets
import shutil
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import urlsplit

import uvicorn
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from mcp_win_stdio.core.config import (
    CERTS_DIR,
    CURRENT_PERMISSION_MODE,
    get_tunnel_config,
    load_hierarchical_config,
)
from mcp_win_stdio.core.hub.secrets import redact_sensitive_data
from mcp_win_stdio.core.permissions import (
    CURRENT_ALLOW_SENSITIVE_READS,
    CURRENT_AUTH_MODE,
    CURRENT_SCOPE_FILTER,
    ToolScopeFilter,
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


def get_stored_direct_certs(certs_dir: Optional[Path] = None) -> Optional[Tuple[Path, Path]]:
    """Return (cert_path, key_path) from ~/.mcp-win-stdio/certs if both exist, else None."""
    base = certs_dir or CERTS_DIR
    cert_path = base / "direct_cert.pem"
    key_path = base / "direct_key.pem"
    if cert_path.is_file() and key_path.is_file():
        return cert_path, key_path
    return None


def import_direct_certs(cert_src: Path, key_src: Path, certs_dir: Optional[Path] = None) -> Tuple[Path, Path]:
    """Copy user-provided TLS cert and key into ~/.mcp-win-stdio/certs/."""
    cert_src = Path(cert_src).expanduser()
    key_src = Path(key_src).expanduser()
    if not cert_src.is_file():
        raise FileNotFoundError(f"Certificate file not found: {cert_src}")
    if not key_src.is_file():
        raise FileNotFoundError(f"Private key file not found: {key_src}")

    base = certs_dir or CERTS_DIR
    base.mkdir(parents=True, exist_ok=True)
    cert_dst = base / "direct_cert.pem"
    key_dst = base / "direct_key.pem"
    shutil.copy2(cert_src, cert_dst)
    shutil.copy2(key_src, key_dst)
    return cert_dst, key_dst


def generate_direct_self_signed_cert(
    host_or_ip: str,
    certs_dir: Optional[Path] = None,
    days: int = 90,
) -> Tuple[Path, Path]:
    """
    Generate a 90-day self-signed TLS certificate + key in ~/.mcp-win-stdio/certs/
    using OpenSSL CLI if available, falling back to Python cryptography.
    """
    import ipaddress

    target = (host_or_ip or "127.0.0.1").strip()
    base = certs_dir or CERTS_DIR
    base.mkdir(parents=True, exist_ok=True)
    cert_path = base / "direct_cert.pem"
    key_path = base / "direct_key.pem"

    is_ip = False
    try:
        ip_obj = ipaddress.ip_address(target)
        is_ip = True
    except ValueError:
        ip_obj = None

    if shutil.which("openssl"):
        san = f"IP:{target}" if is_ip else f"DNS:{target}"
        cmd = [
            "openssl", "req", "-x509",
            "-newkey", "rsa:2048",
            "-keyout", str(key_path),
            "-out", str(cert_path),
            "-days", str(days),
            "-nodes",
            "-subj", f"/CN={target}",
            "-addext", f"subjectAltName={san}",
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=15.0)
        if res.returncode == 0 and cert_path.is_file() and key_path.is_file():
            return cert_path, key_path

    # Fallback: pure-Python cryptography (works even when openssl CLI is not in PATH)
    from datetime import datetime, timedelta, timezone
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, target)])
    san_entry = x509.IPAddress(ip_obj) if is_ip and ip_obj is not None else x509.DNSName(target)
    now = datetime.now(timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=days))
        .add_extension(x509.SubjectAlternativeName([san_entry]), critical=False)
        .sign(key, hashes.SHA256())
    )
    key_path.write_bytes(
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    return cert_path, key_path


class TunnelAuthMiddleware(BaseHTTPMiddleware):
    """
    Generic authentication and permission isolation middleware delegating verification to an AuthProvider.
    Bypasses authentication strictly for health and status endpoints.
    Establishes request-scoped permission context (CURRENT_PERMISSION_MODE) for the lifetime of the request.
    """

    def __init__(
        self,
        app: Any,
        auth_provider: AuthProvider,
        permission_mode: str = "read_only",
        scope_filter: Optional[ToolScopeFilter] = None,
    ):
        super().__init__(app)
        self.auth_provider = auth_provider
        # Ensure middleware always has an initialized ToolScopeFilter (defaulting to clean pass-through if omitted)
        self.scope_filter = scope_filter if scope_filter is not None else ToolScopeFilter()
        self._start_time = time.time()
        if auth_provider.requires_read_only:
            self.permission_mode = "read_only"
        else:
            self.permission_mode = (permission_mode or "read_only").lower().strip()

    async def dispatch(self, request: Any, call_next: Callable[..., Any]) -> Any:
        from starlette.responses import Response

        # Handle CORS preflight requests for web-based AI clients (e.g. Gemini Custom Connected Apps)
        if request.method == "OPTIONS":
            req_headers = request.headers.get(
                "access-control-request-headers",
                "Authorization, Content-Type, Mcp-Session-Id, Last-Event-Id, Accept",
            )
            return Response(
                status_code=204,
                headers={
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Methods": "GET, POST, DELETE, OPTIONS, PUT",
                    "Access-Control-Allow-Headers": req_headers,
                    "Access-Control-Expose-Headers": "Mcp-Session-Id, WWW-Authenticate, Content-Type",
                    "Access-Control-Max-Age": "86400",
                },
            )

        path = request.url.path

        # Seamlessly map root path '/' to '/mcp' so clients connecting to either URL succeed
        if path == "/":
            request.scope["path"] = "/mcp"
            path = "/mcp"

        if path in ("/health", "/status"):
            uptime = time.time() - getattr(self, "_start_time", time.time())
            return JSONResponse({
                "status": "ok",
                "service": "mws-tunnel",
                "auth_mode": self.auth_provider.auth_mode,
                "permission_mode": self.permission_mode,
                "uptime_seconds": round(uptime, 2),
                "timestamp": time.time(),
            }, headers={
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "GET, POST, HEAD, OPTIONS",
                "Access-Control-Allow-Headers": "*",
                "Access-Control-Expose-Headers": "Mcp-Session-Id, WWW-Authenticate, Content-Type",
                "Cache-Control": "no-cache, no-store, must-revalidate",
            })

        # Intercept OAuth endpoints (discovery, registration, authorization, token, revocation)
        if hasattr(self.auth_provider, "is_oauth_path") and self.auth_provider.is_oauth_path(path):
            resp = await self.auth_provider.handle_oauth_request(request)
            if hasattr(resp, "headers"):
                resp.headers["Access-Control-Allow-Origin"] = "*"
                resp.headers["Access-Control-Expose-Headers"] = "Mcp-Session-Id, WWW-Authenticate, Content-Type"
            return resp

        auth_response = await self.auth_provider.authenticate(request)
        if auth_response is not None:
            if hasattr(auth_response, "headers"):
                auth_response.headers["Access-Control-Allow-Origin"] = "*"
                auth_response.headers["Access-Control-Expose-Headers"] = "Mcp-Session-Id, WWW-Authenticate, Content-Type"
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

        # Clone request-scoped filter instance and bound its lifecycle strictly to this request
        request_scope = self.scope_filter.clone()
        scope_token = CURRENT_SCOPE_FILTER.set(request_scope)
        try:
            response = await call_next(request)
            # Attach cleanup to response.background so SSE streaming bodies complete BEFORE revocation
            from starlette.background import BackgroundTask
            from starlette.responses import Response

            if isinstance(response, Response):
                response.headers["Access-Control-Allow-Origin"] = "*"
                response.headers["Access-Control-Expose-Headers"] = "Mcp-Session-Id, WWW-Authenticate, Content-Type"
                # Prevent reverse proxy buffering on StreamableHTTP / SSE
                response.headers["X-Accel-Buffering"] = "no"
                orig_bg = getattr(response, "background", None)

                def _on_request_cleanup():
                    request_scope.revoke()
                    if orig_bg:
                        orig_bg()

                response.background = BackgroundTask(_on_request_cleanup)
            else:
                # If non-Response object (e.g. mock test handler), revoke immediately
                request_scope.revoke()
            return response
        finally:
            CURRENT_SCOPE_FILTER.reset(scope_token)
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
    Orchestrates the local uvicorn StreamableHTTP server, auth provider, and remote tunnel (cloudflared, ngrok, or direct).
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
        scope_filter: Optional[ToolScopeFilter] = None,
        provider: str = "cloudflare",
        domain: Optional[str] = None,
        public_url: Optional[str] = None,
        ssl_certfile: Optional[str] = None,
        ssl_keyfile: Optional[str] = None,
    ):
        self.port = port
        self.mode = mode.lower().strip()
        self.auth_mode = (auth_mode or "bearer").lower().strip()
        self.host = host
        self.workspace_dir = workspace_dir
        self.allow_sensitive_reads = bool(allow_sensitive_reads)
        self.provider = (provider or "cloudflare").lower().strip()
        self.domain = domain.strip() if isinstance(domain, str) and domain.strip() else None
        self.configured_public_url = public_url.rstrip("/") if isinstance(public_url, str) and public_url.strip() else None
        self.ssl_certfile = ssl_certfile.strip() if isinstance(ssl_certfile, str) and ssl_certfile.strip() else None
        self.ssl_keyfile = ssl_keyfile.strip() if isinstance(ssl_keyfile, str) and ssl_keyfile.strip() else None
        if bool(self.ssl_certfile) != bool(self.ssl_keyfile):
            raise ValueError("Both ssl_certfile and ssl_keyfile must be provided together.")
        if self.ssl_certfile and not Path(self.ssl_certfile).is_file():
            raise FileNotFoundError(f"SSL certificate file not found: {self.ssl_certfile}")
        if self.ssl_keyfile and not Path(self.ssl_keyfile).is_file():
            raise FileNotFoundError(f"SSL key file not found: {self.ssl_keyfile}")
        # Ensure tunnel bridge always holds an explicit ToolScopeFilter instance (never uninitialized None)
        self.scope_filter = scope_filter if scope_filter is not None else ToolScopeFilter()

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
        self._proc_stdout_buffer: collections.deque[str] = collections.deque(maxlen=200)
        self._proc_stderr_buffer: collections.deque[str] = collections.deque(maxlen=200)
        self._proc_log_lock = threading.Lock()
        self._stdout_thread: Optional[threading.Thread] = None
        self._stderr_thread: Optional[threading.Thread] = None

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

    @staticmethod
    def is_ngrok_installed() -> bool:
        """Check if ngrok binary is discoverable in PATH."""
        return shutil.which("ngrok") is not None

    @staticmethod
    def has_ngrok_authtoken() -> bool:
        """Check if ngrok has an authtoken configured in env or ngrok.yml."""
        if os.environ.get("NGROK_AUTHTOKEN"):
            return True

        candidate_paths = []
        if sys.platform == "win32":
            local_app = os.environ.get("LOCALAPPDATA")
            if local_app:
                candidate_paths.append(Path(local_app) / "ngrok" / "ngrok.yml")
        elif sys.platform == "darwin":
            candidate_paths.append(Path.home() / "Library" / "Application Support" / "ngrok" / "ngrok.yml")
        else:
            xdg = os.environ.get("XDG_CONFIG_HOME")
            if xdg:
                candidate_paths.append(Path(xdg) / "ngrok" / "ngrok.yml")
            candidate_paths.append(Path.home() / ".config" / "ngrok" / "ngrok.yml")
        candidate_paths.append(Path.home() / ".ngrok2" / "ngrok.yml")

        for cfg_path in candidate_paths:
            if cfg_path.is_file():
                try:
                    content = cfg_path.read_text(encoding="utf-8", errors="ignore")
                    if re.search(r"^\s*authtoken\s*:\s*\S+", content, re.MULTILINE):
                        return True
                except OSError:
                    pass
        return False

    @staticmethod
    def configure_ngrok_authtoken(token: str) -> bool:
        """Persist ngrok authtoken using 'ngrok config add-authtoken'."""
        cleaned = (token or "").strip()
        if not cleaned or not MwsTunnelManager.is_ngrok_installed():
            return False
        try:
            res = subprocess.run(
                ["ngrok", "config", "add-authtoken", cleaned],
                capture_output=True,
                text=True,
                timeout=10.0,
            )
            return res.returncode == 0
        except Exception:
            return False

    @staticmethod
    def get_ngrok_version() -> Optional[str]:
        """Return the installed ngrok version string, or None if not found."""
        if not MwsTunnelManager.is_ngrok_installed():
            return None
        try:
            res = subprocess.run(
                ["ngrok", "version"],
                capture_output=True,
                text=True,
                timeout=3.0,
            )
            if res.returncode == 0:
                first_line = res.stdout.strip().split("\n")[0]
                return first_line.replace("ngrok version ", "v").strip()
        except Exception:
            pass
        return "Installed"

    @staticmethod
    def try_install_ngrok() -> bool:
        """Attempt to install ngrok using system package manager (winget on Windows, brew on macOS)."""
        if sys.platform == "win32":
            if shutil.which("winget"):
                try:
                    res = subprocess.run(
                        [
                            "winget",
                            "install",
                            "--id",
                            "Ngrok.Ngrok",
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
                    res = subprocess.run(["brew", "install", "ngrok/ngrok/ngrok"], timeout=180.0)
                    return res.returncode == 0
                except Exception:
                    return False
        return False

    def _redact_and_buffer_line(self, stream_name: str, line: str) -> str:
        """Redact sensitive tokens from provider log output and append to a bounded ring buffer."""
        try:
            safe_line = redact_sensitive_data(line)
        except Exception:
            safe_line = "[log redaction failed]\n"
        if len(safe_line) > 4096:
            safe_line = safe_line[-4096:]
        with self._proc_log_lock:
            buf = self._proc_stdout_buffer if stream_name == "stdout" else self._proc_stderr_buffer
            buf.append(safe_line)
        return safe_line

    def _start_provider_drainers(
        self,
        proc: Any,
        line_queue: Optional["queue.Queue[Tuple[str, str]]"] = None,
        stop_queue_event: Optional[threading.Event] = None,
    ) -> None:
        """
        Continuously drain both stdout and stderr pipes on background daemon threads
        so provider logging never fills an OS pipe buffer and stalls the child process.
        """
        with self._proc_log_lock:
            self._proc_stdout_buffer.clear()
            self._proc_stderr_buffer.clear()

        def _drain_stream(stream: Any, stream_name: str) -> None:
            if not stream:
                return
            try:
                while not self._stop_event.is_set():
                    try:
                        try:
                            chunk = stream.readline(65536)
                        except TypeError:
                            chunk = stream.readline()
                    except (ValueError, OSError, StopIteration):
                        break

                    if not chunk:
                        break
                    # Guard against unconfigured MagicMock streams returning MagicMock objects
                    if not isinstance(chunk, (str, bytes)):
                        break
                    if isinstance(chunk, bytes):
                        chunk = chunk.decode("utf-8", errors="replace")

                    safe_line = self._redact_and_buffer_line(stream_name, chunk)
                    if line_queue is not None and not (stop_queue_event and stop_queue_event.is_set()):
                        try:
                            line_queue.put_nowait((stream_name, safe_line))
                        except queue.Full:
                            pass
                        except Exception:
                            pass
            except Exception:
                pass

        self._stdout_thread = threading.Thread(
            target=_drain_stream,
            args=(getattr(proc, "stdout", None), "stdout"),
            name=f"mws-tunnel-{self.provider}-stdout",
            daemon=True,
        )
        self._stderr_thread = threading.Thread(
            target=_drain_stream,
            args=(getattr(proc, "stderr", None), "stderr"),
            name=f"mws-tunnel-{self.provider}-stderr",
            daemon=True,
        )
        self._stdout_thread.start()
        self._stderr_thread.start()

    def _collect_provider_logs(self, proc: Any) -> str:
        """Collect buffered/remaining stdout & stderr logs safely when a provider exits or times out."""
        with self._proc_log_lock:
            lines = [l.strip() for l in list(self._proc_stdout_buffer) + list(self._proc_stderr_buffer) if l.strip()]

        if not lines:
            for stream in (getattr(proc, "stderr", None), getattr(proc, "stdout", None)):
                if stream:
                    try:
                        rem = stream.read()
                        if isinstance(rem, bytes):
                            rem = rem.decode("utf-8", errors="replace")
                        if isinstance(rem, str) and rem.strip():
                            try:
                                safe_rem = redact_sensitive_data(rem)
                            except Exception:
                                safe_rem = "[log redaction failed]"
                            lines.extend(safe_rem.strip().splitlines())
                    except Exception:
                        pass
        return "\n".join(lines[-50:]).strip()

    def start_local_bridge(self) -> None:
        """Launch uvicorn StreamableHTTP server with configured auth provider in a worker thread."""
        from mcp.server.transport_security import TransportSecuritySettings

        if self.provider == "direct":
            allowed_hosts: List[str] = ["localhost:*", "127.0.0.1:*", "[::1]:*"]
            if self.configured_public_url:
                parsed = urlsplit(self.configured_public_url)
                if parsed.hostname:
                    allowed_hosts.extend([parsed.hostname, f"{parsed.hostname}:*"])
                if parsed.netloc and parsed.netloc not in allowed_hosts:
                    allowed_hosts.append(parsed.netloc)
            if self.host and self.host not in ("0.0.0.0", "::", ""):
                allowed_hosts.extend([self.host, f"{self.host}:*"])
            else:
                detected_ip = self._detect_local_ip()
                if detected_ip:
                    allowed_hosts.extend([detected_ip, f"{detected_ip}:*"])
            sec = TransportSecuritySettings(
                enable_dns_rebinding_protection=True,
                allowed_hosts=list(dict.fromkeys(allowed_hosts)),
            )
        else:
            # Disable DNS rebinding protections for reverse-proxy providers (Cloudflare / ngrok)
            # whose edge proxies rewrite incoming Host headers.
            sec = TransportSecuritySettings(enable_dns_rebinding_protection=False)
        base_app = mcp.streamable_http_app(transport_security=sec)
        base_app.add_middleware(
            TunnelAuthMiddleware,
            auth_provider=self.auth_provider,
            permission_mode=self.mode,
            scope_filter=self.scope_filter,
        )

        config_kwargs: Dict[str, Any] = {
            "app": base_app,
            "host": self.host,
            "port": self.port,
            "log_level": "warning",
            "access_log": False,
        }
        if self.ssl_certfile and self.ssl_keyfile:
            config_kwargs["ssl_certfile"] = self.ssl_certfile
            config_kwargs["ssl_keyfile"] = self.ssl_keyfile

        config = uvicorn.Config(**config_kwargs)
        self._uvicorn_server = uvicorn.Server(config)

        def _runner():
            try:
                self._uvicorn_server.run()
            except Exception as e:
                logger.error("Uvicorn tunnel bridge exited with error: %s", e)

        self._uvicorn_thread = threading.Thread(target=_runner, name="mws-tunnel-bridge", daemon=True)
        self._uvicorn_thread.start()

        try:
            from mcp_win_stdio.server.process_pool import GLOBAL_POOL

            GLOBAL_POOL.start_background_reaper()
        except Exception:
            pass

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
        output_lines: List[str] = []

        if self._cf_proc.poll() is not None:
            full_log = self._collect_provider_logs(self._cf_proc)
            hint = ""
            if any(k in full_log.lower() for k in ("wsarecv", "connection was forcibly closed", "connection reset", "handshake")):
                hint = (
                    "\n\n💡 DIAGNOSIS: Connection to Cloudflare's quick tunnel service (api.trycloudflare.com) was reset.\n"
                    "   This occurs when an ISP or local firewall restricts *.trycloudflare.com via SNI inspection.\n"
                    "   Suggested remedies:\n"
                    "     • Enable a VPN or switch to an alternate internet connection (e.g. mobile hotspot).\n"
                    "     • Or run local MCP without a remote tunnel using: 'mws server'"
                )
            raise RuntimeError(
                f"cloudflared process terminated unexpectedly (exit code {self._cf_proc.poll()}):\n{full_log}{hint}"
            )

        line_queue: "queue.Queue[Tuple[str, str]]" = queue.Queue(maxsize=256)
        stop_queue_event = threading.Event()
        self._start_provider_drainers(self._cf_proc, line_queue=line_queue, stop_queue_event=stop_queue_event)

        try:
            while time.time() < deadline:
                try:
                    _, line = line_queue.get(timeout=0.05)
                    output_lines.append(line.strip())
                    m = re.search(r"https://([a-zA-Z0-9-]+)\.trycloudflare\.com", line)
                    if m:
                        subdomain = m.group(1).lower()
                        if subdomain != "api":
                            discovered_url = m.group(0)
                            break
                except queue.Empty:
                    if self._cf_proc.poll() is not None:
                        if self._stdout_thread:
                            self._stdout_thread.join(timeout=0.3)
                        if self._stderr_thread:
                            self._stderr_thread.join(timeout=0.3)
                        while not line_queue.empty():
                            _, rem_line = line_queue.get_nowait()
                            output_lines.append(rem_line.strip())
                        full_log = "\n".join(output_lines).strip() or self._collect_provider_logs(self._cf_proc)

                        hint = ""
                        if any(k in full_log.lower() for k in ("wsarecv", "connection was forcibly closed", "connection reset", "handshake")):
                            hint = (
                                "\n\n💡 DIAGNOSIS: Connection to Cloudflare's quick tunnel service (api.trycloudflare.com) was reset.\n"
                                "   This occurs when an ISP or local firewall restricts *.trycloudflare.com via SNI inspection.\n"
                                "   Suggested remedies:\n"
                                "     • Enable a VPN or switch to an alternate internet connection (e.g. mobile hotspot).\n"
                                "     • Or run local MCP without a remote tunnel using: 'mws server'"
                            )
                        raise RuntimeError(
                            f"cloudflared process terminated unexpectedly (exit code {self._cf_proc.poll()}):\n{full_log}{hint}"
                        )
        finally:
            stop_queue_event.set()

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

    def start_ngrok_tunnel(self, timeout: float = 15.0) -> str:
        """
        Spawn ngrok HTTP tunnel and parse the generated public HTTPS URL from JSON logs.
        """
        if not self.is_ngrok_installed():
            raise FileNotFoundError(
                "ngrok binary not found in PATH. "
                "Please install ngrok CLI from: https://ngrok.com/download"
            )

        local_target = f"{self.host}:{self.port}"
        cmd = ["ngrok", "http", local_target, "--log", "stdout", "--log-format", "json"]
        if self.domain:
            cmd.extend(["--domain", self.domain])

        self._cf_proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            stdin=subprocess.DEVNULL,
        )

        discovered_url = None
        deadline = time.time() + timeout
        output_lines: List[str] = []

        if self._cf_proc.poll() is not None:
            full_log = self._collect_provider_logs(self._cf_proc)
            hint = ""
            low_log = full_log.lower()
            if "err_ngrok_4018" in low_log or "authtoken" in low_log:
                hint = (
                    "\n\n💡 DIAGNOSIS: ngrok requires a free authtoken to start tunnels.\n"
                    "   1. Sign up / log in at https://dashboard.ngrok.com/get-started/your-authtoken\n"
                    "   2. Run: ngrok config add-authtoken <YOUR_TOKEN>\n"
                    "   3. Re-run: mws tunnel --type ngrok"
                )
            elif any(k in low_log for k in ("connection reset", "dial tcp", "eof", "timeout")):
                hint = (
                    "\n\n💡 DIAGNOSIS: ngrok could not connect to the ngrok edge network.\n"
                    "   Check your internet connection, proxy settings, or firewall rules."
                )
            raise RuntimeError(
                f"ngrok process terminated unexpectedly (exit code {self._cf_proc.poll()}):\n{full_log}{hint}"
            )

        line_queue: "queue.Queue[Tuple[str, str]]" = queue.Queue(maxsize=256)
        stop_queue_event = threading.Event()
        self._start_provider_drainers(self._cf_proc, line_queue=line_queue, stop_queue_event=stop_queue_event)

        try:
            while time.time() < deadline:
                try:
                    _, line = line_queue.get(timeout=0.05)
                    stripped = line.strip()
                    output_lines.append(stripped)
                    try:
                        data = json.loads(stripped)
                        url_val = data.get("url")
                        if isinstance(url_val, str) and url_val.startswith("https://"):
                            discovered_url = url_val.rstrip("/")
                            break
                    except (ValueError, TypeError):
                        m = re.search(r"https://[a-zA-Z0-9.-]+\.ngrok[-a-zA-Z0-9.]*", stripped)
                        if m:
                            discovered_url = m.group(0).rstrip("/")
                            break
                except queue.Empty:
                    if self._cf_proc.poll() is not None:
                        if self._stdout_thread:
                            self._stdout_thread.join(timeout=0.3)
                        if self._stderr_thread:
                            self._stderr_thread.join(timeout=0.3)
                        while not line_queue.empty():
                            _, rem_line = line_queue.get_nowait()
                            output_lines.append(rem_line.strip())
                        full_log = "\n".join(output_lines).strip() or self._collect_provider_logs(self._cf_proc)

                        hint = ""
                        low_log = full_log.lower()
                        if "err_ngrok_4018" in low_log or "authtoken" in low_log:
                            hint = (
                                "\n\n💡 DIAGNOSIS: ngrok requires a free authtoken to start tunnels.\n"
                                "   1. Sign up / log in at https://dashboard.ngrok.com/get-started/your-authtoken\n"
                                "   2. Run: ngrok config add-authtoken <YOUR_TOKEN>\n"
                                "   3. Re-run: mws tunnel --type ngrok"
                            )
                        elif any(k in low_log for k in ("connection reset", "dial tcp", "eof", "timeout")):
                            hint = (
                                "\n\n💡 DIAGNOSIS: ngrok could not connect to the ngrok edge network.\n"
                                "   Check your internet connection, proxy settings, or firewall rules."
                            )
                        raise RuntimeError(
                            f"ngrok process terminated unexpectedly (exit code {self._cf_proc.poll()}):\n{full_log}{hint}"
                        )
        finally:
            stop_queue_event.set()

        if not discovered_url:
            self.stop()
            recent_logs = "\n".join(output_lines[-8:])
            raise TimeoutError(
                f"ngrok did not produce a public HTTPS URL within {timeout}s.\nRecent logs:\n{recent_logs}"
            )

        self._public_url = discovered_url
        if hasattr(self.auth_provider, "set_public_url"):
            self.auth_provider.set_public_url(discovered_url)
        return discovered_url

    @staticmethod
    def _detect_local_ip() -> str:
        """Best-effort detection of the host's primary LAN IPv4 address."""
        import socket

        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.connect(("8.8.8.8", 80))
                ip = s.getsockname()[0]
                if ip and not ip.startswith("127."):
                    return ip
        except Exception:
            pass
        return "127.0.0.1"

    def start_direct_tunnel(self, public_url: Optional[str] = None) -> str:
        """
        Configure direct HTTP/HTTPS exposure without a third-party tunnel binary.
        """
        explicit = (public_url or self.configured_public_url or "").strip().rstrip("/")
        if explicit:
            resolved_url = explicit
        else:
            scheme = "https" if (self.ssl_certfile and self.ssl_keyfile) else "http"
            effective_host = self._detect_local_ip() if self.host in ("0.0.0.0", "::", "") else self.host
            resolved_url = f"{scheme}://{effective_host}:{self.port}"

        self._public_url = resolved_url
        if hasattr(self.auth_provider, "set_public_url"):
            self.auth_provider.set_public_url(resolved_url)
        return resolved_url

    def start_tunnel(self, timeout: float = 15.0) -> str:
        """Start the configured tunnel provider (cloudflare, ngrok, or direct)."""
        if self.provider == "ngrok":
            return self.start_ngrok_tunnel(timeout=timeout)
        if self.provider == "direct":
            return self.start_direct_tunnel()
        return self.start_cloudflare_tunnel(timeout=timeout)

    def get_client_config(self) -> Dict[str, Any]:
        """Generate ready-to-paste client JSON configurations for ChatGPT, Gemini, Claude, Cursor."""
        return self.auth_provider.get_client_config(self._public_url or "")

    def stop(self) -> None:
        """Gracefully shut down Cloudflare tunnel, local uvicorn bridge, and auth provider."""
        self._stop_event.set()

        try:
            from mcp_win_stdio.server.process_pool import GLOBAL_POOL

            GLOBAL_POOL.stop_background_reaper()
        except Exception:
            pass

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
            proc = self._cf_proc
            try:
                proc.terminate()
                proc.wait(timeout=3)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
            for pipe in (getattr(proc, "stdin", None), getattr(proc, "stdout", None), getattr(proc, "stderr", None)):
                if pipe and not getattr(pipe, "closed", True):
                    try:
                        pipe.close()
                    except Exception:
                        pass
            self._cf_proc = None

        for t_attr in ("_stdout_thread", "_stderr_thread"):
            t = getattr(self, t_attr, None)
            if t and t.is_alive() and threading.current_thread() is not t:
                t.join(timeout=1.0)
            setattr(self, t_attr, None)

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
        """Block until interrupted or stopped, actively monitoring tunnel health and auto-reconnecting if dropped."""
        provider_label = "ngrok" if self.provider == "ngrok" else "Cloudflare"
        try:
            while not self._stop_event.is_set():
                if self._cf_proc is not None and self._cf_proc.poll() is not None:
                    code = self._cf_proc.poll()
                    if not self._stop_event.is_set():
                        logger.warning(
                            "%s tunnel process terminated unexpectedly (exit code %s). "
                            "Local StreamableHTTP bridge remains active on %s:%s.",
                            provider_label, code, self.host, self.port,
                        )
                        # Attempt automatic tunnel recovery
                        try:
                            logger.info("Attempting automatic %s tunnel reconnection...", provider_label)
                            new_url = self.start_tunnel(timeout=10.0)
                            logger.info("Tunnel reconnected successfully at: %s", new_url)
                            print(f"\n🔄 {provider_label} tunnel automatically reconnected: {new_url}")
                        except Exception as rec_err:
                            logger.error("Tunnel auto-reconnection failed: %s", rec_err)
                            print(f"\n⚠️  {provider_label} tunnel dropped (code {code}). Reconnection attempt failed: {rec_err}")
                            break
                time.sleep(0.5)
        except (KeyboardInterrupt, SystemExit):
            pass
        finally:
            self.stop()
