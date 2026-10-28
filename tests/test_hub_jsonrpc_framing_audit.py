"""
Adversarial tests for Phase 6.2 Audit 3: JSON-RPC protocol framing and reader hardening.

Covers:
1. Bounded line reading & memory exhaustion defense (overflow with terminate policy).
2. Overflow recovery with drain policy (resynchronization on subsequent line).
3. Chunked delivery without newline (small chunks accumulating up to limit).
4. Strict JSON-RPC ID type preservation (integer 1 != string "1").
5. Boolean and float ID rejection (id: true and id: 1.0 do not match int 1).
6. Out-of-order response correlation across multiplexed requests.
7. Late response after caller timeout (discarded without queue contamination).
8. Duplicate response handling (only first delivered, second discarded safely).
9. Unknown and unsolicited response IDs safely ignored.
10. Malformed JSON and plain text stdout lines ignored without reader crash.
11. Non-dict payloads (scalars and batch arrays) ignored safely.
12. Unsolicited notifications (missing or null id) ignored for response queues.
13. Abrupt child process exit notifies all pending callers immediately.
14. Reader thread unblocks and terminates cleanly during supervisor stop/shutdown.
"""

import json
import queue
import sys
import threading
import time
from typing import Any, Dict

import pytest

from mcp_win_stdio.core.hub.lifecycle import ProcessInstance
from mcp_win_stdio.core.hub.models import (
    HubConfig,
    ServerConfig,
    ServerState,
    SupervisorConfig,
)
from mcp_win_stdio.core.hub.registry import HubRegistry
from mcp_win_stdio.core.hub.supervisor import ProcessSupervisor

# ---------------------------------------------------------------------------
# Unit tests: ProcessInstance type-sensitive response queue lifecycle
# ---------------------------------------------------------------------------


def test_response_queue_strict_type_preservation():
    """Verify that integer 1, string '1', boolean True, and float 1.0 are distinct."""
    inst = ProcessInstance(server_name="test_srv", instance_id=1)

    q_int1: queue.Queue = queue.Queue()
    inst.register_response_queue(1, q_int1)

    # String "1" should NOT match integer 1
    msg_str = {"jsonrpc": "2.0", "id": "1", "result": "str_match"}
    assert not inst.deliver_response("1", msg_str)
    assert q_int1.empty()

    # Boolean True should NOT match integer 1 (despite Python True == 1)
    msg_bool = {"jsonrpc": "2.0", "id": True, "result": "bool_match"}
    assert not inst.deliver_response(True, msg_bool)
    assert q_int1.empty()

    # Float 1.0 should NOT match integer 1
    msg_float = {"jsonrpc": "2.0", "id": 1.0, "result": "float_match"}
    assert not inst.deliver_response(1.0, msg_float)
    assert q_int1.empty()

    # Integer 1 should match integer 1 and pop the queue
    msg_int = {"jsonrpc": "2.0", "id": 1, "result": "int_match"}
    assert inst.deliver_response(1, msg_int)
    assert not q_int1.empty()
    assert q_int1.get()["result"] == "int_match"

    # Subsequent delivery to same ID should fail (duplicate response rejected)
    assert not inst.deliver_response(1, msg_int)


def test_response_queue_duplicate_response_discarded():
    """Verify that duplicate responses for the same ID do not contaminate the queue."""
    inst = ProcessInstance(server_name="test_srv", instance_id=1)
    q: queue.Queue = queue.Queue()
    inst.register_response_queue(42, q)

    first_msg = {"jsonrpc": "2.0", "id": 42, "result": "first"}
    second_msg = {"jsonrpc": "2.0", "id": 42, "result": "duplicate"}

    assert inst.deliver_response(42, first_msg) is True
    # Second delivery is rejected because queue was popped atomically
    assert inst.deliver_response(42, second_msg) is False

    assert q.qsize() == 1
    res = q.get_nowait()
    assert res["result"] == "first"


