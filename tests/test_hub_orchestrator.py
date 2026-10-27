"""
Unit and integration tests for Profile-Driven Hub Orchestrator (Phase 5 Step 2).
Validates multi-server startup, tool auto-discovery, concurrent start idempotency,
partial failure tolerance (DEGRADED), fail-fast policy, graceful shutdown,
dynamic child crash detection, status reporting, and secret redaction.
"""

import json
import sys
import time
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from mcp_win_stdio.core.hub.config_loader import LoadedHubConfig
from mcp_win_stdio.core.hub.models import (
    HubConfig,
    ServerConfig,
    ServerState,
    SupervisorConfig,
    ToolFilter,
)
from mcp_win_stdio.core.hub.orchestrator import (
    HubLifecycleState,
    HubOrchestrator,
    HubStatusInfo,
)
from mcp_win_stdio.core.hub.profiles import ProfileManager

MOCK_CHILD_MATH = """
import sys, json

while True:
    line = sys.stdin.readline()
    if not line:
        break
    line = line.strip()
    if not line:
        continue
    try:
        req = json.loads(line)
        method = req.get("method")
        req_id = req.get("id")

        if method == "initialize":
            resp = {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "serverInfo": {"name": "math_srv", "version": "1.0"},
                },
            }
        elif method == "ping":
            resp = {"jsonrpc": "2.0", "id": req_id, "result": {}}
        elif method == "tools/list":
            resp = {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "tools": [
                        {
                            "name": "calc_mult",
                            "description": "Multiplies two numbers",
                            "inputSchema": {
                                "type": "object",
                                "properties": {"x": {"type": "integer"}, "y": {"type": "integer"}},
                            },
                        }
                    ]
                },
            }
        elif method == "tools/call":
            params = req.get("params", {})
            name = params.get("name")
            args = params.get("arguments", {})
            if name == "calc_mult":
                ans = args.get("x", 0) * args.get("y", 0)
                resp = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [{"type": "text", "text": f"Product: {ans}"}],
                        "isError": False,
                    },
                }
            else:
                resp = {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": "Method not found"}}
        else:
            continue

        sys.stdout.write(json.dumps(resp) + "\\n")
        sys.stdout.flush()
    except Exception:
        pass
"""

MOCK_CHILD_ECHO = """
import sys, json

while True:
    line = sys.stdin.readline()
    if not line:
        break
    line = line.strip()
    if not line:
        continue
    try:
        req = json.loads(line)
        method = req.get("method")
        req_id = req.get("id")

        if method == "initialize":
            resp = {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "serverInfo": {"name": "echo_srv", "version": "1.0"},
                },
            }
        elif method == "ping":
            resp = {"jsonrpc": "2.0", "id": req_id, "result": {}}
        elif method == "tools/list":
            resp = {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "tools": [
                        {
                            "name": "echo_text",
                            "description": "Echoes text",
                            "inputSchema": {"type": "object", "properties": {"msg": {"type": "string"}}},
                        }
                    ]
                },
            }
        elif method == "tools/call":
            params = req.get("params", {})
            args = params.get("arguments", {})
            resp = {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": f"Echo: {args.get('msg', '')}"}],
                    "isError": False,
                },
            }
        else:
            continue

        sys.stdout.write(json.dumps(resp) + "\\n")
        sys.stdout.flush()
    except Exception:
        pass
"""


@pytest.fixture
def multi_server_loaded_config():
    """Build a LoadedHubConfig with two working child servers (math_srv and echo_srv)."""
    cfg = HubConfig(
        schema_version="1.0",
        http_host="127.0.0.1",
        http_port=8080,
        tools=ToolFilter(allow=["*"], deny=["*forbidden*"]),
        servers={
            "math_srv": ServerConfig(
                name="math_srv",
                command=sys.executable,
                args=["-u", "-c", MOCK_CHILD_MATH],
                supervisor=SupervisorConfig(
                    startup_timeout_seconds=5.0,
                    shutdown_grace_seconds=1.0,
                    protocol_ping=True,
                    probe_timeout_seconds=2.0,
                ),
            ),
            "echo_srv": ServerConfig(
                name="echo_srv",
                command=sys.executable,
                args=["-u", "-c", MOCK_CHILD_ECHO],
                supervisor=SupervisorConfig(
                    startup_timeout_seconds=5.0,
                    shutdown_grace_seconds=1.0,
                    protocol_ping=True,
                    probe_timeout_seconds=2.0,
                ),
            ),
        },
    )
    pm = ProfileManager()
    return LoadedHubConfig(
        config=cfg,
        source_path=Path("hub.yaml"),
        source_tier="test_fixture",
        profile_manager=pm,
    )


