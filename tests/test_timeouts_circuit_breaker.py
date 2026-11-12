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