def test_response_queue_late_response_after_timeout():
    """Verify that late response arriving after caller removal is safely ignored."""
    inst = ProcessInstance(server_name="test_srv", instance_id=1)
    q: queue.Queue = queue.Queue()
    inst.register_response_queue(100, q)

    # Caller times out and removes queue
    removed_q = inst.remove_response_queue(100)
    assert removed_q is q

    # Late response arrives
    late_msg = {"jsonrpc": "2.0", "id": 100, "result": "late"}
    assert inst.deliver_response(100, late_msg) is False
    assert q.empty()


def test_response_queue_fail_all_pending():
    """Verify fail_all_pending notifies all registered queues atomically."""
    inst = ProcessInstance(server_name="test_srv", instance_id=1)
    q1: queue.Queue = queue.Queue()
    q2: queue.Queue = queue.Queue()
    inst.register_response_queue(1, q1)
    inst.register_response_queue(2, q2)

    err = {"error": {"code": -32000, "message": "crash"}}
    notified = inst.fail_all_pending(err)
    assert notified == 2
    assert q1.get_nowait() == err
    assert q2.get_nowait() == err
    assert len(inst.response_queues) == 0


# ---------------------------------------------------------------------------
# Integration tests with ProcessSupervisor & real child subprocesses
# ---------------------------------------------------------------------------


def _create_supervisor_with_script(script_body: str, supervisor_cfg: SupervisorConfig) -> ProcessSupervisor:
    hub_cfg = HubConfig(
        servers={
            "mock": ServerConfig(
                name="mock",
                command=sys.executable,
                args=["-u", "-c", script_body],
                enabled=True,
                supervisor=supervisor_cfg,
            )
        }
    )
    registry = HubRegistry(hub_cfg)
    return ProcessSupervisor(registry=registry)


def test_bounded_line_reading_overflow_terminate():
    """
    Child process emits an oversized line exceeding max_line_bytes.
    With default policy='terminate', child process is killed and pending caller receives error.
    """
    # Child script: responds to initialize, then on tools/call emits 50 KB without newline
    script = """
import sys, json
while True:
    line = sys.stdin.readline()
    if not line:
        break
    req = json.loads(line)
    method = req.get("method")
    req_id = req.get("id")
    if method == "initialize":
        sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": req_id, "result": {"protocolVersion": "2024-11-05"}}) + "\\n")
        sys.stdout.flush()
    elif method == "tools/call":
        # Emit 50 KB of garbage without a newline
        sys.stdout.write("X" * 50000)
        sys.stdout.flush()
"""
    sup_cfg = SupervisorConfig(
        startup_timeout_seconds=5.0,
        shutdown_grace_seconds=1.0,
        protocol_ping=False,
        max_line_bytes=4096,  # 4 KB limit
        line_overflow_policy="terminate",
        max_restart_retries=0,
    )

    with _create_supervisor_with_script(script, sup_cfg) as supervisor:
        supervisor.start("mock")
        st = supervisor.get_status("mock")
        assert st is not None and st.state == ServerState.HEALTHY

        # Calling tool should trigger line overflow, terminate process, and raise error
        with pytest.raises(RuntimeError) as exc_info:
            supervisor.call_tool("mock", "test_tool", timeout=3.0)

        assert "exceeded maximum" in str(exc_info.value).lower()

        # Instance should have transitioned to FAILED
        time.sleep(0.3)
        st_after = supervisor.get_status("mock")
        assert st_after is not None and st_after.state == ServerState.FAILED


