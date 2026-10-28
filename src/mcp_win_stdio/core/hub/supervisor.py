"""
Process Supervisor for supervised MCP server instances.
Manages process lifecycle, Win32 Job Object isolation, MCP protocol handshake,
crash loop detection, exponential backoff, and graceful termination.
"""

import json
import logging
import os
import queue
import subprocess
import sys
import threading
import time
from typing import Any, Callable, Dict, List, Optional

from mcp_win_stdio.core.hub.lifecycle import ProcessInstance
from mcp_win_stdio.core.hub.models import (
    LifecycleEvent,
    ProcessInstanceInfo,
    ProjectConfig,
    ServerConfig,
    ServerState,
    SupervisorConfig,
)
from mcp_win_stdio.core.hub.profiles import ProfileManager
from mcp_win_stdio.core.hub.registry import HubRegistry
from mcp_win_stdio.core.hub.secrets import redact_sensitive_data
from mcp_win_stdio.core.hub.win32_job import Win32JobObject

logger = logging.getLogger(__name__)


class ServerNotFoundError(Exception):
    """Raised when an operation is requested on an unregistered server."""


class ProcessSupervisor:
    """
    Supervises the execution, OS isolation, protocol handshake, health monitoring,
    and automatic restart of MCP child servers.
    """

    def __init__(
        self,
        registry: HubRegistry,
        profile_manager: Optional[ProfileManager] = None,
        job_object: Optional[Win32JobObject] = None,
        max_backoff_seconds: float = 30.0,
        auto_start_monitor: bool = True,
        on_event: Optional[Callable[[LifecycleEvent], None]] = None,
    ):
        self._registry = registry
        self._profile_manager = profile_manager
        self._custom_job_object = job_object
        self._job_object = job_object or Win32JobObject()
        self._max_backoff_seconds = max_backoff_seconds
        self._on_event = on_event

        self._instances: Dict[str, ProcessInstance] = {}
        self._server_locks: Dict[str, threading.RLock] = {}
        self._global_lock = threading.RLock()
        self._instance_seq = 0
        self._shutdown_event = threading.Event()

        self._monitor_thread: Optional[threading.Thread] = None
        if auto_start_monitor:
            self._monitor_thread = threading.Thread(
                target=self._monitor_loop,
                name="mws-supervisor-monitor",
                daemon=True,
            )
            self._monitor_thread.start()

    @property
    def job_object(self) -> Win32JobObject:
        """Return the active Windows Job Object instance."""
        return self._job_object

    def _get_server_lock(self, server_name: str) -> threading.RLock:
        """Get or create the per-server lock to ensure serialized start/stop per server."""
        clean = server_name.lower().strip()
        with self._global_lock:
            if clean not in self._server_locks:
                self._server_locks[clean] = threading.RLock()
            return self._server_locks[clean]

    def _dispatch_event(self, event: LifecycleEvent) -> None:
        """Internal callback when an instance emits a lifecycle event."""
        if self._on_event:
            try:
                self._on_event(event)
            except Exception as e:
                logger.warning("Error in supervisor lifecycle event listener: %s", e)

    def start(
        self,
        server_name: str,
        profile_override: Optional[str] = None,
        session_id: Optional[str] = None,
        project_config: Optional[ProjectConfig] = None,
    ) -> ProcessInstanceInfo:
        """
        Start and supervise a configured MCP server.
        Enforces:
          1. Concurrent start guard (no duplicate process spawn).
          2. Win32 Job Object assignment immediately after spawn.
          3. Full MCP protocol handshake (initialize -> initialized notification -> ping).
        """
        clean_name = server_name.lower().strip()

        with self._get_server_lock(clean_name):
            # 1. Check if already active
            existing = self._instances.get(clean_name)
            if existing and existing.state in (
                ServerState.HEALTHY,
                ServerState.STARTING,
                ServerState.INITIALIZING,
            ):
                return existing.snapshot()

            # 2. Resolve ServerConfig from HubRegistry
            server_cfg: Optional[ServerConfig] = self._registry.get_server(clean_name)
            if not server_cfg:
                raise ServerNotFoundError(f"Server '{server_name}' is not registered in the Hub.")
            if not server_cfg.enabled:
                raise ValueError(f"Server '{server_name}' is disabled in the Hub configuration.")

            # 3. Construct Environment with security redaction awareness
            env = os.environ.copy()
            extra_paths = [p for p in sys.path if "packages" in p or "src" in p]
            if extra_paths:
                combined = os.pathsep.join(extra_paths)
                existing_pp = env.get("PYTHONPATH", "")
                env["PYTHONPATH"] = f"{combined}{os.pathsep}{existing_pp}" if existing_pp else combined

            # Merge server config environment
            for k, v in server_cfg.env.items():
                env[k] = str(v)

            # Resolve profile if manager is provided
            if self._profile_manager:
                try:
                    prof, _ = self._profile_manager.resolve_profile(
                        clean_name,
                        request_override=profile_override,
                        session_id=session_id,
                        project_config=project_config,
                    )
                    for pk, pv in prof.parameters.items():
                        env[pk] = str(pv)
                        env[f"MWS_PARAM_{pk.upper()}"] = str(pv)
                    for sk, sec_ref in prof.secrets.items():
                        try:
                            sval = self._profile_manager._secrets.resolve_secret(sec_ref)
                            env[sk] = sval
                            env[f"MWS_SECRET_{sk.upper()}"] = sval
                        except Exception as sec_err:
                            logger.warning("Could not resolve secret '%s': %s", sk, sec_err)
                except Exception as e:
                    logger.debug("Profile resolution bypassed or skipped for %s: %s", clean_name, e)

            # 4. Allocate instance_id
            with self._global_lock:
                self._instance_seq += 1
                inst_id = self._instance_seq

            instance = ProcessInstance(
                server_name=clean_name,
                instance_id=inst_id,
                on_event=self._dispatch_event,
            )
            self._instances[clean_name] = instance
            instance.transition_to(ServerState.STARTING, reason="starting server process")

            # 5. Connect to Windows Job Object for guaranteed kernel process-tree containment
            if self._custom_job_object is not None:
                job = self._custom_job_object
            else:
                job = Win32JobObject(name=f"mws-job-{clean_name}-{instance.instance_id}")
            instance.job_object = job

            # Spawn child with CREATE_SUSPENDED (0x00000004) on Windows to eliminate assignment race conditions
            creationflags = 0x00000004 if job.is_supported else 0
            cmd = [server_cfg.command, *server_cfg.args]
            try:
                proc = subprocess.Popen(
                    cmd,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    env=env,
                    text=True,
                    bufsize=1,
                    encoding="utf-8",
                    creationflags=creationflags,
                )
            except Exception as spawn_exc:
                safe_err = redact_sensitive_data(str(spawn_exc))
                instance.transition_to(ServerState.FAILED, reason=f"Spawn failed: {safe_err}")
                raise

            instance.process = proc
            instance.pid = proc.pid

            # Helper for robust, leak-free cleanup of a failed child spawn
            def _cleanup_failed_spawn(reason: str, error_msg: str) -> None:
                try:
                    proc.kill()
                except Exception:
                    pass
                try:
                    proc.wait(timeout=2.0)
                except Exception:
                    pass
                try:
                    self._close_pipes(proc)
                except Exception:
                    pass
                if instance.job_object:
                    try:
                        instance.job_object.terminate()
                    except Exception:
                        pass
                    if instance.job_object is not self._custom_job_object:
                        try:
                            instance.job_object.close()
                        except Exception:
                            pass
                    instance.job_object = None
                instance.transition_to(ServerState.FAILED, reason=reason)
                raise RuntimeError(error_msg)

            # 6. Assign to Windows Job Object immediately while suspended before executing any code
            if job.is_supported:
                assigned = job.assign_process(proc)
                if not assigned:
                    _cleanup_failed_spawn(
                        reason="Failed to assign process to Windows Job Object",
                        error_msg=(
                            f"Failed to assign child process for '{server_name}' (PID {proc.pid}) to Windows Job Object; "
                            "process terminated to prevent orphan process."
                        ),
                    )

                # Resume the child process after kernel containment is established
                resumed = job.resume_process(proc)
                if not resumed:
                    _cleanup_failed_spawn(
                        reason="Failed to resume suspended child process",
                        error_msg=f"Failed to resume child process for '{server_name}' (PID {proc.pid})",
                    )

            # 7. Start persistent stdout JSON-RPC reader thread
            def stdout_reader() -> None:
                try:
                    if proc.stdout:
                        for line in iter(proc.stdout.readline, ""):
                            line_str = line.strip()
                            if not line_str.startswith("{"):
                                continue
                            try:
                                msg = json.loads(line_str)
                                mid = msg.get("id")
                                if mid is not None and mid in instance.response_queues:
                                    instance.response_queues[mid].put(msg)
                            except Exception:
                                pass
                except Exception:
                    pass
                finally:
                    # Notify any pending callers that process exited
                    err_msg = {
                        "error": {
                            "code": -32000,
                            "message": f"Server '{instance.server_name}' closed stdout prematurely",
                        }
                    }
                    for q_item in list(instance.response_queues.values()):
                        q_item.put(err_msg)

            reader_t = threading.Thread(
                target=stdout_reader,
                name=f"mws-stdout-{instance.server_name}-{instance.instance_id}",
                daemon=True,
            )
            reader_t.start()
            instance.reader_thread = reader_t

            # 8. Transition to INITIALIZING
            instance.transition_to(
                ServerState.INITIALIZING,
                reason="process spawned, assigned to job object, and resumed",
            )

            # 9. Perform full MCP protocol handshake
            try:
                self._perform_mcp_handshake(instance, proc, server_cfg.supervisor)
            except Exception as handshake_err:
                try:
                    proc.kill()
                except Exception:
                    pass
                if instance.job_object:
                    try:
                        instance.job_object.terminate()
                    except Exception:
                        pass
                    if instance.job_object is not self._custom_job_object:
                        try:
                            instance.job_object.close()
                        except Exception:
                            pass
                    instance.job_object = None
                try:
                    proc.wait(timeout=2.0)
                except Exception:
                    pass
                try:
                    self._close_pipes(proc)
                except Exception:
                    pass
                safe_msg = redact_sensitive_data(str(handshake_err))
                instance.transition_to(ServerState.FAILED, reason=f"Handshake failed: {safe_msg}")
                raise

            # 10. Handshake confirmed -> Transition to HEALTHY
            instance.transition_to(ServerState.HEALTHY, reason="MCP handshake acknowledged")
            return instance.snapshot()

    def _perform_mcp_handshake(
        self,
        instance: ProcessInstance,
        proc: subprocess.Popen,
        sup_config: SupervisorConfig,
    ) -> None:
        """
        Execute JSON-RPC handshake over stdin/stdout with timeout safety.
        Sequence:
          1. Send 'initialize'
          2. Wait for response with timeout = startup_timeout_seconds
          3. Send 'notifications/initialized'
          4. (Optional) Send 'ping' and verify response within probe_timeout_seconds
        """
        timeout = sup_config.startup_timeout_seconds

        # Step 1: Send 'initialize' request
        req_id = 1
        q_init: queue.Queue[Dict[str, Any]] = queue.Queue()
        instance.response_queues[req_id] = q_init

        init_req = {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "mws", "version": "0.4.2"},
            },
        }
        try:
            if not proc.stdin:
                raise RuntimeError("Process stdin pipe is not available")
            proc.stdin.write(json.dumps(init_req) + "\n")
            proc.stdin.flush()
        except Exception as e:
            instance.response_queues.pop(req_id, None)
            raise RuntimeError(f"Failed writing initialize request to '{instance.server_name}': {e}") from e

        # Step 2: Await matching initialize response
        try:
            msg = q_init.get(timeout=timeout)
        except queue.Empty:
            code = proc.poll()
            raise TimeoutError(
                f"Timed out waiting for MCP initialize response from '{instance.server_name}' "
                f"after {timeout:.1f}s (process exit code: {code})."
            )
        finally:
            instance.response_queues.pop(req_id, None)

        if "error" in msg:
            err = msg["error"]
            raise RuntimeError(f"MCP initialize error from '{instance.server_name}': {err}")

        result = msg.get("result")
        if not isinstance(result, dict):
            raise RuntimeError(f"MCP initialize response from '{instance.server_name}' missing result dictionary")
        if "protocolVersion" not in result:
            raise RuntimeError(f"MCP initialize response from '{instance.server_name}' missing protocolVersion")

        # Step 3: Send 'notifications/initialized'
        notif = {
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
            "params": {},
        }
        try:
            proc.stdin.write(json.dumps(notif) + "\n")
            proc.stdin.flush()
        except Exception as e:
            raise RuntimeError(f"Failed sending notifications/initialized to '{instance.server_name}': {e}") from e

        # Step 4: Optional protocol ping check
        if sup_config.protocol_ping:
            ping_id = 2
            q_ping: queue.Queue[Dict[str, Any]] = queue.Queue()
            instance.response_queues[ping_id] = q_ping

            ping_req = {
                "jsonrpc": "2.0",
                "id": ping_id,
                "method": "ping",
                "params": {},
            }
            try:
                proc.stdin.write(json.dumps(ping_req) + "\n")
                proc.stdin.flush()
            except Exception as e:
                instance.response_queues.pop(ping_id, None)
                raise RuntimeError(f"Failed sending ping to '{instance.server_name}': {e}") from e

            try:
                ping_msg = q_ping.get(timeout=sup_config.probe_timeout_seconds)
            except queue.Empty:
                code = proc.poll()
                raise TimeoutError(
                    f"Protocol ping to '{instance.server_name}' timed out after "
                    f"{sup_config.probe_timeout_seconds:.1f}s (process exit code: {code})."
                )
            finally:
                instance.response_queues.pop(ping_id, None)

            if "error" in ping_msg:
                raise RuntimeError(f"Protocol ping error from '{instance.server_name}': {ping_msg['error']}")

    def call_tool(
        self,
        server_name: str,
        tool_name: str,
        arguments: Optional[Dict[str, Any]] = None,
        timeout: float = 60.0,
    ) -> Dict[str, Any]:
        """
        Forward an MCP tools/call request to the supervised child server process.
        Thread-safe under server lock; validates process health before dispatch.
        """
        clean_name = server_name.lower().strip()
        with self._get_server_lock(clean_name):
            instance = self._instances.get(clean_name)
            if not instance or instance.state != ServerState.HEALTHY:
                self.start(clean_name)
                instance = self._instances.get(clean_name)

            if not instance or instance.state != ServerState.HEALTHY:
                st = instance.state.value if instance else "unknown"
                raise RuntimeError(f"Server '{server_name}' is not in HEALTHY state (current: {st}).")

            proc = instance.process
            if not proc or proc.poll() is not None:
                code = proc.poll() if proc else None
                raise RuntimeError(f"Server '{server_name}' process is dead (exit code: {code}).")

            with self._global_lock:
                self._instance_seq += 1
                req_id = self._instance_seq

            q: queue.Queue[Dict[str, Any]] = queue.Queue()
            instance.response_queues[req_id] = q

            payload = {
                "jsonrpc": "2.0",
                "id": req_id,
                "method": "tools/call",
                "params": {"name": tool_name, "arguments": arguments or {}},
            }
            try:
                proc.stdin.write(json.dumps(payload) + "\n")
                proc.stdin.flush()
            except Exception as write_err:
                instance.response_queues.pop(req_id, None)
                raise RuntimeError(f"Failed writing tools/call request to '{server_name}': {write_err}") from write_err

        # Lock is released before awaiting response, allowing concurrent multiplexed requests
        try:
            msg = q.get(timeout=timeout)
        except queue.Empty:
            raise TimeoutError(
                f"Timed out executing tool '{tool_name}' on server '{server_name}' after {timeout:.1f}s."
            )
        finally:
            instance.response_queues.pop(req_id, None)

        if "error" in msg:
            err = msg["error"]
            err_msg = err.get("message", err) if isinstance(err, dict) else str(err)
            raise RuntimeError(redact_sensitive_data(f"MCP tool error: {err_msg}"))

        raw_result = msg.get("result", {})
        return redact_sensitive_data(raw_result)

    def list_server_tools(self, server_name: str, timeout: float = 10.0) -> List[Dict[str, Any]]:
        """
        Request tools/list from a healthy supervised child server.
        """
        clean_name = server_name.lower().strip()
        with self._get_server_lock(clean_name):
            instance = self._instances.get(clean_name)
            if not instance or instance.state != ServerState.HEALTHY:
                st = instance.state.value if instance else "unknown"
                raise RuntimeError(f"Server '{server_name}' is not in HEALTHY state (current: {st}).")

            proc = instance.process
            if not proc or proc.poll() is not None:
                code = proc.poll() if proc else None
                raise RuntimeError(f"Server '{server_name}' process is dead (exit code: {code}).")

            with self._global_lock:
                self._instance_seq += 1
                req_id = self._instance_seq

            q: queue.Queue[Dict[str, Any]] = queue.Queue()
            instance.response_queues[req_id] = q

            payload = {
                "jsonrpc": "2.0",
                "id": req_id,
                "method": "tools/list",
                "params": {},
            }
            try:
                proc.stdin.write(json.dumps(payload) + "\n")
                proc.stdin.flush()
            except Exception as write_err:
                instance.response_queues.pop(req_id, None)
                raise RuntimeError(f"Failed writing tools/list request to '{server_name}': {write_err}") from write_err

        try:
            msg = q.get(timeout=timeout)
        except queue.Empty:
            raise TimeoutError(f"Timed out listing tools from server '{server_name}' after {timeout:.1f}s.")
        finally:
            instance.response_queues.pop(req_id, None)

        if "error" in msg:
            err = msg["error"]
            err_msg = err.get("message", err) if isinstance(err, dict) else str(err)
            raise RuntimeError(redact_sensitive_data(f"MCP tools/list error: {err_msg}"))

        result = msg.get("result", {})
        tools = result.get("tools", [])
        return tools if isinstance(tools, list) else []

    def stop(self, server_name: str, timeout: Optional[float] = None) -> ProcessInstanceInfo:
        """
        Gracefully terminate a supervised MCP server instance.
        1. Closes stdin to signal EOF.
        2. Waits up to shutdown_grace_seconds.
        3. If still alive, escalates to force kill.
        4. Transitions state to STOPPED and cleans up pipes.
        """
        clean_name = server_name.lower().strip()

        with self._get_server_lock(clean_name):
            instance = self._instances.get(clean_name)
            if not instance:
                return ProcessInstanceInfo(
                    instance_id=0,
                    server_name=clean_name,
                    pid=None,
                    state=ServerState.STOPPED,
                )

            if instance.state == ServerState.STOPPED:
                return instance.snapshot()

            if instance.state == ServerState.FAILED:
                # Process has already failed/exited; ensure pipes closed and transition cleanly to STOPPED
                proc = instance.process
                if proc:
                    self._close_pipes(proc)
                if instance.job_object:
                    try:
                        instance.job_object.terminate()
                        instance.job_object.close()
                    except Exception:
                        pass
                    instance.job_object = None
                instance.transition_to(ServerState.STOPPED, reason="stopped from failed state")
                return instance.snapshot()

            if instance.state != ServerState.STOPPING:
                instance.transition_to(ServerState.STOPPING, reason="stop requested")

            proc = instance.process
            if proc and proc.poll() is None:
                # 1. Close stdin to signal graceful exit
                try:
                    if proc.stdin and not proc.stdin.closed:
                        proc.stdin.close()
                except Exception:
                    pass

                # 2. Wait up to configured grace period
                srv_cfg = self._registry.get_server(clean_name)
                grace = (
                    timeout if timeout is not None else (srv_cfg.supervisor.shutdown_grace_seconds if srv_cfg else 5.0)
                )

                try:
                    proc.wait(timeout=grace)
                except subprocess.TimeoutExpired:
                    logger.warning(
                        "Server '%s' (PID %s) did not exit within %.1fs; force-terminating",
                        clean_name,
                        proc.pid,
                        grace,
                    )
                    try:
                        proc.kill()
                        if instance.job_object:
                            instance.job_object.terminate()
                        proc.wait(timeout=5.0)
                    except Exception as e:
                        logger.debug("Error during force kill of %s: %s", clean_name, e)

                self._close_pipes(proc)
            elif proc:
                self._close_pipes(proc)

            # Ensure all descendants in the instance's Job Object are terminated and the handle closed
            if instance.job_object:
                try:
                    instance.job_object.terminate()
                    if instance.job_object is not self._custom_job_object:
                        instance.job_object.close()
                except Exception:
                    pass
                instance.job_object = None

            instance.transition_to(ServerState.STOPPED, reason="process exited")
            return instance.snapshot()

    def restart(
        self,
        server_name: str,
        profile_override: Optional[str] = None,
        session_id: Optional[str] = None,
        project_config: Optional[ProjectConfig] = None,
    ) -> ProcessInstanceInfo:
        """Stop and re-launch a supervised MCP server instance."""
        clean_name = server_name.lower().strip()
        with self._get_server_lock(clean_name):
            self.stop(clean_name)
            return self.start(
                clean_name,
                profile_override=profile_override,
                session_id=session_id,
                project_config=project_config,
            )

    def get_status(self, server_name: str) -> Optional[ProcessInstanceInfo]:
        """Return the current immutable snapshot of a server instance, or None if never started."""
        clean_name = server_name.lower().strip()
        with self._global_lock:
            instance = self._instances.get(clean_name)
            return instance.snapshot() if instance else None

    def get_instance(self, server_name: str) -> Optional[ProcessInstanceInfo]:
        """Return the current immutable snapshot of a server instance, or None if never started."""
        return self.get_status(server_name)

    def list_instances(self) -> List[ProcessInstanceInfo]:
        """Return snapshots of all supervised server instances."""
        with self._global_lock:
            return [inst.snapshot() for inst in self._instances.values()]

    def _monitor_loop(self) -> None:
        """Background supervision loop checking for process exits and applying exponential backoff."""
        while not self._shutdown_event.is_set():
            try:
                time.sleep(0.2)
            except Exception:
                break

            if self._shutdown_event.is_set():
                break

            with self._global_lock:
                instances = list(self._instances.values())

            for instance in instances:
                if self._shutdown_event.is_set():
                    break

                with self._get_server_lock(instance.server_name):
                    # Check active states
                    if instance.state in (
                        ServerState.HEALTHY,
                        ServerState.INITIALIZING,
                        ServerState.STARTING,
                        ServerState.DEGRADED,
                    ):
                        proc = instance.process
                        if proc and proc.poll() is not None:
                            exit_code = proc.poll()
                            instance.last_exit_code = exit_code
                            self._close_pipes(proc)
                            reason = redact_sensitive_data(f"Process exited unexpectedly with code {exit_code}")
                            instance.transition_to(ServerState.FAILED, reason=reason)

                            # Evaluate auto-restart policy
                            srv_cfg = self._registry.get_server(instance.server_name)
                            if srv_cfg and srv_cfg.enabled and not self._shutdown_event.is_set():
                                sup = srv_cfg.supervisor
                                if instance.consecutive_crashes <= sup.max_restart_retries:
                                    backoff = min(
                                        sup.restart_backoff_seconds * (2 ** (instance.consecutive_crashes - 1)),
                                        self._max_backoff_seconds,
                                    )
                                    logger.info(
                                        "Scheduling restart for '%s' in %.2fs (crash %d/%d)",
                                        instance.server_name,
                                        backoff,
                                        instance.consecutive_crashes,
                                        sup.max_restart_retries,
                                    )
                                    t = threading.Thread(
                                        target=self._delayed_restart,
                                        args=(instance.server_name, backoff, instance.instance_id),
                                        name=f"mws-restart-{instance.server_name}-{instance.instance_id}",
                                        daemon=True,
                                    )
                                    t.start()
                                else:
                                    logger.warning(
                                        "Server '%s' exceeded max restart retries (%d). Halting auto-restart.",
                                        instance.server_name,
                                        sup.max_restart_retries,
                                    )

    def _delayed_restart(self, server_name: str, delay: float, triggering_instance_id: int) -> None:
        """Wait for backoff delay and perform restart if the instance remains in FAILED state."""
        start = time.time()
        while time.time() - start < delay:
            if self._shutdown_event.is_set():
                return
            time.sleep(0.05)

        if self._shutdown_event.is_set():
            return

        with self._get_server_lock(server_name):
            if self._shutdown_event.is_set():
                return
            current = self._instances.get(server_name)
            # Guarantee: only proceed if current instance matches the crash trigger
            if not current or current.instance_id != triggering_instance_id or current.state != ServerState.FAILED:
                return

            try:
                logger.info("Executing auto-restart for '%s'", server_name)
                self.start(server_name)
            except Exception as e:
                logger.warning("Auto-restart failed for '%s': %s", server_name, redact_sensitive_data(str(e)))

    def _close_pipes(self, proc: subprocess.Popen) -> None:
        """Safely close open stdin/stdout/stderr pipes to prevent resource leaks."""
        for pipe in (proc.stdin, proc.stdout, proc.stderr):
            if pipe and not getattr(pipe, "closed", True):
                try:
                    pipe.close()
                except Exception:
                    pass

    def shutdown(self) -> None:
        """Stop supervisor, terminate all instances, join monitor thread, and close Job Object."""
        self._shutdown_event.set()
        with self._global_lock:
            names = list(self._instances.keys())

        for name in names:
            try:
                self.stop(name, timeout=2.0)
            except Exception as e:
                logger.debug("Error stopping server '%s' during supervisor shutdown: %s", name, e)

        self._job_object.close()
        if getattr(self, "_monitor_thread", None) is not None and self._monitor_thread.is_alive():
            self._monitor_thread.join(timeout=2.0)

    def __enter__(self) -> "ProcessSupervisor":
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.shutdown()
