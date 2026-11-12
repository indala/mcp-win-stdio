"""
Dynamic Process Pool and JSON-RPC Client for mws server.
Manages lazy-spawning, health-monitoring, and idle-reaping of child MCP server processes.
"""

import atexit
import json
import os
import subprocess
import sys
import threading
import time
from typing import Any, Dict, List, Optional

from .config import DEFAULT_IDLE_TIMEOUT_SECONDS, MAX_RESPONSE_CHARS
from .discovery import discover_available_servers


class MCPProcess:
    """Manages a single running MCP child server process over stdio."""

    def __init__(self, name: str, command: str, args: List[str]):
        self.name = name
        self.command = command
        self.args = args
        self.started_at = time.time()
        self.last_active_at = time.time()
        self.tools_called_count = 0
        self._request_id = 0
        self._lock = threading.Lock()

        # Start child process with unbuffered line-based stdio
        env = os.environ.copy()
        existing_pp = env.get("PYTHONPATH", "")
        extra_paths = [p for p in sys.path if "packages" in p or "src" in p]
        if extra_paths:
            combined = os.pathsep.join(extra_paths)
            env["PYTHONPATH"] = f"{combined}{os.pathsep}{existing_pp}" if existing_pp else combined

        self.proc = subprocess.Popen(
            [self.command, *self.args],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            text=True,
            bufsize=1,
            encoding="utf-8",
        )
        self.pid = self.proc.pid
        self._initialized = False

    def is_alive(self) -> bool:
        """Check if process is still running."""
        return self.proc.poll() is None

    def kill_process_tree(self) -> None:
        """
        Force-terminate the child process and all its grandchildren cleanly on Windows.
        Ensures spawned processes like npx, node, uvx, or python sub-workers don't become zombies.
        """
        if not self.is_alive():
            return
        if sys.platform == "win32":
            try:
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(self.pid)],
                    capture_output=True,
                    stdin=subprocess.DEVNULL,
                    timeout=5.0,
                )
            except Exception:
                try:
                    self.proc.kill()
                except Exception:
                    pass
        else:
            try:
                self.proc.kill()
            except Exception:
                pass

    def _next_id(self) -> int:
        self._request_id += 1
        return self._request_id

    def send_request(self, method: str, params: Optional[Dict[str, Any]] = None, timeout: float = 60.0) -> Any:
        """Send a JSON-RPC request and wait for matching response."""
        with self._lock:
            if not self.is_alive():
                raise RuntimeError(f"MCP server '{self.name}' (PID {self.pid}) is no longer running.")

            req_id = self._next_id()
            payload = {
                "jsonrpc": "2.0",
                "id": req_id,
                "method": method,
                "params": params or {},
            }
            raw = json.dumps(payload) + "\n"
            try:
                self.proc.stdin.write(raw)
                self.proc.stdin.flush()
            except (BrokenPipeError, OSError) as exc:
                self.kill_process_tree()
                raise RuntimeError(f"Failed writing to MCP server '{self.name}': {exc}") from exc

            # Read responses until we find the response matching req_id
            start_time = time.time()
            while time.time() - start_time < timeout:
                line = self.proc.stdout.readline()
                if not line:
                    if not self.is_alive():
                        stderr_out = ""
                        try:
                            stderr_out = self.proc.stderr.read()
                        except Exception:
                            pass
                        raise RuntimeError(
                            f"MCP server '{self.name}' terminated unexpectedly. Stderr: {stderr_out[:500]}"
                        )
                    time.sleep(0.01)
                    continue

                line_str = line.strip()
                if not line_str.startswith("{"):
                    continue

                try:
                    msg = json.loads(line_str)
                except json.JSONDecodeError:
                    continue

                if msg.get("id") == req_id:
                    self.last_active_at = time.time()
                    if "error" in msg:
                        err = msg["error"]
                        raise RuntimeError(f"MCP Error from '{self.name}': {err.get('message', err)}")
                    return msg.get("result")

            # On timeout: kill process tree immediately to prevent pipe desynchronization!
            self.kill_process_tree()
            raise TimeoutError(
                f"Timed out waiting for response from '{self.name}' on method '{method}' after {timeout}s. "
                "Child process tree terminated to prevent pipe desynchronization."
            )

    def send_notification(self, method: str, params: Optional[Dict[str, Any]] = None) -> None:
        """Send a JSON-RPC notification (no response expected)."""
        with self._lock:
            if not self.is_alive():
                return
            payload = {
                "jsonrpc": "2.0",
                "method": method,
                "params": params or {},
            }
            try:
                self.proc.stdin.write(json.dumps(payload) + "\n")
                self.proc.stdin.flush()
            except Exception:
                pass

    def initialize(self) -> None:
        """Perform MCP protocol handshake."""
        if self._initialized:
            return
        init_params = {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "mws", "version": "0.2.5"},
        }
        self.send_request("initialize", init_params, timeout=30.0)
        self.send_notification("notifications/initialized")
        self._initialized = True

    def list_tools(self) -> List[Dict[str, Any]]:
        """Query live tools list dynamically from child server."""
        self.initialize()
        result = self.send_request("tools/list", {})
        return result.get("tools", []) if isinstance(result, dict) else []

    def call_tool(self, tool_name: str, arguments: Optional[Dict[str, Any]] = None) -> Any:
        """Execute a tool dynamically on the child server."""
        self.initialize()
        call_params = {
            "name": tool_name,
            "arguments": arguments or {},
        }
        self.tools_called_count += 1
        result = self.send_request("tools/call", call_params, timeout=120.0)
        return self._format_result(result)

    def _format_result(self, raw_result: Any) -> Any:
        """Format MCP tool call result safely, protecting agent context from overflow."""
        if not raw_result:
            return {"status": "ok", "content": []}

        content_list = raw_result.get("content", []) if isinstance(raw_result, dict) else []
        formatted_content = []

        for item in content_list:
            if isinstance(item, dict) and item.get("type") == "text":
                text = item.get("text", "")
                if len(text) > MAX_RESPONSE_CHARS:
                    truncated = text[:MAX_RESPONSE_CHARS] + f"\n... [Truncated: {len(text) - MAX_RESPONSE_CHARS} characters omitted for context protection]"
                    formatted_content.append({"type": "text", "text": truncated})
                else:
                    try:
                        parsed = json.loads(text)
                        formatted_content.append({"type": "json", "data": parsed})
                    except Exception:
                        formatted_content.append(item)
            else:
                formatted_content.append(item)

        is_error = raw_result.get("isError", False) if isinstance(raw_result, dict) else False
        return {
            "isError": is_error,
            "content": formatted_content if formatted_content else content_list,
        }

    def terminate(self) -> None:
        """Gracefully shut down the child server process and its process tree."""
        with self._lock:
            if not self.is_alive():
                return
            self.kill_process_tree()


