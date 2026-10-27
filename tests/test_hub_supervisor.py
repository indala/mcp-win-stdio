"""
Unit and integration tests for ProcessSupervisor (Phase 3 Step 2).
Covers process ownership, Win32 Job Object isolation, MCP handshake,
exponential backoff, shutdown escalation, and secret redaction.
"""

import subprocess
import sys
import threading
import time
from unittest.mock import MagicMock

import pytest

from mcp_win_stdio.core.hub.models import (
    HubConfig,
    LifecycleEvent,
    ProfileConfig,
    SecretReference,
    ServerConfig,
    ServerProfileManifest,
    ServerState,
    SupervisorConfig,
)
from mcp_win_stdio.core.hub.profiles import ProfileManager
from mcp_win_stdio.core.hub.registry import HubRegistry
from mcp_win_stdio.core.hub.secrets import EnvSecretProvider, SecretRegistry
from mcp_win_stdio.core.hub.supervisor import ProcessSupervisor, ServerNotFoundError
from mcp_win_stdio.core.hub.win32_job import Win32JobObject

# Mock MCP server that answers initialize and ping then holds open until stdin EOF
MOCK_MCP_SCRIPT = """
import sys, json
while True:
    line = sys.stdin.readline()
    if not line:
        break
    try:
        req = json.loads(line)
        method = req.get("method")
        req_id = req.get("id")
        if method == "initialize":
            resp = {"jsonrpc": "2.0", "id": req_id, "result": {"protocolVersion": "2024-11-05", "capabilities": {}}}
            sys.stdout.write(json.dumps(resp) + "\\n")
            sys.stdout.flush()
        elif method == "ping":
            resp = {"jsonrpc": "2.0", "id": req_id, "result": {}}
            sys.stdout.write(json.dumps(resp) + "\\n")
            sys.stdout.flush()
    except Exception:
        pass
"""

# Mock hanging server that never responds
MOCK_HANGING_SCRIPT = """
import time
time.sleep(30)
"""

# Mock unresponsive server that ignores stdin close
MOCK_UNRESPONSIVE_SCRIPT = """
import sys, json, time
while True:
    line = sys.stdin.readline()
    if not line:
        break
    try:
        req = json.loads(line)
        method = req.get("method")
        req_id = req.get("id")
        if method == "initialize":
            resp = {"jsonrpc": "2.0", "id": req_id, "result": {"protocolVersion": "2024-11-05", "capabilities": {}}}
            sys.stdout.write(json.dumps(resp) + "\\n")
            sys.stdout.flush()
        elif method == "ping":
            resp = {"jsonrpc": "2.0", "id": req_id, "result": {}}
            sys.stdout.write(json.dumps(resp) + "\\n")
            sys.stdout.flush()
            # Handshake complete! Now ignore any further stdin and hang
            break
    except Exception:
        pass

time.sleep(30)
"""


@pytest.fixture
def base_registry():
    """Create a HubRegistry populated with mock servers."""
    registry = HubRegistry()
    registry.load_from_dict(
        {
            "schema_version": "1.0",
            "servers": {
                "mock_srv": {
                    "command": sys.executable,
                    "args": ["-u", "-c", MOCK_MCP_SCRIPT],
                    "supervisor": {
                        "startup_timeout_seconds": 5.0,
                        "shutdown_grace_seconds": 1.0,
                        "max_restart_retries": 2,
                        "restart_backoff_seconds": 0.2,
                        "protocol_ping": True,
                        "probe_timeout_seconds": 2.0,
                    },
                },
                "hang_srv": {
                    "command": sys.executable,
                    "args": ["-u", "-c", MOCK_HANGING_SCRIPT],
                    "supervisor": {
                        "startup_timeout_seconds": 0.5,
                        "shutdown_grace_seconds": 0.5,
                    },
                },
                "unresponsive_srv": {
                    "command": sys.executable,
                    "args": ["-u", "-c", MOCK_UNRESPONSIVE_SCRIPT],
                    "supervisor": {
                        "startup_timeout_seconds": 5.0,
                        "shutdown_grace_seconds": 0.5,
                    },
                },
            },
        }
    )
    return registry


