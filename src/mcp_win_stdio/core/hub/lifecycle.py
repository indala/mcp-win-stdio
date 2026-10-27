"""
Lifecycle state machine and transition validation for supervised MCP server instances.
Enforces explicit separation between OS spawn (STARTING), protocol handshake (INITIALIZING),
and readiness (HEALTHY), with strict failure semantics and event notifications.
"""

import logging
import queue
import subprocess
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Set

from mcp_win_stdio.core.hub.models import LifecycleEvent, ProcessInstanceInfo, ServerState

logger = logging.getLogger(__name__)


class InvalidStateTransitionError(Exception):
    """Raised when an illegal lifecycle state transition is attempted."""

    def __init__(self, server_name: str, instance_id: int, current_state: ServerState, requested_state: ServerState):
        self.server_name = server_name
        self.instance_id = instance_id
        self.current_state = current_state
        self.requested_state = requested_state
        super().__init__(
            f"Invalid lifecycle transition for server '{server_name}' (instance {instance_id}): "
            f"cannot transition from {current_state.value.upper()} to {requested_state.value.upper()}"
        )


# Valid transition graph
VALID_TRANSITIONS: Dict[ServerState, Set[ServerState]] = {
    ServerState.STOPPED: {ServerState.STARTING},
    ServerState.STARTING: {ServerState.INITIALIZING, ServerState.FAILED, ServerState.STOPPING},
    ServerState.INITIALIZING: {ServerState.HEALTHY, ServerState.FAILED, ServerState.STOPPING},
    ServerState.HEALTHY: {ServerState.DEGRADED, ServerState.STOPPING, ServerState.FAILED},
    ServerState.DEGRADED: {ServerState.HEALTHY, ServerState.STOPPING, ServerState.FAILED},
    ServerState.FAILED: {ServerState.STARTING, ServerState.STOPPED},
    ServerState.STOPPING: {ServerState.STOPPED},
}


class ProcessInstance:
    """
    State machine controller for an individual supervised server process instance.
    Guarantees thread-safe transitions, tracks metrics, and fires lifecycle events.
    """

    def __init__(
        self,
        server_name: str,
        instance_id: int,
        initial_state: ServerState = ServerState.STOPPED,
        on_event: Optional[Callable[[LifecycleEvent], None]] = None,
    ):
        self.server_name = server_name.lower().strip()
        self.instance_id = instance_id
        self._state = initial_state
        self._lock = threading.RLock()

        self.process: Optional[subprocess.Popen] = None
        self.pid: Optional[int] = None
        self.started_at: Optional[float] = None
        self.last_heartbeat: Optional[float] = None
        self.restart_count: int = 0
        self.consecutive_crashes: int = 0
        self.last_exit_code: Optional[int] = None
        self.last_error: Optional[str] = None
        self.response_queues: Dict[int, queue.Queue] = {}
        self.reader_thread: Optional[threading.Thread] = None
        self.job_object: Optional[Any] = None

        self._listeners: List[Callable[[LifecycleEvent], None]] = []
        if on_event:
            self._listeners.append(on_event)

    @property
    def state(self) -> ServerState:
        with self._lock:
            return self._state

    def add_listener(self, listener: Callable[[LifecycleEvent], None]) -> None:
        """Register an event callback for lifecycle transitions."""
        with self._lock:
            if listener not in self._listeners:
                self._listeners.append(listener)

    def remove_listener(self, listener: Callable[[LifecycleEvent], None]) -> None:
        """Remove a previously registered lifecycle listener."""
        with self._lock:
            if listener in self._listeners:
                self._listeners.remove(listener)

    def can_transition_to(self, target: ServerState) -> bool:
        """Check whether transition to target state is legally permissible."""
        with self._lock:
            allowed = VALID_TRANSITIONS.get(self._state, set())
            return target in allowed

    def transition_to(self, new_state: ServerState, reason: Optional[str] = None) -> LifecycleEvent:
        """
        Transition the instance to a new lifecycle state.

        Args:
            new_state: Target ServerState.
            reason: Optional explanation or error message.

        Returns:
            LifecycleEvent: The event emitted by the transition.

        Raises:
            InvalidStateTransitionError: If the transition is not allowed by the state machine.
        """
        with self._lock:
            if not self.can_transition_to(new_state):
                raise InvalidStateTransitionError(
                    server_name=self.server_name,
                    instance_id=self.instance_id,
                    current_state=self._state,
                    requested_state=new_state,
                )

            old_state = self._state
            self._state = new_state
            now = time.time()

            # State-specific tracking
            if new_state == ServerState.STARTING:
                self.started_at = now
            elif new_state == ServerState.HEALTHY:
                self.last_heartbeat = now
                self.consecutive_crashes = 0
            elif new_state == ServerState.FAILED:
                self.consecutive_crashes += 1
                if reason:
                    self.last_error = reason

            event = LifecycleEvent(
                server_name=self.server_name,
                instance_id=self.instance_id,
                old_state=old_state,
                new_state=new_state,
                timestamp=now,
                reason=reason,
            )

            # Fire listeners under snapshot copy to prevent deadlock in external handlers
            listeners = list(self._listeners)

        for callback in listeners:
            try:
                callback(event)
            except Exception as e:
                logger.warning(
                    "Error executing lifecycle listener for %s (instance %d): %s",
                    self.server_name,
                    self.instance_id,
                    e,
                )

        return event

    def snapshot(self) -> ProcessInstanceInfo:
        """Create an immutable snapshot of this instance's current runtime status."""
        with self._lock:
            return ProcessInstanceInfo(
                instance_id=self.instance_id,
                server_name=self.server_name,
                pid=self.pid,
                state=self._state,
                started_at=self.started_at,
                last_heartbeat=self.last_heartbeat,
                restart_count=self.restart_count,
                consecutive_crashes=self.consecutive_crashes,
                last_exit_code=self.last_exit_code,
                last_error=self.last_error,
            )

    def __repr__(self) -> str:
        with self._lock:
            return (
                f"<ProcessInstance(server={self.server_name}, id={self.instance_id}, "
                f"state={self._state.value}, pid={self.pid})>"
            )