class CircuitBreaker:
    """
    Child server circuit breaker.
    Trips open after consecutive infrastructure failures (crashes, timeouts, broken pipes).
    Does NOT count normal tool errors (e.g. invalid SQL syntax or bad args).
    Cooldown: 30 seconds before allowing a single probe attempt.
    """

    def __init__(self, failure_threshold: int = 3, cooldown_seconds: float = 30.0):
        self.failure_threshold = failure_threshold
        self.cooldown_seconds = cooldown_seconds
        self.consecutive_failures: Dict[str, int] = {}
        self.opened_at: Dict[str, float] = {}
        self.probing: Dict[str, bool] = {}
        self._lock = threading.RLock()

    def check_availability(self, server: str) -> Optional[str]:
        """
        Check if server is blocked by open circuit breaker. Returns error message if blocked.
        Guarantees that when transitioning to half-open, exactly ONE thread is granted the probe.
        """
        srv = server.lower().strip()
        with self._lock:
            opened = self.opened_at.get(srv)
            if opened:
                elapsed = time.time() - opened
                if elapsed < self.cooldown_seconds:
                    remaining = int(self.cooldown_seconds - elapsed)
                    return f"Server '{srv}' circuit breaker is OPEN due to repeated process crashes/timeouts. Retry in {remaining}s."
                else:
                    # Cooldown elapsed -> half-open transition
                    if self.probing.get(srv, False):
                        return f"Server '{srv}' is currently probing recovery. Please wait a moment."
                    # Lock probe to this caller
                    self.probing[srv] = True
                    return None
            return None

    def record_success(self, server: str) -> None:
        """Reset failure counter and close circuit breaker."""
        srv = server.lower().strip()
        with self._lock:
            self.consecutive_failures.pop(srv, None)
            self.opened_at.pop(srv, None)
            self.probing.pop(srv, None)

    def record_infrastructure_failure(self, server: str, error_msg: str) -> None:
        """Record a crash, timeout, or pipe failure. Trip breaker if threshold reached."""
        srv = server.lower().strip()
        with self._lock:
            self.probing.pop(srv, None)
            cnt = self.consecutive_failures.get(srv, 0) + 1
            self.consecutive_failures[srv] = cnt
            if cnt >= self.failure_threshold:
                self.opened_at[srv] = time.time()

    def get_status(self) -> Dict[str, Any]:
        """Inspect circuit breaker state for all servers."""
        with self._lock:
            now = time.time()
            res = {}
            for srv, opened in list(self.opened_at.items()):
                remaining = max(0.0, round(self.cooldown_seconds - (now - opened), 1))
                if remaining > 0:
                    res[srv] = {
                        "state": "open",
                        "consecutive_failures": self.consecutive_failures.get(srv, self.failure_threshold),
                        "retry_in_seconds": remaining,
                    }
                else:
                    res[srv] = {"state": "half_open", "consecutive_failures": self.consecutive_failures.get(srv, 0)}
            return res