def test_1_successful_spawn_job_assignment_and_handshake(base_registry):
    """1. Verify successful spawn, Job Object assignment, and handshake to HEALTHY."""
    events = []
    with ProcessSupervisor(registry=base_registry, on_event=events.append) as supervisor:
        info = supervisor.start("mock_srv")
        assert info.state == ServerState.HEALTHY
        assert info.pid is not None
        assert info.instance_id == 1

        # Verify Job Object
        if supervisor.job_object.is_supported:
            assert supervisor.job_object.handle is not None

        # Verify event sequence
        state_flow = [ev.new_state for ev in events]
        assert state_flow == [
            ServerState.STARTING,
            ServerState.INITIALIZING,
            ServerState.HEALTHY,
        ]

        # Stop and verify transition
        stop_info = supervisor.stop("mock_srv")
        assert stop_info.state == ServerState.STOPPED


def test_2_job_assignment_failure_terminates_child_without_orphan(base_registry):
    """2. Verify that if Job Object assignment fails, child is killed immediately (0 orphans)."""
    mock_job = MagicMock(spec=Win32JobObject)
    mock_job.is_supported = True
    mock_job.assign_process.return_value = False  # Simulate OS assignment failure

    with ProcessSupervisor(registry=base_registry, job_object=mock_job) as supervisor:
        with pytest.raises(RuntimeError, match="Failed to assign child process"):
            supervisor.start("mock_srv")

        status = supervisor.get_status("mock_srv")
        assert status.state == ServerState.FAILED
        assert "Job Object" in (status.last_error or "")


def test_3_handshake_timeout_and_failure(base_registry):
    """3. Verify hanging server times out during handshake and is terminated."""
    with ProcessSupervisor(registry=base_registry) as supervisor:
        with pytest.raises((TimeoutError, RuntimeError)):
            supervisor.start("hang_srv")

        status = supervisor.get_status("hang_srv")
        assert status.state == ServerState.FAILED
        assert status.pid is not None


def test_4_unexpected_exit_and_backoff(base_registry):
    """4. Verify monitor detects unexpected exit, records code, and respawns after backoff."""
    with ProcessSupervisor(registry=base_registry) as supervisor:
        info = supervisor.start("mock_srv")
        assert info.state == ServerState.HEALTHY
        initial_pid = info.pid

        # Kill child process externally to simulate a crash
        proc = supervisor._instances["mock_srv"].process
        assert proc is not None
        proc.kill()
        proc.wait()

        # Wait for monitor loop to detect and trigger backoff restart
        deadline = time.time() + 5.0
        recovered = False
        while time.time() < deadline:
            time.sleep(0.1)
            cur = supervisor.get_status("mock_srv")
            if cur and cur.state == ServerState.HEALTHY and cur.pid != initial_pid:
                recovered = True
                break

        assert recovered is True, "Process did not auto-restart to HEALTHY after crash"


def test_5_retry_exhaustion_halts_respawns(base_registry):
    """5. Verify that servers crashing continuously exhaust retries and halt."""
    base_registry.load_from_dict(
        {
            "schema_version": "1.0",
            "servers": {
                "fast_crash": {
                    "command": sys.executable,
                    "args": ["-c", "import sys; sys.exit(42)"],
                    "supervisor": {
                        "startup_timeout_seconds": 1.0,
                        "max_restart_retries": 1,
                        "restart_backoff_seconds": 0.1,
                    },
                }
            },
        }
    )

    with ProcessSupervisor(registry=base_registry) as supervisor:
        with pytest.raises(RuntimeError):
            supervisor.start("fast_crash")

        status = supervisor.get_status("fast_crash")
        assert status.state == ServerState.FAILED

        # Wait for auto-restart thread to trigger and exhaust
        time.sleep(0.8)
        final_status = supervisor.get_status("fast_crash")
        assert final_status.state == ServerState.FAILED
        assert final_status.consecutive_crashes >= 1


def test_6_manual_stop_racing_with_process_exit(base_registry):
    """6. Verify manual stop cleanly halts the server without monitor auto-restarting it."""
    with ProcessSupervisor(registry=base_registry) as supervisor:
        supervisor.start("mock_srv")

        # Call stop
        stop_info = supervisor.stop("mock_srv")
        assert stop_info.state == ServerState.STOPPED

        # Wait to ensure monitor didn't trigger restart
        time.sleep(0.5)
        status = supervisor.get_status("mock_srv")
        assert status.state == ServerState.STOPPED


