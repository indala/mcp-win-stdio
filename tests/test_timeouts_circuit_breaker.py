"""
Unit tests for Timeout Tree Kill and Child Server Circuit Breaker.
"""

import sys
import time
from unittest.mock import MagicMock, patch

import pytest

from mcp_win_stdio.server.process_pool import (
    CIRCUIT_BREAKER,
    CircuitBreaker,
    GLOBAL_POOL,
    MCPProcess,
)


def test_circuit_breaker_trip_and_cooldown():
    """Verify circuit breaker opens after 3 infrastructure failures and respects cooldown."""
    cb = CircuitBreaker(failure_threshold=3, cooldown_seconds=0.5)

    # 1. Initial state: closed / available
    assert cb.check_availability("test_srv") is None

    # 2. Record 2 failures (threshold not reached yet)
    cb.record_infrastructure_failure("test_srv", "timeout")
    cb.record_infrastructure_failure("test_srv", "crash")
    assert cb.check_availability("test_srv") is None

    # 3. 3rd failure trips the breaker open
    cb.record_infrastructure_failure("test_srv", "process died")
    blocked = cb.check_availability("test_srv")
    assert blocked is not None
    assert "circuit breaker is OPEN" in blocked

    # 4. Wait out cooldown (0.5s) -> half-open probe permitted
    time.sleep(0.6)
    assert cb.check_availability("test_srv") is None

    # 5. Successful probe call resets the breaker to closed
    cb.record_success("test_srv")
    assert cb.check_availability("test_srv") is None
    assert "test_srv" not in cb.consecutive_failures


def test_timeout_kills_process_tree():
    """Verify timed out request triggers kill_process_tree immediately."""
    proc = MCPProcess(name="fake_server", command=sys.executable, args=["-c", "import time; time.sleep(10)"])
    try:
        assert proc.is_alive()
        # Request with 0.3s timeout must trigger TimeoutError and terminate process tree
        with pytest.raises(TimeoutError) as exc_info:
            proc.send_request("tools/call", {}, timeout=0.3)

        assert "Child process tree terminated" in str(exc_info.value)
        # Give OS 0.5s to clean up PID
        time.sleep(0.5)
        assert not proc.is_alive()
    finally:
        proc.terminate()


def test_timeout_kills_grandchild_process(tmp_path):
    """Verify that timeout tree killing cleanly terminates grandchildren processes."""
    import os

    pid_file = tmp_path / "grandchild.pid"
    child_code = f"""
import subprocess, sys, time
g = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])
with open(r'{pid_file}', 'w') as f:
    f.write(str(g.pid))
time.sleep(30)
"""
    proc = MCPProcess(name="tree_test", command=sys.executable, args=["-c", child_code])
    try:
        # Wait for grandchild PID to be written
        for _ in range(50):
            if pid_file.exists() and pid_file.stat().st_size > 0:
                break
            time.sleep(0.1)

        assert pid_file.exists(), "Grandchild PID file was not created"
        grandchild_pid = int(pid_file.read_text().strip())

        def pid_exists(pid: int) -> bool:
            if sys.platform == "win32":
                import ctypes

                kernel32 = ctypes.windll.kernel32
                handle = kernel32.OpenProcess(0x1000, False, pid)
                if not handle:
                    return False
                exit_code = ctypes.c_ulong()
                kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code))
                kernel32.CloseHandle(handle)
                return exit_code.value == 259  # STILL_ACTIVE
            try:
                os.kill(pid, 0)
                return True
            except OSError:
                return False

        assert pid_exists(grandchild_pid), "Grandchild must be alive before timeout kill"

        # Trigger timeout kill
        with pytest.raises(TimeoutError):
            proc.send_request("tools/call", {}, timeout=0.2)

        time.sleep(0.6)
        assert not proc.is_alive(), "Child process must be dead"
        assert not pid_exists(grandchild_pid), "Grandchild process must be killed by tree kill"
    finally:
        proc.terminate()


def test_circuit_breaker_single_probe_concurrency():
    """Verify that during half-open state, only exactly 1 concurrent probe is permitted."""
    import concurrent.futures

    cb = CircuitBreaker(failure_threshold=2, cooldown_seconds=0.3)
    cb.record_infrastructure_failure("srv1", "crash1")
    cb.record_infrastructure_failure("srv1", "crash2")
    assert cb.check_availability("srv1") is not None

    # Wait out cooldown to enter half-open
    time.sleep(0.4)

    results = []

    def probe_worker():
        return cb.check_availability("srv1")

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futs = [executor.submit(probe_worker) for _ in range(5)]
        for f in futs:
            results.append(f.result())

    # Exactly one thread got None (permission to probe)
    none_count = sum(1 for r in results if r is None)
    blocked_count = sum(1 for r in results if r is not None and "probing recovery" in r)

    assert none_count == 1, f"Expected exactly 1 probe permit, got {none_count}"
    assert blocked_count == 4, f"Expected 4 blocked threads, got {blocked_count}"