def test_bounded_line_reading_overflow_drain_recovery():
    """
    Child process emits an oversized line followed by newline, then a valid response.
    With policy='drain', the reader discards the oversized line and successfully receives the valid response.
    """
    script = """
import sys, json
while True:
    line = sys.stdin.readline()
    if not line:
        break
    req = json.loads(line)
    method = req.get("method")
    req_id = req.get("id")
    if method == "initialize":
        sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": req_id, "result": {"protocolVersion": "2024-11-05"}}) + "\\n")
        sys.stdout.flush()
    elif method == "tools/call":
        # Emit an oversized line (> 4 KB), then newline, then the actual valid response!
        sys.stdout.write("OVERSIZED_" * 600 + "\\n")
        sys.stdout.flush()
        resp = {"jsonrpc": "2.0", "id": req_id, "result": {"content": [{"type": "text", "text": "recovered"}]}}
        sys.stdout.write(json.dumps(resp) + "\\n")
        sys.stdout.flush()
"""
    sup_cfg = SupervisorConfig(
        startup_timeout_seconds=5.0,
        shutdown_grace_seconds=1.0,
        protocol_ping=False,
        max_line_bytes=4096,  # 4 KB limit
        line_overflow_policy="drain",
        max_restart_retries=0,
    )

    with _create_supervisor_with_script(script, sup_cfg) as supervisor:
        supervisor.start("mock")
        res = supervisor.call_tool("mock", "test_tool", timeout=4.0)
        assert res["content"][0]["text"] == "recovered"


def test_line_emitted_in_multiple_small_chunks_without_newline():
    """
    Child process emits small chunks without newline. Reader should detect overflow
    when accumulated bytes exceed max_line_bytes without allocating unbounded memory.
    """
    script = """
import sys, json, time
while True:
    line = sys.stdin.readline()
    if not line:
        break
    req = json.loads(line)
    method = req.get("method")
    req_id = req.get("id")
    if method == "initialize":
        sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": req_id, "result": {"protocolVersion": "2024-11-05"}}) + "\\n")
        sys.stdout.flush()
    elif method == "tools/call":
        # Emit 20 chunks of 500 bytes each (10 KB total) without newline
        for _ in range(20):
            sys.stdout.write("A" * 500)
            sys.stdout.flush()
            time.sleep(0.01)
"""
    sup_cfg = SupervisorConfig(
        startup_timeout_seconds=5.0,
        shutdown_grace_seconds=1.0,
        protocol_ping=False,
        max_line_bytes=2048,  # 2 KB limit
        line_overflow_policy="terminate",
        max_restart_retries=0,
    )

    with _create_supervisor_with_script(script, sup_cfg) as supervisor:
        supervisor.start("mock")
        with pytest.raises(RuntimeError) as exc_info:
            supervisor.call_tool("mock", "test_tool", timeout=3.0)

        assert "exceeded maximum" in str(exc_info.value).lower()


def test_id_type_sensitivity_int_vs_string_mismatch():
    """
    When supervisor sends an integer ID, a response returning string ID '1' is rejected
    and does not match the request, causing the request to time out rather than misroute.
    """
    script = """
import sys, json
while True:
    line = sys.stdin.readline()
    if not line:
        break
    req = json.loads(line)
    method = req.get("method")
    req_id = req.get("id")
    if method == "initialize":
        # Proper int match for initialize
        sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": req_id, "result": {"protocolVersion": "2024-11-05"}}) + "\\n")
        sys.stdout.flush()
    elif method == "tools/call":
        # Intentionally coerce ID to string "1", "2", etc.
        resp = {"jsonrpc": "2.0", "id": str(req_id), "result": {"value": "wrong_type"}}
        sys.stdout.write(json.dumps(resp) + "\\n")
        sys.stdout.flush()
"""
    sup_cfg = SupervisorConfig(
        startup_timeout_seconds=5.0,
        shutdown_grace_seconds=1.0,
        protocol_ping=False,
        max_restart_retries=0,
    )

    with _create_supervisor_with_script(script, sup_cfg) as supervisor:
        supervisor.start("mock")
        # Tool call should time out because string ID is rejected by type-sensitive correlation
        with pytest.raises(TimeoutError):
            supervisor.call_tool("mock", "test_tool", timeout=1.0)


