"""
Tests for Hub Runtime Phase 3: Win32 Job Object Isolation and Lifecycle State Machine.
"""

import subprocess
import sys
import time

import pytest

from mcp_win_stdio.core.hub.lifecycle import (
    VALID_TRANSITIONS,
    InvalidStateTransitionError,
    ProcessInstance,
)
from mcp_win_stdio.core.hub.models import LifecycleEvent, ServerState
from mcp_win_stdio.core.hub.win32_job import Win32JobObject


def test_win32_job_object_lifecycle():
    """Verify Job Object creation, process assignment, and termination."""
    job = Win32JobObject(name="test_mws_job")
    if not job.is_supported:
        pytest.skip("Win32 Job Objects only supported on Windows")

    assert job.handle is not None and job.handle != 0

    # Spawn short-lived dummy process
    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(10)"])
    try:
        assigned = job.assign_process(proc)
        assert assigned is True

        # Terminate via Job Object
        term_res = job.terminate(exit_code=42)
        assert term_res is True

        # Process should terminate promptly
        exit_code = proc.wait(timeout=5.0)
        assert exit_code != 0
    finally:
        if proc.poll() is None:
            proc.kill()
        job.close()
        assert job.handle is None


def test_win32_job_object_context_manager():
    """Verify Job Object works cleanly with Python context manager."""
    with Win32JobObject() as job:
        if not job.is_supported:
            pytest.skip("Win32 Job Objects only supported on Windows")
        assert job.handle is not None
    assert job.handle is None


def test_win32_job_object_kernel_kill_on_close():
    """Verify OS kernel automatically kills child processes when Job Object handle closes."""
    job = Win32JobObject()
    if not job.is_supported:
        pytest.skip("Win32 Job Objects only supported on Windows")

    # Spawn process sleeping 30s
    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        assert job.assign_process(proc) is True
        # Close job handle without terminating process directly
        job.close()
        # OS kernel must kill the process promptly due to JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        code = proc.wait(timeout=5.0)
        assert code is not None
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()


def test_lifecycle_happy_path_transitions():
    """Verify full valid transition sequence: STOPPED -> STARTING -> INITIALIZING -> HEALTHY -> STOPPING -> STOPPED."""
    instance = ProcessInstance(server_name="test-server", instance_id=1)
    assert instance.state == ServerState.STOPPED
    assert instance.started_at is None
    assert instance.last_heartbeat is None

    # STOPPED -> STARTING
    ev1 = instance.transition_to(ServerState.STARTING, reason="launch requested")
    assert instance.state == ServerState.STARTING
    assert instance.started_at is not None
    assert ev1.old_state == ServerState.STOPPED
    assert ev1.new_state == ServerState.STARTING

    # STARTING -> INITIALIZING
    ev2 = instance.transition_to(ServerState.INITIALIZING, reason="pipes connected")
    assert instance.state == ServerState.INITIALIZING
    assert ev2.old_state == ServerState.STARTING
    assert ev2.new_state == ServerState.INITIALIZING

    # INITIALIZING -> HEALTHY
    ev3 = instance.transition_to(ServerState.HEALTHY, reason="handshake acknowledged")
    assert instance.state == ServerState.HEALTHY
    assert instance.last_heartbeat is not None
    assert instance.consecutive_crashes == 0
    assert ev3.old_state == ServerState.INITIALIZING
    assert ev3.new_state == ServerState.HEALTHY

    # HEALTHY -> STOPPING
    ev4 = instance.transition_to(ServerState.STOPPING, reason="user shutdown")
    assert instance.state == ServerState.STOPPING
    assert ev4.old_state == ServerState.HEALTHY
    assert ev4.new_state == ServerState.STOPPING

    # STOPPING -> STOPPED
    ev5 = instance.transition_to(ServerState.STOPPED, reason="clean exit")
    assert instance.state == ServerState.STOPPED
    assert ev5.old_state == ServerState.STOPPING
    assert ev5.new_state == ServerState.STOPPED


