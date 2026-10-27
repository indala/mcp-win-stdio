"""
Local IPC Control Plane and Instance Ownership Manager for MCP Hub.
Provides authenticated local IPC over Windows Named Pipes (multiprocessing.connection AF_PIPE)
with per-instance secret tokens, stale PID verification, and cross-process stop/status requests.
"""

import json
import logging
import os
import secrets
import sys
import threading
import time
from dataclasses import dataclass
from multiprocessing.connection import Client, Listener
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Tuple, Union

from mcp_win_stdio.core.config import USER_DIR
from mcp_win_stdio.core.hub.orchestrator import HubOrchestrator
from mcp_win_stdio.core.hub.secrets import redact_sensitive_data

logger = logging.getLogger(__name__)


def is_pid_alive(pid: int) -> bool:
    """Check if a process with given PID is currently active in the OS kernel."""
    if pid <= 0:
        return False
    if sys.platform == "win32":
        try:
            import ctypes
            from ctypes import wintypes

            k32 = ctypes.windll.kernel32
            h = k32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
            if not h:
                return False
            exit_code = wintypes.DWORD()
            k32.GetExitCodeProcess(h, ctypes.byref(exit_code))
            k32.CloseHandle(h)
            return exit_code.value == 259  # STILL_ACTIVE
        except Exception:
            return False
    else:
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False


def get_default_pipe_name() -> str:
    """Generate default named pipe path for current user."""
    username = os.environ.get("USERNAME", os.environ.get("USER", "default")).lower().strip()
    safe_user = "".join(c if c.isalnum() else "_" for c in username)
    if sys.platform == "win32":
        return f"\\\\.\\pipe\\mws-control-{safe_user}"
    else:
        return str(USER_DIR / f"mws_control_{safe_user}.sock")


def get_ipc_family(endpoint: str) -> str:
    """Return appropriate IPC family for current platform and endpoint."""
    if sys.platform == "win32" and endpoint.startswith("\\\\.\\pipe\\"):
        return "AF_PIPE"
    return "AF_UNIX"


@dataclass(frozen=True)
class HubInstanceMetadata:
    """Metadata representing an active running MCP Hub instance."""

    pid: int
    started_at: float
    pipe_name: str
    authkey_hex: str
    config_path: Optional[str]
    config_source: str
    http_host: str
    http_port: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "pid": self.pid,
            "started_at": self.started_at,
            "pipe_name": self.pipe_name,
            "authkey_hex": self.authkey_hex,
            "config_path": self.config_path,
            "config_source": self.config_source,
            "http_host": self.http_host,
            "http_port": self.http_port,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "HubInstanceMetadata":
        return cls(
            pid=int(data["pid"]),
            started_at=float(data["started_at"]),
            pipe_name=str(data["pipe_name"]),
            authkey_hex=str(data["authkey_hex"]),
            config_path=data.get("config_path"),
            config_source=str(data.get("config_source", "unknown")),
            http_host=str(data.get("http_host", "127.0.0.1")),
            http_port=int(data.get("http_port", 8080)),
        )


class HubControlClient:
    """Client for cross-process control IPC with a running Hub instance."""

    @staticmethod
    def ping(pipe_name: str, authkey_hex: str, timeout: float = 2.0) -> Optional[int]:
        """Ping hub instance. Returns running PID on success, None on failure."""
        family = get_ipc_family(pipe_name)
        try:
            auth_bytes = bytes.fromhex(authkey_hex)
            with Client(pipe_name, family=family, authkey=auth_bytes) as conn:
                conn.send({"cmd": "ping"})
                resp = conn.recv()
                if isinstance(resp, dict) and resp.get("status") == "ok":
                    return resp.get("pid")
        except Exception:
            pass
        return None

    @staticmethod
    def get_status(pipe_name: str, authkey_hex: str, timeout: float = 5.0) -> Optional[Dict[str, Any]]:
        """Request aggregate status dictionary from running hub instance."""
        family = get_ipc_family(pipe_name)
        try:
            auth_bytes = bytes.fromhex(authkey_hex)
            with Client(pipe_name, family=family, authkey=auth_bytes) as conn:
                conn.send({"cmd": "status"})
                resp = conn.recv()
                if isinstance(resp, dict) and resp.get("status") == "ok":
                    return resp.get("data")
        except Exception as e:
            logger.debug("Failed retrieving status via control IPC: %s", e)
        return None

    @staticmethod
    def request_stop(pipe_name: str, authkey_hex: str, timeout: float = 10.0) -> bool:
        """Send graceful stop request to running hub instance."""
        family = get_ipc_family(pipe_name)
        try:
            auth_bytes = bytes.fromhex(authkey_hex)
            with Client(pipe_name, family=family, authkey=auth_bytes) as conn:
                conn.send({"cmd": "stop", "timeout": timeout})
                resp = conn.recv()
                return bool(isinstance(resp, dict) and resp.get("status") == "stopping")
        except Exception as e:
            logger.debug("Failed sending stop via control IPC: %s", e)
            return False