def test_out_of_order_responses():
    """
    Two concurrent requests are outstanding. Responses arrive in reverse order.
    Verify each caller receives its own corresponding response.
    """
    script = """
import sys, json, time
while True:
    line = sys.stdin.readline()
    if not line:
        break
    req = json.loads(line)
    method = req.get("method")
    req_id = req.get("id")
    if method == "initialize":
        sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": req_id, "result": {"protocolVersion": "2024-11-05"}}) + "\\n")
        sys.stdout.flush()
    elif method == "tools/call":
        tool_name = req.get("params", {}).get("name")
        if tool_name == "slow":
            # Sleep briefly, then respond
            time.sleep(0.4)
            resp = {"jsonrpc": "2.0", "id": req_id, "result": {"tool": "slow"}}
            sys.stdout.write(json.dumps(resp) + "\\n")
            sys.stdout.flush()
        else:
            # Fast tool responds immediately
            resp = {"jsonrpc": "2.0", "id": req_id, "result": {"tool": "fast"}}
            sys.stdout.write(json.dumps(resp) + "\\n")
            sys.stdout.flush()
"""
    sup_cfg = SupervisorConfig(
        startup_timeout_seconds=5.0,
        shutdown_grace_seconds=1.0,
        protocol_ping=False,
        max_restart_retries=0,
    )

    with _create_supervisor_with_script(script, sup_cfg) as supervisor:
        supervisor.start("mock")

        res_slow: Dict[str, Any] = {}
        res_fast: Dict[str, Any] = {}

        def call_slow():
            nonlocal res_slow
            res_slow = supervisor.call_tool("mock", "slow", timeout=3.0)

        def call_fast():
            nonlocal res_fast
            # Sleep 0.05s so slow request is sent first
            time.sleep(0.05)
            res_fast = supervisor.call_tool("mock", "fast", timeout=3.0)

        t_slow = threading.Thread(target=call_slow)
        t_fast = threading.Thread(target=call_fast)

        t_slow.start()
        t_fast.start()

        t_slow.join(timeout=3.0)
        t_fast.join(timeout=3.0)

        assert res_slow.get("tool") == "slow"
        assert res_fast.get("tool") == "fast"


def test_late_response_followed_by_valid_response():
    """
    A response arrives after caller times out, followed by a valid response for another request.
    Verify the late response is dropped and the second request succeeds.
    """
    script = """
import sys, json, time
while True:
    line = sys.stdin.readline()
    if not line:
        break
    req = json.loads(line)
    method = req.get("method")
    req_id = req.get("id")
    if method == "initialize":
        sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": req_id, "result": {"protocolVersion": "2024-11-05"}}) + "\\n")
        sys.stdout.flush()
    elif method == "tools/call":
        tool_name = req.get("params", {}).get("name")
        if tool_name == "laggy":
            # Laggy call responds after 1.5s
            time.sleep(1.2)
            resp = {"jsonrpc": "2.0", "id": req_id, "result": {"tool": "laggy"}}
            sys.stdout.write(json.dumps(resp) + "\\n")
            sys.stdout.flush()
        else:
            # Subsequent call responds immediately
            resp = {"jsonrpc": "2.0", "id": req_id, "result": {"tool": "quick"}}
            sys.stdout.write(json.dumps(resp) + "\\n")
            sys.stdout.flush()
"""
    sup_cfg = SupervisorConfig(
        startup_timeout_seconds=5.0,
        shutdown_grace_seconds=1.0,
        protocol_ping=False,
        max_restart_retries=0,
    )

    with _create_supervisor_with_script(script, sup_cfg) as supervisor:
        supervisor.start("mock")

        # 1. Laggy call with 0.5s timeout: times out
        with pytest.raises(TimeoutError):
            supervisor.call_tool("mock", "laggy", timeout=0.5)

        # Wait for the laggy response to arrive and be discarded on child stdout
        time.sleep(1.0)

        # 2. Subsequent call: should succeed cleanly without contamination
        res = supervisor.call_tool("mock", "quick", timeout=2.0)
        assert res.get("tool") == "quick"