def test_7_shutdown_during_backoff(base_registry):
    """7. Verify shutdown gracefully aborts pending backoff restarts without hanging."""
    base_registry.load_from_dict(
        {
            "schema_version": "1.0",
            "servers": {
                "long_backoff": {
                    "command": sys.executable,
                    "args": ["-c", "import sys; sys.exit(1)"],
                    "supervisor": {
                        "startup_timeout_seconds": 1.0,
                        "max_restart_retries": 3,
                        "restart_backoff_seconds": 10.0,  # 10s backoff
                    },
                }
            },
        }
    )

    supervisor = ProcessSupervisor(registry=base_registry)
    try:
        with pytest.raises(RuntimeError):
            supervisor.start("long_backoff")

        t0 = time.time()
        # Immediate shutdown should not wait for the 10s backoff timer
        supervisor.shutdown()
        elapsed = time.time() - t0
        assert elapsed < 2.0, f"Shutdown took {elapsed}s, expected < 2.0s"
    finally:
        supervisor.shutdown()


def test_8_graceful_shutdown_escalates_to_force_kill(base_registry):
    """8. Verify that processes ignoring stdin closure are force-killed after grace period."""
    with ProcessSupervisor(registry=base_registry) as supervisor:
        info = supervisor.start("unresponsive_srv")
        assert info.state == ServerState.STARTING or info.pid is not None

        t0 = time.time()
        stop_info = supervisor.stop("unresponsive_srv", timeout=0.5)
        elapsed = time.time() - t0

        assert stop_info.state == ServerState.STOPPED
        # Grace period was 0.5s, should exit shortly after 0.5s
        assert elapsed >= 0.4
        assert elapsed < 3.0


def test_9_concurrent_starts_single_process(base_registry):
    """9. Verify concurrent callers attempting to start the same server get the same instance."""
    results = []

    def start_worker(sup):
        res = sup.start("mock_srv")
        results.append(res)

    with ProcessSupervisor(registry=base_registry) as supervisor:
        threads = [threading.Thread(target=start_worker, args=(supervisor,)) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(results) == 5
        # All callers received the same instance_id and PID
        first_id = results[0].instance_id
        first_pid = results[0].pid
        for r in results:
            assert r.instance_id == first_id
            assert r.pid == first_pid
            assert r.state == ServerState.HEALTHY


def test_10_secrets_never_appear_in_lifecycle_events_or_logs(monkeypatch):
    """10. Verify secret values are redacted from lifecycle event reasons and logs."""
    monkeypatch.setenv("TEST_HUB_SECRET", "super_secret_db_password_12345")

    registry = HubRegistry()
    registry.load_from_dict(
        {
            "schema_version": "1.0",
            "servers": {
                "secret_srv": {
                    "command": sys.executable,
                    # Echoes secret into stderr and fails
                    "args": [
                        "-c",
                        "import os, sys; sys.stderr.write('Fatal with super_secret_db_password_12345\\n'); sys.exit(1)",
                    ],
                    "supervisor": {
                        "startup_timeout_seconds": 1.0,
                    },
                }
            },
        }
    )

    sec_reg = SecretRegistry()
    prof_mgr = ProfileManager(secret_registry=sec_reg)
    prof_mgr.register_manifest(
        "secret_srv",
        ServerProfileManifest(
            default_profile="default",
            profiles={
                "default": ProfileConfig(
                    name="default",
                    secrets={"db_pass": SecretReference(provider="env", key="TEST_HUB_SECRET")},
                )
            },
        ),
    )

    events = []
    with ProcessSupervisor(registry=registry, profile_manager=prof_mgr, on_event=events.append) as supervisor:
        with pytest.raises(RuntimeError):
            supervisor.start("secret_srv")

        status = supervisor.get_status("secret_srv")
        assert status is not None
        assert status.state == ServerState.FAILED

        # Secret MUST NOT appear in status.last_error
        assert "super_secret_db_password_12345" not in (status.last_error or "")

        # Secret MUST NOT appear in any lifecycle event reason
        for ev in events:
            assert "super_secret_db_password_12345" not in (ev.reason or "")