class HubInstanceManager:
    """Manages active instance ownership metadata (~/.mcp-win-stdio/hub_instance.json)."""

    def __init__(self, metadata_path: Optional[Path] = None):
        self.metadata_path = metadata_path or (USER_DIR / "hub_instance.json")
        self._lock = threading.RLock()

    def get_metadata(self) -> Optional[HubInstanceMetadata]:
        """Read existing metadata if present and valid."""
        if not self.metadata_path.is_file():
            return None
        try:
            with open(self.metadata_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return HubInstanceMetadata.from_dict(data)
        except Exception:
            return None

    def is_running(self) -> Tuple[bool, Optional[HubInstanceMetadata]]:
        """
        Verify if the hub instance is genuinely running:
          1. Reads metadata file.
          2. Checks if PID is active in OS.
          3. Pings control pipe with authkey to guarantee process identity (no PID reuse).
          4. Cleans up stale metadata automatically if dead.
        """
        with self._lock:
            meta = self.get_metadata()
            if not meta:
                return False, None

            # 1. OS-level PID check: if process is dead in kernel, purge immediately
            if not is_pid_alive(meta.pid):
                logger.info("Found stale hub metadata for dead PID %d; purging.", meta.pid)
                self.release()
                return False, None

            # 2. Control IPC ping verification to confirm process identity
            active_pid = HubControlClient.ping(meta.pipe_name, meta.authkey_hex, timeout=1.0)
            if active_pid == meta.pid:
                return True, meta

            # If PID is alive in OS but ping did not respond, allow startup grace period
            # before treating the metadata as an unrelated reused PID
            age = time.time() - meta.started_at
            if age > 15.0:
                logger.info("PID %d did not respond to control ping after %.1fs; cleaning up stale instance.", meta.pid, age)
                self.release()
                return False, None

            # Process is alive in OS kernel but IPC handshake is not yet ready (starting up)
            return False, meta

    def acquire(
        self,
        pid: int,
        pipe_name: str,
        config_path: Optional[str] = None,
        config_source: str = "default",
        http_host: str = "127.0.0.1",
        http_port: int = 8080,
    ) -> HubInstanceMetadata:
        """
        Register active instance ownership. Fails if another instance is running.
        Generates per-instance cryptographic authkey for IPC security.
        """
        with self._lock:
            running, existing = self.is_running()
            if running and existing:
                raise RuntimeError(
                    f"MCP Hub is already running (PID {existing.pid}) on {existing.http_host}:{existing.http_port}."
                )

            authkey_hex = secrets.token_hex(16)
            meta = HubInstanceMetadata(
                pid=pid,
                started_at=time.time(),
                pipe_name=pipe_name,
                authkey_hex=authkey_hex,
                config_path=config_path,
                config_source=config_source,
                http_host=http_host,
                http_port=http_port,
            )

            self.metadata_path.parent.mkdir(parents=True, exist_ok=True)
            # Atomic file write via temp file
            tmp_path = self.metadata_path.with_suffix(".tmp")
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(meta.to_dict(), f, indent=2)
            tmp_path.replace(self.metadata_path)

            return meta

    def release(self) -> None:
        """Clean up instance metadata file."""
        with self._lock:
            try:
                self.metadata_path.unlink(missing_ok=True)
            except Exception as e:
                logger.warning("Error releasing hub instance metadata: %s", e)


class HubControlServer:
    """
    Authenticated local control server listening on a named pipe or Unix socket.
    Responds to status, ping, and stop requests from CLI commands.
    """

    def __init__(
        self,
        orchestrator: HubOrchestrator,
        pipe_name: str,
        authkey_hex: str,
        on_stop_requested: Optional[Callable[[], None]] = None,
    ):
        self.orchestrator = orchestrator
        self.pipe_name = pipe_name
        self.authkey_hex = authkey_hex
        self.on_stop_requested = on_stop_requested

        self._listener: Optional[Listener] = None
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    def start(self) -> None:
        """Initialize listener and start server background thread."""
        family = get_ipc_family(self.pipe_name)
        auth_bytes = bytes.fromhex(self.authkey_hex)

        try:
            self._listener = Listener(self.pipe_name, family=family, authkey=auth_bytes)
        except Exception as e:
            raise RuntimeError(f"Failed opening control IPC pipe '{self.pipe_name}': {e}") from e

        self._thread = threading.Thread(
            target=self._serve_loop,
            name="mws-hub-control-server",
            daemon=True,
        )
        self._thread.start()

    def _serve_loop(self) -> None:
        """Listen and handle incoming authenticated client requests."""
        while not self._stop_event.is_set():
            conn = None
            try:
                if not self._listener:
                    break
                conn = self._listener.accept()
                req = conn.recv()
                if not isinstance(req, dict):
                    continue

                cmd = req.get("cmd")
                if cmd == "ping":
                    conn.send({"status": "ok", "pid": os.getpid()})
                elif cmd == "status":
                    status_dict = self.orchestrator.status().to_dict()
                    conn.send({"status": "ok", "data": status_dict})
                elif cmd == "stop":
                    conn.send({"status": "stopping"})
                    conn.close()
                    conn = None
                    # Schedule shutdown asynchronously so response is delivered cleanly
                    if self.on_stop_requested:
                        threading.Thread(target=self.on_stop_requested, daemon=True).start()
                    else:
                        timeout = req.get("timeout", 10.0)
                        threading.Thread(target=self.orchestrator.stop, args=(timeout,), daemon=True).start()
                    break
            except Exception:
                if self._stop_event.is_set():
                    break
            finally:
                if conn:
                    try:
                        conn.close()
                    except Exception:
                        pass

    def stop(self) -> None:
        """Close control listener and stop server thread."""
        self._stop_event.set()
        if self._listener:
            try:
                self._listener.close()
            except Exception:
                pass
            self._listener = None