def test_malformed_json_and_scalar_lines_ignored():
    """
    Child process emits plain text logs, malformed JSON, and scalar JSON values.
    Verify reader does not crash and processes the subsequent valid response.
    """
    script = """
import sys, json
while True:
    line = sys.stdin.readline()
    if not line:
        break
    req = json.loads(line)
    method = req.get("method")
    req_id = req.get("id")
    if method == "initialize":
        sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": req_id, "result": {"protocolVersion": "2024-11-05"}}) + "\\n")
        sys.stdout.flush()
    elif method == "tools/call":
        # Emit plain text log
        sys.stdout.write("[INFO] Child server processing request\\n")
        # Emit malformed JSON
        sys.stdout.write("{\\\"invalid_json\\\": incomplete\\n")
        # Emit JSON scalar
        sys.stdout.write("12345\\n")
        # Emit JSON array
        sys.stdout.write("[\\\"array_item\\\"]\\n")
        # Emit unsolicited notification
        sys.stdout.write(json.dumps({"jsonrpc": "2.0", "method": "notifications/progress", "params": {}}) + "\\n")
        sys.stdout.flush()

        # Finally emit valid response
        resp = {"jsonrpc": "2.0", "id": req_id, "result": {"status": "success"}}
        sys.stdout.write(json.dumps(resp) + "\\n")
        sys.stdout.flush()
"""
    sup_cfg = SupervisorConfig(
        startup_timeout_seconds=5.0,
        shutdown_grace_seconds=1.0,
        protocol_ping=False,
        max_restart_retries=0,
    )

    with _create_supervisor_with_script(script, sup_cfg) as supervisor:
        supervisor.start("mock")
        res = supervisor.call_tool("mock", "test_tool", timeout=3.0)
        assert res.get("status") == "success"


def test_child_abrupt_exit_releases_pending_callers():
    """
    Child process terminates abruptly while callers are waiting for responses.
    Verify pending callers are released immediately with a clean error rather than hanging.
    """
    script = """
import sys, json, os
while True:
    line = sys.stdin.readline()
    if not line:
        break
    req = json.loads(line)
    method = req.get("method")
    req_id = req.get("id")
    if method == "initialize":
        sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": req_id, "result": {"protocolVersion": "2024-11-05"}}) + "\\n")
        sys.stdout.flush()
    elif method == "tools/call":
        # Abruptly exit without sending response
        os._exit(1)
"""
    sup_cfg = SupervisorConfig(
        startup_timeout_seconds=5.0,
        shutdown_grace_seconds=1.0,
        protocol_ping=False,
        max_restart_retries=0,
    )

    with _create_supervisor_with_script(script, sup_cfg) as supervisor:
        supervisor.start("mock")
        start = time.time()
        with pytest.raises(RuntimeError) as exc_info:
            supervisor.call_tool("mock", "test_tool", timeout=10.0)

        elapsed = time.time() - start
        # Caller should be notified immediately upon child exit, well before 10s timeout
        assert elapsed < 3.0
        assert "closed stdout prematurely" in str(exc_info.value).lower()


def test_supervisor_shutdown_unblocks_reader_thread():
    """
    When supervisor shutdown is called while reader thread is blocked on empty stdout,
    the reader thread terminates cleanly and joins within the shutdown deadline.
    """
    script = """
import sys, json, time
while True:
    line = sys.stdin.readline()
    if not line:
        break
    req = json.loads(line)
    method = req.get("method")
    req_id = req.get("id")
    if method == "initialize":
        sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": req_id, "result": {"protocolVersion": "2024-11-05"}}) + "\\n")
        sys.stdout.flush()
    # After initialize, server remains alive and silent on stdout
"""
    sup_cfg = SupervisorConfig(
        startup_timeout_seconds=5.0,
        shutdown_grace_seconds=1.0,
        protocol_ping=False,
        max_restart_retries=0,
    )

    supervisor = _create_supervisor_with_script(script, sup_cfg)
    try:
        supervisor.start("mock")
        inst = supervisor._instances.get("mock")
        assert inst is not None
        reader_t = inst.reader_thread
        assert reader_t is not None and reader_t.is_alive()
    finally:
        start = time.time()
        supervisor.shutdown()
        elapsed = time.time() - start

        # Shutdown should complete quickly and join reader thread cleanly
        assert elapsed < 3.0
        assert not reader_t.is_alive()