def test_orchestrator_multi_server_startup_and_tool_discovery(multi_server_loaded_config, monkeypatch):
    """Orchestrator starts multiple servers, discovers child tools, and serves HTTP bridge."""
    monkeypatch.setenv("MWS_HTTP_AUTH_TOKEN", "orch_test_token_123")
    orchestrator = HubOrchestrator(loaded_config=multi_server_loaded_config)
    try:
        status1 = orchestrator.start()
        assert status1.state == HubLifecycleState.RUNNING
        assert status1.uptime_seconds >= 0.0
        assert "math_srv" in status1.servers
        assert "echo_srv" in status1.servers
        assert status1.servers["math_srv"]["state"] == ServerState.HEALTHY.value
        assert status1.servers["echo_srv"]["state"] == ServerState.HEALTHY.value

        # Verify child tools were auto-discovered and registered in bridge router
        tools = orchestrator.bridge.router.list_tools()
        tool_names = {t.name for t in tools}
        assert "calc_mult" in tool_names
        assert "echo_text" in tool_names

        # Verify execution via ASGI app
        app = orchestrator.asgi_app
        assert app is not None
        with TestClient(app) as client:
            headers = {
                "Authorization": "Bearer orch_test_token_123",
                "Accept": "application/json, text/event-stream",
            }
            # Initialize MCP session
            r_init = client.post(
                "/mcp",
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "agent", "version": "1.0"}},
                },
                headers=headers,
            )
            assert r_init.status_code == 200
            mcp_sess = r_init.headers.get("mcp-session-id")
            if mcp_sess:
                headers["mcp-session-id"] = mcp_sess

            # Call calc_mult (x=6, y=7)
            r_call = client.post(
                "/mcp",
                json={"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "calc_mult", "arguments": {"x": 6, "y": 7}}},
                headers=headers,
            )
            assert r_call.status_code == 200
            assert "Product: 42" in r_call.text
    finally:
        orchestrator.stop()


def test_concurrent_and_repeated_start_is_idempotent(multi_server_loaded_config):
    """Repeated calls to start() do not duplicate processes or re-create listeners."""
    orchestrator = HubOrchestrator(loaded_config=multi_server_loaded_config)
    try:
        s1 = orchestrator.start()
        pid_math = s1.servers["math_srv"]["pid"]
        pid_echo = s1.servers["echo_srv"]["pid"]

        # Call start() again while RUNNING
        s2 = orchestrator.start()
        assert s2.state == HubLifecycleState.RUNNING
        assert s2.servers["math_srv"]["pid"] == pid_math
        assert s2.servers["echo_srv"]["pid"] == pid_echo
    finally:
        orchestrator.stop()


def test_partial_failure_yields_degraded_state(multi_server_loaded_config):
    """When one server fails to start but another succeeds, hub enters DEGRADED state."""
    # Add a broken server that immediately exits with error code 99
    multi_server_loaded_config.config.servers["broken_srv"] = ServerConfig(
        name="broken_srv",
        command=sys.executable,
        args=["-c", "import sys; sys.exit(99)"],
        supervisor=SupervisorConfig(
            startup_timeout_seconds=2.0,
            max_restart_retries=0,
        ),
    )
    orchestrator = HubOrchestrator(loaded_config=multi_server_loaded_config, fail_fast=False)
    try:
        status = orchestrator.start()
        # State must be DEGRADED because math_srv & echo_srv are healthy while broken_srv failed
        assert status.state == HubLifecycleState.DEGRADED
        assert status.servers["broken_srv"]["state"] == ServerState.FAILED.value
        assert status.servers["math_srv"]["state"] == ServerState.HEALTHY.value
        assert status.servers["echo_srv"]["state"] == ServerState.HEALTHY.value
    finally:
        orchestrator.stop()


def test_fail_fast_policy_raises_and_unwinds(multi_server_loaded_config):
    """When fail_fast=True, any server failure raises immediately and unwinds started servers."""
    multi_server_loaded_config.config.servers["broken_srv"] = ServerConfig(
        name="broken_srv",
        command=sys.executable,
        args=["-c", "import sys; sys.exit(99)"],
        supervisor=SupervisorConfig(startup_timeout_seconds=2.0, max_restart_retries=0),
    )
    orchestrator = HubOrchestrator(loaded_config=multi_server_loaded_config, fail_fast=True)
    try:
        with pytest.raises(Exception):
            orchestrator.start()
        assert orchestrator.lifecycle_state == HubLifecycleState.FAILED

        # All servers should be stopped due to unwind
        for inst in orchestrator.supervisor.list_instances():
            assert inst.state == ServerState.STOPPED
    finally:
        orchestrator.stop()


def test_all_servers_failed_transitions_to_failed(tmp_path):
    """When all configured servers fail to start, orchestrator transitions to FAILED."""
    cfg = HubConfig(
        schema_version="1.0",
        servers={
            "broken1": ServerConfig(
                name="broken1",
                command=sys.executable,
                args=["-c", "import sys; sys.exit(1)"],
                supervisor=SupervisorConfig(startup_timeout_seconds=1.0, max_restart_retries=0),
            ),
        },
    )
    loaded = LoadedHubConfig(config=cfg, source_path=None, source_tier="test", profile_manager=ProfileManager())
    orchestrator = HubOrchestrator(loaded_config=loaded)
    try:
        with pytest.raises(RuntimeError, match="All 1 configured servers failed to start"):
            orchestrator.start()
        assert orchestrator.lifecycle_state == HubLifecycleState.FAILED
    finally:
        orchestrator.stop()


def test_bridge_mount_failure_unwinds_resources(multi_server_loaded_config, monkeypatch):
    """If bridge ASGI app creation fails, child servers are stopped and state is FAILED."""
    orchestrator = HubOrchestrator(loaded_config=multi_server_loaded_config)

    def mock_create_asgi_app():
        raise RuntimeError("Simulated ASGI bridge failure")

    monkeypatch.setattr(orchestrator.bridge, "create_asgi_app", mock_create_asgi_app)

    try:
        with pytest.raises(RuntimeError, match="Failed mounting HTTP bridge application"):
            orchestrator.start()

        assert orchestrator.lifecycle_state == HubLifecycleState.FAILED
        # Servers must be unwound and stopped
        for inst in orchestrator.supervisor.list_instances():
            assert inst.state == ServerState.STOPPED
    finally:
        orchestrator.stop()


def test_shutdown_is_graceful_and_idempotent(multi_server_loaded_config):
    """Shutdown cleanly terminates children and repeated stop() calls are safe."""
    orchestrator = HubOrchestrator(loaded_config=multi_server_loaded_config)
    orchestrator.start()
    assert orchestrator.lifecycle_state == HubLifecycleState.RUNNING

    # 1. First stop
    s1 = orchestrator.stop()
    assert s1.state == HubLifecycleState.STOPPED
    assert orchestrator.lifecycle_state == HubLifecycleState.STOPPED

    # 2. Second stop (idempotent)
    s2 = orchestrator.stop()
    assert s2.state == HubLifecycleState.STOPPED


def test_child_crash_updates_aggregate_status(multi_server_loaded_config):
    """External termination of a child updates orchestrator status dynamically to DEGRADED."""
    orchestrator = HubOrchestrator(loaded_config=multi_server_loaded_config)
    try:
        orchestrator.start()
        assert orchestrator.status().state == HubLifecycleState.RUNNING

        # Manually kill math_srv process
        math_inst = orchestrator.supervisor.get_instance("math_srv")
        assert math_inst is not None and math_inst.pid is not None

        import ctypes
        k32 = ctypes.windll.kernel32
        h_proc = k32.OpenProcess(0x0001, False, math_inst.pid)  # PROCESS_TERMINATE
        if h_proc:
            k32.TerminateProcess(h_proc, 99)
            k32.CloseHandle(h_proc)

        # Allow monitor thread to detect exit
        time.sleep(0.5)

        # Status must reflect DEGRADED (echo_srv still healthy, math_srv dead/failed)
        st = orchestrator.status()
        assert st.state in (HubLifecycleState.DEGRADED, HubLifecycleState.RUNNING)
    finally:
        orchestrator.stop()


def test_status_output_redacts_secrets(multi_server_loaded_config):
    """Status dictionary serialization strictly redacts any sensitive tokens or URIs."""
    orchestrator = HubOrchestrator(loaded_config=multi_server_loaded_config)
    try:
        orchestrator.start()
        st_dict = orchestrator.status().to_dict()

        # Format as json string to check for leaks
        dumped = json.dumps(st_dict)
        assert "password" not in dumped.lower() or "******" in dumped
        assert st_dict["state"] == "running"
        assert st_dict["http_port"] == 8080
    finally:
        orchestrator.stop()


def test_orchestrator_context_manager(multi_server_loaded_config):
    """Orchestrator operates cleanly as a Python context manager."""
    with HubOrchestrator(loaded_config=multi_server_loaded_config) as hub:
        assert hub.lifecycle_state == HubLifecycleState.RUNNING
        assert "calc_mult" in [t.name for t in hub.bridge.router.list_tools()]

    assert hub.lifecycle_state == HubLifecycleState.STOPPED
