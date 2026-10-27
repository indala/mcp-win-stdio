"""
Hub Orchestrator: Coordinates HubRegistry, ProfileManager, ProcessSupervisor,
and StreamableHttpBridge into a cohesive runtime lifecycle.
Provides programmatic start(), stop(), and status() with partial failure tolerance,
deterministic server startup, tool auto-discovery, and safe secret redaction.
"""

import logging
import threading
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union

from mcp_win_stdio.core.hub.bridge import StreamableHttpBridge
from mcp_win_stdio.core.hub.config_loader import LoadedHubConfig, load_hub_config
from mcp_win_stdio.core.hub.models import ServerConfig, ServerState
from mcp_win_stdio.core.hub.profiles import ProfileManager
from mcp_win_stdio.core.hub.registry import HubRegistry
from mcp_win_stdio.core.hub.secrets import redact_sensitive_data
from mcp_win_stdio.core.hub.supervisor import ProcessSupervisor
from mcp_win_stdio.core.hub.win32_job import Win32JobObject

logger = logging.getLogger(__name__)


class HubLifecycleState(str, Enum):
    """Lifecycle states of the MCP Hub orchestrator."""

    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    DEGRADED = "degraded"
    STOPPING = "stopping"
    FAILED = "failed"


@dataclass(frozen=True)
class HubStatusInfo:
    """Immutable aggregate status snapshot of the MCP Hub."""

    state: HubLifecycleState
    uptime_seconds: float
    started_at: Optional[float]
    config_source: Optional[str]
    config_path: Optional[str]
    http_host: str
    http_port: int
    active_sessions: int
    servers: Dict[str, Dict[str, Any]]

    def to_dict(self) -> Dict[str, Any]:
        """Return sensitive-redacted dictionary for JSON and status reporting."""
        data = {
            "state": self.state.value,
            "uptime_seconds": round(self.uptime_seconds, 2),
            "started_at": self.started_at,
            "config_source": self.config_source,
            "config_path": self.config_path,
            "http_host": self.http_host,
            "http_port": self.http_port,
            "active_sessions": self.active_sessions,
            "servers": self.servers,
        }
        return redact_sensitive_data(data)