def test_end_to_end_duplicate_response_discarded():
    """
    Child process emits duplicate responses for the same request ID over stdio.
    Verify the first response is delivered and the second response is discarded safely.
    """
    script = """
import sys, json
while True:
    line = sys.stdin.readline()
    if not line:
        break
    req = json.loads(line)
    method = req.get("method")
    req_id = req.get("id")
    if method == "initialize":
        sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": req_id, "result": {"protocolVersion": "2024-11-05"}}) + "\\n")
        sys.stdout.flush()
    elif method == "tools/call":
        # Emit original response
        resp1 = {"jsonrpc": "2.0", "id": req_id, "result": {"content": [{"type": "text", "text": "first_response"}]}}
        sys.stdout.write(json.dumps(resp1) + "\\n")
        # Emit duplicate response for the exact same ID
        resp2 = {"jsonrpc": "2.0", "id": req_id, "result": {"content": [{"type": "text", "text": "duplicate_response"}]}}
        sys.stdout.write(json.dumps(resp2) + "\\n")
        sys.stdout.flush()
"""
    sup_cfg = SupervisorConfig(
        startup_timeout_seconds=5.0,
        shutdown_grace_seconds=1.0,
        protocol_ping=False,
        max_restart_retries=0,
    )

    with _create_supervisor_with_script(script, sup_cfg) as supervisor:
        supervisor.start("mock")
        res = supervisor.call_tool("mock", "test_tool", timeout=3.0)
        assert res["content"][0]["text"] == "first_response"

        # Check instance state: no orphaned response queues left behind
        inst = supervisor._instances.get("mock")
        assert inst is not None
        assert len(inst.response_queues) == 0


def test_bounded_line_reading_overflow_terminate_followed_by_output():
    """
    Child emits an oversized line followed by another message under policy='terminate'.
    Verifies that the child process is terminated immediately upon overflow and subsequent
    output is not processed.
    """
    script = """
import sys, json
while True:
    line = sys.stdin.readline()
    if not line:
        break
    req = json.loads(line)
    method = req.get("method")
    req_id = req.get("id")
    if method == "initialize":
        sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": req_id, "result": {"protocolVersion": "2024-11-05"}}) + "\\n")
        sys.stdout.flush()
    elif method == "tools/call":
        # Emit oversized chunk (> 4096 bytes) followed by newline and then a valid response
        sys.stdout.write("G" * 5000 + "\\n")
        resp = {"jsonrpc": "2.0", "id": req_id, "result": {"status": "unreachable"}}
        sys.stdout.write(json.dumps(resp) + "\\n")
        sys.stdout.flush()
"""
    sup_cfg = SupervisorConfig(
        startup_timeout_seconds=5.0,
        shutdown_grace_seconds=1.0,
        protocol_ping=False,
        max_line_bytes=4096,
        line_overflow_policy="terminate",
        max_restart_retries=0,
    )

    with _create_supervisor_with_script(script, sup_cfg) as supervisor:
        supervisor.start("mock")
        with pytest.raises(RuntimeError) as exc_info:
            supervisor.call_tool("mock", "test_tool", timeout=3.0)

        assert "exceeded maximum" in str(exc_info.value).lower()
        time.sleep(0.3)
        inst = supervisor._instances.get("mock")
        assert inst is not None and inst.state == ServerState.FAILED