def test_lifecycle_illegal_transitions_fail_closed():
    """Verify that illegal transitions raise InvalidStateTransitionError and preserve current state."""
    instance = ProcessInstance(server_name="test-server", instance_id=2)
    assert instance.state == ServerState.STOPPED

    # Illegal: STOPPED -> HEALTHY directly
    with pytest.raises(InvalidStateTransitionError) as exc_info:
        instance.transition_to(ServerState.HEALTHY)
    assert exc_info.value.current_state == ServerState.STOPPED
    assert exc_info.value.requested_state == ServerState.HEALTHY
    assert instance.state == ServerState.STOPPED

    # Move to STARTING
    instance.transition_to(ServerState.STARTING)

    # Illegal: STARTING -> HEALTHY (cannot skip INITIALIZING)
    with pytest.raises(InvalidStateTransitionError):
        instance.transition_to(ServerState.HEALTHY)
    assert instance.state == ServerState.STARTING

    # Move to INITIALIZING -> HEALTHY
    instance.transition_to(ServerState.INITIALIZING)
    instance.transition_to(ServerState.HEALTHY)

    # Illegal: HEALTHY -> STARTING (cannot restart without stopping or failing first)
    with pytest.raises(InvalidStateTransitionError):
        instance.transition_to(ServerState.STARTING)
    assert instance.state == ServerState.HEALTHY


def test_lifecycle_degraded_and_failure_semantics():
    """Verify DEGRADED recovery and crash count tracking on FAILED state."""
    instance = ProcessInstance(server_name="db-server", instance_id=3)
    instance.transition_to(ServerState.STARTING)
    instance.transition_to(ServerState.INITIALIZING)
    instance.transition_to(ServerState.HEALTHY)
    assert instance.consecutive_crashes == 0

    # HEALTHY -> DEGRADED
    instance.transition_to(ServerState.DEGRADED, reason="high ping latency")
    assert instance.state == ServerState.DEGRADED

    # DEGRADED -> HEALTHY (recovery)
    instance.transition_to(ServerState.HEALTHY, reason="ping latency normalized")
    assert instance.state == ServerState.HEALTHY

    # HEALTHY -> FAILED (crash)
    instance.transition_to(ServerState.FAILED, reason="process exited unexpectedly")
    assert instance.state == ServerState.FAILED
    assert instance.consecutive_crashes == 1
    assert instance.last_error == "process exited unexpectedly"

    # FAILED -> STARTING -> INITIALIZING -> HEALTHY (recovers and resets consecutive crashes)
    instance.transition_to(ServerState.STARTING)
    instance.transition_to(ServerState.INITIALIZING)
    instance.transition_to(ServerState.HEALTHY)
    assert instance.consecutive_crashes == 0


def test_lifecycle_event_listeners():
    """Verify event listeners receive all transitions and can be unregistered."""
    events: list[LifecycleEvent] = []

    def on_event(ev: LifecycleEvent):
        events.append(ev)

    instance = ProcessInstance(server_name="listener-srv", instance_id=4, on_event=on_event)

    instance.transition_to(ServerState.STARTING, reason="boot")
    instance.transition_to(ServerState.INITIALIZING)

    assert len(events) == 2
    assert events[0].old_state == ServerState.STOPPED
    assert events[0].new_state == ServerState.STARTING
    assert events[0].reason == "boot"
    assert events[1].new_state == ServerState.INITIALIZING

    # Unregister listener
    instance.remove_listener(on_event)
    instance.transition_to(ServerState.HEALTHY)
    # Should still be 2 events
    assert len(events) == 2


def test_lifecycle_snapshot():
    """Verify snapshot creates an immutable ProcessInstanceInfo copy."""
    instance = ProcessInstance(server_name="snapshot-srv", instance_id=10)
    instance.pid = 9999
    instance.transition_to(ServerState.STARTING)

    snap = instance.snapshot()
    assert snap.server_name == "snapshot-srv"
    assert snap.instance_id == 10
    assert snap.pid == 9999
    assert snap.state == ServerState.STARTING
    assert snap.started_at is not None

    d = snap.to_dict()
    assert d["state"] == "starting"
    assert d["instance_id"] == 10
    assert d["server_name"] == "snapshot-srv"


def test_valid_transitions_completeness():
    """Ensure every ServerState enum is present in the transition table."""
    for state in ServerState:
        assert state in VALID_TRANSITIONS
        # Permitted transitions must be a set of ServerState
        assert isinstance(VALID_TRANSITIONS[state], set)
        for target in VALID_TRANSITIONS[state]:
            assert isinstance(target, ServerState)