CIRCUIT_BREAKER = CircuitBreaker()


class ProcessPool:
    """Singleton-style pool of active child MCP processes."""

    def __init__(self):
        self._processes: Dict[str, MCPProcess] = {}
        self._pool_lock = threading.Lock()
        self.circuit_breaker = CIRCUIT_BREAKER
        atexit.register(self.shutdown_all)

    def get_or_spawn(self, server_name: str) -> MCPProcess:
        """Get an existing warm MCP process or spawn a new one on demand."""
        norm_name = server_name.lower().replace("_", "-")

        # Check circuit breaker before attempting to spawn
        blocked_msg = self.circuit_breaker.check_availability(norm_name)
        if blocked_msg:
            raise ConnectionError(blocked_msg)

        with self._pool_lock:
            existing = self._processes.get(norm_name)
            if existing and existing.is_alive():
                return existing

            if existing:
                try:
                    existing.terminate()
                except Exception:
                    pass
                self._processes.pop(norm_name, None)

            available = discover_available_servers()
            srv_spec = available.get(norm_name)
            if not srv_spec:
                raise ValueError(
                    f"Unknown MCP server '{norm_name}'. Available servers: {', '.join(sorted(available.keys()))}"
                )

            try:
                proc = MCPProcess(
                    name=norm_name,
                    command=srv_spec["command"],
                    args=srv_spec["args"],
                )
                proc.initialize()
                self._processes[norm_name] = proc
                self.circuit_breaker.record_success(norm_name)
                return proc
            except Exception as e:
                self.circuit_breaker.record_infrastructure_failure(norm_name, str(e))
                raise

    def stop_server(self, server_name: str) -> bool:
        """Stop a specific active child MCP server."""
        norm_name = server_name.lower().replace("_", "-")
        with self._pool_lock:
            proc = self._processes.pop(norm_name, None)
            if proc:
                proc.terminate()
                return True
            return False

    def reap_idle(self, max_idle_seconds: float = DEFAULT_IDLE_TIMEOUT_SECONDS) -> List[str]:
        """Terminate processes that have been idle longer than max_idle_seconds."""
        now = time.time()
        reaped = []
        with self._pool_lock:
            for name, proc in list(self._processes.items()):
                if now - proc.last_active_at > max_idle_seconds:
                    proc.terminate()
                    self._processes.pop(name, None)
                    reaped.append(name)
        return reaped

    def get_active_sessions(self) -> List[Dict[str, Any]]:
        """Return status information for all active warm child processes."""
        now = time.time()
        sessions = []
        with self._pool_lock:
            for name, proc in list(self._processes.items()):
                if proc.is_alive():
                    sessions.append({
                        "server": name,
                        "pid": proc.pid,
                        "uptime_seconds": round(now - proc.started_at, 1),
                        "idle_seconds": round(now - proc.last_active_at, 1),
                        "tools_called": proc.tools_called_count,
                    })
                else:
                    self._processes.pop(name, None)
        return sessions

    def shutdown_all(self) -> None:
        """Terminate all active children."""
        with self._pool_lock:
            for proc in self._processes.values():
                try:
                    proc.terminate()
                except Exception:
                    pass
            self._processes.clear()


GLOBAL_POOL = ProcessPool()