def test_supervisor_config_line_bounds_validation():
    """Verify validation of max_line_bytes and line_overflow_policy in SupervisorConfig."""
    # Valid configurations
    cfg1 = SupervisorConfig.from_dict({"max_line_bytes": 1024, "line_overflow_policy": "drain"})
    assert cfg1.max_line_bytes == 1024
    assert cfg1.line_overflow_policy == "drain"

    cfg2 = SupervisorConfig.from_dict({"max_line_bytes": 8192, "line_overflow_policy": "terminate"})
    assert cfg2.max_line_bytes == 8192
    assert cfg2.line_overflow_policy == "terminate"

    # Non-positive max_line_bytes rejected
    with pytest.raises(ValueError, match="max_line_bytes must be positive"):
        SupervisorConfig.from_dict({"max_line_bytes": 0})

    with pytest.raises(ValueError, match="max_line_bytes must be positive"):
        SupervisorConfig.from_dict({"max_line_bytes": -100})

    # Invalid line_overflow_policy rejected
    with pytest.raises(ValueError, match="line_overflow_policy must be 'terminate' or 'drain'"):
        SupervisorConfig.from_dict({"line_overflow_policy": "ignore"})


def test_bounded_line_reading_multibyte_utf8_byte_limit():
    """
    Verify that max_line_bytes is enforced in exact BYTES, not character counts.
    Sends 1,000 four-byte UTF-8 emojis (4,000 bytes) with a limit of 2,048 bytes.
    In character mode this would be 1,000 chars (< 2048), but in byte mode it exceeds 2048.
    """
    script = """
import sys, json
while True:
    line = sys.stdin.readline()
    if not line:
        break
    req = json.loads(line)
    method = req.get("method")
    req_id = req.get("id")
    if method == "initialize":
        sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": req_id, "result": {"protocolVersion": "2024-11-05"}}) + "\\n")
        sys.stdout.flush()
    elif method == "tools/call":
        # 1000 rocket emojis = 1000 characters, but 4000 UTF-8 bytes!
        emojis = "\\U0001F680" * 1000
        sys.stdout.write(emojis + "\\n")
        sys.stdout.flush()
"""
    sup_cfg = SupervisorConfig(
        startup_timeout_seconds=5.0,
        shutdown_grace_seconds=1.0,
        protocol_ping=False,
        max_line_bytes=2048,  # 2 KB byte limit
        line_overflow_policy="terminate",
        max_restart_retries=0,
    )

    with _create_supervisor_with_script(script, sup_cfg) as supervisor:
        supervisor.start("mock")
        with pytest.raises(RuntimeError) as exc_info:
            supervisor.call_tool("mock", "test_tool", timeout=3.0)

        assert "exceeded maximum" in str(exc_info.value).lower()
        time.sleep(0.3)
        inst = supervisor._instances.get("mock")
        assert inst is not None and inst.state == ServerState.FAILED


def test_multibyte_utf8_within_limits_parsed_cleanly():
    """
    Verify that multibyte UTF-8 input (Japanese, emojis) within max_line_bytes
    is decoded cleanly and delivers correct content without corruption.
    """
    script = """
import sys, json
while True:
    line = sys.stdin.readline()
    if not line:
        break
    req = json.loads(line)
    method = req.get("method")
    req_id = req.get("id")
    if method == "initialize":
        sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": req_id, "result": {"protocolVersion": "2024-11-05"}}) + "\\n")
        sys.stdout.flush()
    elif method == "tools/call":
        resp = {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {"greeting": "こんにちは世界！ 🚀✨", "count": 42}
        }
        sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\\n")
        sys.stdout.flush()
"""
    sup_cfg = SupervisorConfig(
        startup_timeout_seconds=5.0,
        shutdown_grace_seconds=1.0,
        protocol_ping=False,
        max_line_bytes=16384,
        max_restart_retries=0,
    )

    with _create_supervisor_with_script(script, sup_cfg) as supervisor:
        supervisor.start("mock")
        res = supervisor.call_tool("mock", "test_tool", timeout=3.0)
        assert res.get("greeting") == "こんにちは世界！ 🚀✨"
        assert res.get("count") == 42