class HubOrchestrator:
    """
    Orchestrates the entire MCP Hub runtime.
    Manages deterministic startup order, child tool discovery, partial failure
    tolerance (DEGRADED state), graceful teardown, and aggregate status reporting.
    """

    def __init__(
        self,
        loaded_config: Optional[LoadedHubConfig] = None,
        config_path: Optional[Union[str, Path]] = None,
        cwd: Optional[Path] = None,
        user_dir: Optional[Path] = None,
        profile_manager: Optional[ProfileManager] = None,
        fail_fast: bool = False,
        job_object: Optional[Win32JobObject] = None,
    ):
        self._lock = threading.RLock()
        self._fail_fast = fail_fast

        # 1. Load or accept configuration
        if loaded_config is not None:
            self._loaded = loaded_config
        else:
            self._loaded = load_hub_config(
                cli_path=config_path,
                cwd=cwd,
                user_dir=user_dir,
                profile_manager=profile_manager,
            )

        # 2. Wire subsystems
        self._registry = HubRegistry(self._loaded.config)
        self._profile_manager = self._loaded.profile_manager
        self._supervisor = ProcessSupervisor(
            registry=self._registry,
            profile_manager=self._profile_manager,
            job_object=job_object,
        )
        self._bridge = StreamableHttpBridge(
            supervisor=self._supervisor,
            registry=self._registry,
            profile_manager=self._profile_manager,
            tool_filter=self._loaded.config.tools,
        )

        self._state = HubLifecycleState.STOPPED
        self._started_at: Optional[float] = None
        self._asgi_app: Optional[Callable[..., Any]] = None

    @property
    def lifecycle_state(self) -> HubLifecycleState:
        """Return the current orchestrator lifecycle state."""
        with self._lock:
            return self._state

    @property
    def supervisor(self) -> ProcessSupervisor:
        return self._supervisor

    @property
    def bridge(self) -> StreamableHttpBridge:
        return self._bridge

    @property
    def registry(self) -> HubRegistry:
        return self._registry

    @property
    def profile_manager(self) -> ProfileManager:
        return self._profile_manager

    @property
    def asgi_app(self) -> Optional[Callable[..., Any]]:
        """Return the initialized Starlette ASGI application, if running."""
        with self._lock:
            return self._asgi_app

    def start(self) -> HubStatusInfo:
        """
        Start the MCP Hub:
          1. Concurrent-start guard prevents duplicate processes and listeners.
          2. Starts configured servers in deterministic sorted order.
          3. Auto-discovers tools from healthy servers and registers them in the bridge.
          4. Fault policy: If a server fails and fail_fast=False, records failure and
             transitions hub to DEGRADED (if others succeed) or FAILED (if all fail).
          5. Mounts the Streamable HTTP ASGI app with Bearer authentication.
        """
        with self._lock:
            # 1. Concurrent start guard: idempotent return if already active
            if self._state in (
                HubLifecycleState.STARTING,
                HubLifecycleState.RUNNING,
                HubLifecycleState.DEGRADED,
            ):
                return self.status()

            self._state = HubLifecycleState.STARTING
            self._started_at = time.time()

            # 2. Determine enabled servers in deterministic sorted order
            enabled_servers: List[ServerConfig] = sorted(
                self._registry.list_servers(enabled_only=True),
                key=lambda s: s.name,
            )

            started_count = 0
            failed_count = 0

            for srv in enabled_servers:
                try:
                    self._supervisor.start(srv.name)
                    # 3. Discover child server tools and register into bridge
                    try:
                        child_tools = self._supervisor.list_server_tools(srv.name)
                        for t in child_tools:
                            t_name = t.get("name")
                            if t_name:
                                self._bridge.register_tool(
                                    server_name=srv.name,
                                    name=t_name,
                                    description=t.get("description", ""),
                                    input_schema=t.get("inputSchema"),
                                )
                    except Exception as disc_err:
                        logger.debug("Tool discovery skipped for '%s': %s", srv.name, disc_err)

                    started_count += 1
                except Exception as srv_err:
                    logger.warning("Failed starting server '%s': %s", srv.name, srv_err)
                    failed_count += 1
                    if self._fail_fast:
                        self._supervisor.shutdown()
                        self._state = HubLifecycleState.FAILED
                        raise

            # 4. Evaluate server startup state
            if enabled_servers:
                if started_count == 0:
                    self._supervisor.shutdown()
                    self._state = HubLifecycleState.FAILED
                    raise RuntimeError(f"All {len(enabled_servers)} configured servers failed to start.")
                elif failed_count > 0:
                    self._state = HubLifecycleState.DEGRADED
                else:
                    self._state = HubLifecycleState.RUNNING
            else:
                self._state = HubLifecycleState.RUNNING

            # 5. Initialize and mount Streamable HTTP ASGI bridge
            try:
                self._asgi_app = self._bridge.create_asgi_app()
            except Exception as bridge_err:
                # Unwind started servers if bridge fails to mount
                self._supervisor.shutdown()
                self._state = HubLifecycleState.FAILED
                raise RuntimeError(f"Failed mounting HTTP bridge application: {bridge_err}") from bridge_err

            return self.status()

    def stop(self, timeout: Optional[float] = None) -> HubStatusInfo:
        """
        Gracefully shut down the MCP Hub:
          1. Idempotent: safe to call repeatedly.
          2. Shuts down HTTP bridge and session manager first.
          3. Shuts down ProcessSupervisor and all child processes.
          4. Transitions state to STOPPED.
        """
        with self._lock:
            if self._state == HubLifecycleState.STOPPED:
                return self.status()

            self._state = HubLifecycleState.STOPPING

            # 1. Stop bridge and purge active sessions
            try:
                self._bridge.shutdown()
            except Exception as be:
                logger.warning("Error during bridge shutdown: %s", be)

            # 2. Stop supervisor and child processes
            try:
                self._supervisor.shutdown()
            except Exception as se:
                logger.warning("Error during supervisor shutdown: %s", se)

            self._state = HubLifecycleState.STOPPED
            self._asgi_app = None
            return self.status()

    def status(self) -> HubStatusInfo:
        """
        Collect aggregate status across all supervised servers, active sessions,
        and runtime uptime.
        """
        with self._lock:
            instances = self._supervisor.list_instances()

            # Dynamic health assessment
            if self._state in (HubLifecycleState.RUNNING, HubLifecycleState.DEGRADED):
                any_failed = any(inst.state in (ServerState.FAILED, ServerState.DEGRADED) for inst in instances)
                all_failed = instances and all(
                    inst.state in (ServerState.FAILED, ServerState.STOPPED) for inst in instances
                )
                if all_failed:
                    current_state = HubLifecycleState.FAILED
                elif any_failed:
                    current_state = HubLifecycleState.DEGRADED
                else:
                    current_state = self._state
            else:
                current_state = self._state

            servers_status: Dict[str, Dict[str, Any]] = {}
            for inst in instances:
                servers_status[inst.server_name] = inst.to_dict()

            now = time.time()
            uptime = (now - self._started_at) if self._started_at and current_state != HubLifecycleState.STOPPED else 0.0

            return HubStatusInfo(
                state=current_state,
                uptime_seconds=uptime,
                started_at=self._started_at,
                config_source=self._loaded.source_tier,
                config_path=str(self._loaded.source_path) if self._loaded.source_path else None,
                http_host=self._loaded.config.http_host,
                http_port=self._loaded.config.http_port,
                active_sessions=self._bridge.session_manager.active_session_count(),
                servers=servers_status,
            )

    def __enter__(self) -> "HubOrchestrator":
        self.start()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.stop()