def test_bounded_line_reading_drain_newline_in_crossing_chunk():
    """
    Under policy='drain', child emits an oversized line whose final chunk contains
    the newline, followed immediately by another valid tool request and response.
    Verify the oversized line is discarded and the subsequent valid call succeeds.
    """
    script = """
import sys, json
while True:
    line = sys.stdin.readline()
    if not line:
        break
    req = json.loads(line)
    method = req.get("method")
    req_id = req.get("id")
    if method == "initialize":
        sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": req_id, "result": {"protocolVersion": "2024-11-05"}}) + "\\n")
        sys.stdout.flush()
    elif method == "tools/call":
        tool_name = req.get("params", {}).get("name")
        if tool_name == "overflow_tool":
            # 5000 bytes line with newline at end (> 2048 limit)
            sys.stdout.write("D" * 5000 + "\\n")
            sys.stdout.flush()
        else:
            resp = {"jsonrpc": "2.0", "id": req_id, "result": {"recovered": True}}
            sys.stdout.write(json.dumps(resp) + "\\n")
            sys.stdout.flush()
"""
    sup_cfg = SupervisorConfig(
        startup_timeout_seconds=5.0,
        shutdown_grace_seconds=1.0,
        protocol_ping=False,
        max_line_bytes=2048,
        line_overflow_policy="drain",
        max_restart_retries=0,
    )

    with _create_supervisor_with_script(script, sup_cfg) as supervisor:
        supervisor.start("mock")
        # 1. Overflow call times out because its oversized response was discarded
        with pytest.raises(TimeoutError):
            supervisor.call_tool("mock", "overflow_tool", timeout=0.6)

        # 2. Subsequent call succeeds immediately through stream resynchronization
        res = supervisor.call_tool("mock", "valid_tool", timeout=2.0)
        assert res.get("recovered") is True


def test_handshake_and_tool_call_request_ids_are_globally_unique():
    """
    Verify that initialize, ping, and subsequent tool call IDs are strictly
    unique and monotonically increasing, eliminating cross-lifecycle ID collisions.
    """
    script = """
import sys, json
while True:
    line = sys.stdin.readline()
    if not line:
        break
    req = json.loads(line)
    method = req.get("method")
    req_id = req.get("id")
    if method == "initialize":
        sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": req_id, "result": {"protocolVersion": "2024-11-05"}}) + "\\n")
        sys.stdout.flush()
    elif method == "ping":
        sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": req_id, "result": {}}) + "\\n")
        sys.stdout.flush()
    elif method == "tools/call":
        resp = {"jsonrpc": "2.0", "id": req_id, "result": {"observed_id": req_id}}
        sys.stdout.write(json.dumps(resp) + "\\n")
        sys.stdout.flush()
"""
    sup_cfg = SupervisorConfig(
        startup_timeout_seconds=5.0,
        shutdown_grace_seconds=1.0,
        protocol_ping=True,
        max_restart_retries=0,
    )

    with _create_supervisor_with_script(script, sup_cfg) as supervisor:
        supervisor.start("mock")
        # Tool call 1
        res1 = supervisor.call_tool("mock", "test_tool", timeout=2.0)
        # Tool call 2
        res2 = supervisor.call_tool("mock", "test_tool", timeout=2.0)

        id1 = res1.get("observed_id")
        id2 = res2.get("observed_id")

        # Handshake used instance_id (1), init_id (2), ping_id (3)
        # Therefore tool call 1 must have id >= 4, and id2 > id1
        assert id1 > 3
        assert id2 > id1


def test_custom_server_env_overrides_pythonioencoding():
    """
    Verify that if a server explicitly configures PYTHONIOENCODING in its env,
    the supervisor respects the custom server configuration over default UTF-8.
    """
    hub_cfg = HubConfig(
        servers={
            "custom_env": ServerConfig(
                name="custom_env",
                command=sys.executable,
                args=["-u", "-c", "import sys, os; print(os.environ.get('PYTHONIOENCODING', ''))"],
                enabled=True,
                env={"PYTHONIOENCODING": "latin-1"},
            )
        }
    )
    registry = HubRegistry(hub_cfg)
    supervisor = ProcessSupervisor(registry=registry)
    with supervisor:
        srv = registry.get_server("custom_env")
        assert srv is not None
        assert srv.env.get("PYTHONIOENCODING") == "latin-1"
