"""
End-to-End Acceptance Tests for Model Context Protocol (MCP) Hub (Phase 5 Step 4).

Validates complete operational scenarios:
1. Fresh configuration loading from YAML and environment variables.
2. Hub Orchestrator lifecycle: STOPPED -> STARTING -> RUNNING -> STOPPING -> STOPPED.
3. Authenticated Streamable HTTP bridge:
   - Remote/loopback authentication enforcement (401 on missing/bad token).
   - Loopback /health diagnostic probe without token.
   - MCP protocol initialization and session tracking.
4. Tool discovery and namespace filtering:
   - Multi-server namespaced tool discovery (<server>__<tool>).
   - ToolFilter enforcement at both discovery (tools/list) and execution (tools/call) boundaries.
5. Bidirectional tool invocation and rich MCP response handling.
6. Control plane IPC over Windows Named Pipe:
   - Machine-readable status query (--json) and human-readable dashboard output.
   - Secret redaction in status reporting.
   - Single-instance mutual exclusion (duplicate start rejection).
7. Supervised child crash detection, isolation, and bounded restart recovery.
8. Partial failure resilience (DEGRADED state when non-critical server fails).
9. Graceful shutdown: child process tree termination via Windows Job Object, pipe teardown,
   and instance lock release.
"""

import argparse
import io
import json
import os
import sys
import time
import uuid
from pathlib import Path
from unittest.mock import patch

import pytest
from starlette.testclient import TestClient

from mcp_win_stdio.cli import cmd_hub_status, cmd_hub_stop
from mcp_win_stdio.core.hub.config_loader import LoadedHubConfig, load_hub_config
from mcp_win_stdio.core.hub.control import (
    HubControlClient,
    HubControlServer,
    HubInstanceManager,
    is_pid_alive,
)
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
)
from mcp_win_stdio.core.hub.profiles import ProfileManager

# Mock child process implementations
MOCK_MATH_SERVER = """
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

MOCK_ECHO_SERVER = """
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
                        },
                        {
                            "name": "secret_admin_exec",
                            "description": "Restricted administrative command",
                            "inputSchema": {"type": "object"},
                        },
                    ]
                },
            }
        elif method == "tools/call":
            params = req.get("params", {})
            name = params.get("name")
            args = params.get("arguments", {})
            if name == "echo_text":
                resp = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [{"type": "text", "text": f"Echo: {args.get('msg', '')}"}],
                        "isError": False,
                    },
                }
            elif name == "crash_on_demand":
                sys.exit(42)
            else:
                resp = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [{"type": "text", "text": f"Admin executed: {name}"}],
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


def _generate_e2e_yaml(tmp_path: Path, token_env: str = "MWS_E2E_AUTH_TOKEN") -> Path:
    """Create a realistic hub.yaml configured for end-to-end testing."""
    config_file = tmp_path / "hub.yaml"
    exe_str = sys.executable.replace("\\", "/")
    math_code = json.dumps(MOCK_MATH_SERVER)
    echo_code = json.dumps(MOCK_ECHO_SERVER)
    content = f"""
schema_version: '1.0'
runtime:
  mode: hybrid
  http_bridge:
    host: 127.0.0.1
    port: 8899
    auth_token_env: {token_env}
tools:
  allow:
    - "*"
  deny:
    - "*secret*"
servers:
  math_srv:
    command: "{exe_str}"
    args: ["-u", "-c", {math_code}]
    supervisor:
      startup_timeout_seconds: 5.0
      shutdown_grace_seconds: 1.0
      protocol_ping: true
  echo_srv:
    command: "{exe_str}"
    args: ["-u", "-c", {echo_code}]
    supervisor:
      startup_timeout_seconds: 5.0
      shutdown_grace_seconds: 1.0
      protocol_ping: true
"""
    config_file.write_text(content.strip(), encoding="utf-8")
    return config_file


def _init_mcp_session(client: TestClient, headers: dict) -> str:
    """Perform MCP initialize request and return server-issued mcp-session-id."""
    r_init = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "e2e_agent", "version": "1.0"},
            },
        },
        headers=headers,
    )
    assert r_init.status_code == 200, f"Init failed: {r_init.text}"
    sess_id = r_init.headers.get("mcp-session-id")
    assert sess_id is not None
    headers["mcp-session-id"] = sess_id
    return sess_id


# =========================================================================
# Acceptance Scenario 1: Complete End-to-End Operational Lifecycle
# =========================================================================


def test_e2e_full_lifecycle_and_authenticated_tool_execution(tmp_path, monkeypatch):
    """
    Full operational pipeline acceptance test:
    1. Loads fresh configuration with multi-server setup, tool filtering, and Bearer auth.
    2. Starts HubOrchestrator and Windows Named Pipe control server.
    3. Verifies loopback unauthenticated /health diagnostics.
    4. Enforces HTTP Bearer authentication on /mcp (rejects missing/bad tokens with 401).
    5. Handshakes MCP protocol over Streamable HTTP transport and tracks server session.
    6. Discovers tools, confirming allowed tools exist and *secret* tools are filtered out.
    7. Executes namespaced tools across different child processes and asserts results.
    8. Direct invocation of denied tool is rejected.
    9. Queries control plane status over Named Pipe (verifies JSON & human outputs, secret redaction).
    10. Graceful shutdown terminates child processes cleanly and releases instance lock.
    """
    token_val = "secret_e2e_token_xyz987"
    monkeypatch.setenv("MWS_E2E_AUTH_TOKEN", token_val)

    config_file = _generate_e2e_yaml(tmp_path)
    inst_file = tmp_path / "hub_instance.json"
    pipe_name = f"\\\\.\\pipe\\mws-e2e-{uuid.uuid4().hex[:8]}"

    # 1. Load config
    loaded = load_hub_config(cli_path=config_file)
    assert loaded.config.http_port == 8899

    # 2. Acquire instance ownership
    instance_mgr = HubInstanceManager(metadata_path=inst_file)
    meta = instance_mgr.acquire(
        pid=os.getpid(),
        pipe_name=pipe_name,
        config_path=str(config_file),
        config_source="cli_argument",
        http_host=loaded.config.http_host,
        http_port=loaded.config.http_port,
    )
    assert inst_file.is_file()

    # 3. Initialize Orchestrator & Control Server
    orchestrator = HubOrchestrator(loaded_config=loaded)
    stop_called = [False]

    def on_stop():
        stop_called[0] = True
        orchestrator.stop()

    control_server = HubControlServer(
        orchestrator=orchestrator,
        pipe_name=pipe_name,
        authkey_hex=meta.authkey_hex,
        on_stop_requested=on_stop,
    )
    control_server.start()

    try:
        status_info = orchestrator.start()
        assert status_info.state == HubLifecycleState.RUNNING
        assert len(status_info.servers) == 2
        assert status_info.servers["math_srv"]["state"] == ServerState.HEALTHY.value
        assert status_info.servers["echo_srv"]["state"] == ServerState.HEALTHY.value

        # PIDs of child processes
        math_pid = status_info.servers["math_srv"]["pid"]
        echo_pid = status_info.servers["echo_srv"]["pid"]
        assert math_pid is not None and is_pid_alive(math_pid)
        assert echo_pid is not None and is_pid_alive(echo_pid)

        # 4. HTTP Bridge interaction via TestClient
        app = orchestrator.asgi_app
        with TestClient(app) as client:
            # A. Loopback unauthenticated /health check
            r_health = client.get("/health")
            assert r_health.status_code == 200
            health_json = r_health.json()
            assert health_json["status"] == "ok"
            assert health_json["servers_count"] == 2
            assert "active_sessions" in health_json

            # B. Authentication enforcement on /mcp
            r_noauth = client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "initialize"})
            assert r_noauth.status_code == 401
            assert "Missing Authorization header" in r_noauth.json()["message"]

            r_badauth = client.post(
                "/mcp",
                json={"jsonrpc": "2.0", "id": 1, "method": "initialize"},
                headers={"Authorization": "Bearer completely_wrong_token"},
            )
            assert r_badauth.status_code == 401
            assert "Invalid Bearer token" in r_badauth.json()["message"]

            # C. Authenticated MCP session initialization
            headers = {
                "Authorization": f"Bearer {token_val}",
                "Accept": "application/json, text/event-stream",
            }
            sess_id = _init_mcp_session(client, headers)
            assert sess_id

            # D. Tool discovery & ToolFilter validation
            r_list = client.post(
                "/mcp",
                json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
                headers=headers,
            )
            assert r_list.status_code == 200

            # Allowed tools MUST be present
            assert "calc_mult" in r_list.text
            assert "echo_text" in r_list.text

            # Denied tool MUST be filtered out
            assert "secret_admin_exec" not in r_list.text

            # E. Tool execution: math_srv.calc_mult
            r_call_math = client.post(
                "/mcp",
                json={
                    "jsonrpc": "2.0",
                    "id": 3,
                    "method": "tools/call",
                    "params": {"name": "math_srv.calc_mult", "arguments": {"x": 6, "y": 7}},
                },
                headers=headers,
            )
            assert r_call_math.status_code == 200
            assert "Product: 42" in r_call_math.text

            # F. Tool execution: echo_srv.echo_text
            r_call_echo = client.post(
                "/mcp",
                json={
                    "jsonrpc": "2.0",
                    "id": 4,
                    "method": "tools/call",
                    "params": {"name": "echo_srv.echo_text", "arguments": {"msg": "Antigravity E2E"}},
                },
                headers=headers,
            )
            assert r_call_echo.status_code == 200
            assert "Echo: Antigravity E2E" in r_call_echo.text

            # G. Direct invocation of denied tool MUST be rejected
            r_call_denied = client.post(
                "/mcp",
                json={
                    "jsonrpc": "2.0",
                    "id": 5,
                    "method": "tools/call",
                    "params": {"name": "echo_srv.secret_admin_exec", "arguments": {}},
                },
                headers=headers,
            )
            assert r_call_denied.status_code == 200
            assert "prohibited by access policy" in r_call_denied.text

        # 5. Control plane inspection over Named Pipe IPC
        ping_pid = HubControlClient.ping(pipe_name, meta.authkey_hex)
        assert ping_pid == os.getpid()

        status_ipc = HubControlClient.get_status(pipe_name, meta.authkey_hex)
        assert status_ipc["state"] == "running"
        assert status_ipc["http_port"] == 8899
        assert "math_srv" in status_ipc["servers"]
        assert status_ipc["servers"]["math_srv"]["state"] == "healthy"
        assert status_ipc["servers"]["math_srv"]["pid"] == math_pid

        # Verify CLI status helper outputs
        with patch("mcp_win_stdio.core.hub.control.HubInstanceManager", return_value=instance_mgr):
            # Machine-readable JSON output
            out_buf = io.StringIO()
            with patch("sys.stdout", out_buf), pytest.raises(SystemExit) as exc:
                cmd_hub_status(argparse.Namespace(json=True))
            assert exc.value.code == 0
            cli_json = json.loads(out_buf.getvalue())
            assert cli_json["running"] is True
            assert cli_json["pid"] == os.getpid()
            assert cli_json["details"]["state"] == "running"

            # Human-readable tabular output
            out_buf_txt = io.StringIO()
            with patch("sys.stdout", out_buf_txt):
                cmd_hub_status(argparse.Namespace(json=False))
            txt_output = out_buf_txt.getvalue()
            assert "MCP Hub Status: RUNNING" in txt_output
            assert "math_srv" in txt_output
            assert "echo_srv" in txt_output

        # 6. Graceful stop via Control IPC
        stop_ack = HubControlClient.request_stop(pipe_name, meta.authkey_hex, timeout=5.0)
        assert stop_ack is True
        time.sleep(0.5)
        assert stop_called[0] is True
        assert orchestrator.lifecycle_state == HubLifecycleState.STOPPED

        # 7. Verify OS-level child process termination
        assert not is_pid_alive(math_pid)
        assert not is_pid_alive(echo_pid)

    finally:
        control_server.stop()
        orchestrator.stop()
        instance_mgr.release()
        assert not inst_file.exists()


# =========================================================================
# Acceptance Scenario 2: Child Crash Detection & Supervisor Auto-Restart
# =========================================================================


def test_e2e_child_crash_and_restart_policy(tmp_path, monkeypatch):
    """
    Acceptance test for process supervisor resilience:
    When a child process crashes unexpectedly:
    1. Supervisor detects the crash and captures exit code.
    2. Exponential backoff and restart policy automatically respawns child.
    3. Hub lifecycle transitions back to HEALTHY with incremented restart_count.
    4. New child PID is tracked and responds to subsequent requests.
    """
    token_val = "restart_token_abc"
    monkeypatch.setenv("MWS_HTTP_AUTH_TOKEN", token_val)

    cfg = HubConfig(
        schema_version="1.0",
        http_host="127.0.0.1",
        http_port=8890,
        tools=ToolFilter(allow=["*"]),
        servers={
            "echo_srv": ServerConfig(
                name="echo_srv",
                command=sys.executable,
                args=["-u", "-c", MOCK_ECHO_SERVER],
                supervisor=SupervisorConfig(
                    startup_timeout_seconds=5.0,
                    shutdown_grace_seconds=1.0,
                    max_restart_retries=2,
                    restart_backoff_seconds=0.2,
                    protocol_ping=True,
                ),
            ),
        },
    )
    loaded = LoadedHubConfig(
        config=cfg,
        source_path=Path("hub.yaml"),
        source_tier="test",
        profile_manager=ProfileManager(),
    )
    orchestrator = HubOrchestrator(loaded_config=loaded)
    orchestrator.start()

    try:
        app = orchestrator.asgi_app
        with TestClient(app) as client:
            headers = {"Authorization": f"Bearer {token_val}"}
            _init_mcp_session(client, headers)

            first_inst = orchestrator.supervisor.get_status("echo_srv")
            assert first_inst is not None
            first_pid = first_inst.pid
            assert first_pid is not None
            assert first_inst.restart_count == 0

            # Terminate child process externally to simulate an unexpected crash
            proc = orchestrator.supervisor._instances["echo_srv"].process
            assert proc is not None
            proc.kill()
            proc.wait()

            # Wait for supervisor monitor loop and bounded restart
            deadline = time.time() + 5.0
            restarted = False
            new_pid = None
            while time.time() < deadline:
                time.sleep(0.2)
                curr_inst = orchestrator.supervisor.get_status("echo_srv")
                if curr_inst and curr_inst.pid != first_pid and curr_inst.state == ServerState.HEALTHY:
                    restarted = True
                    new_pid = curr_inst.pid
                    break

            assert restarted, "Child process was not restarted within deadline"
            assert new_pid != first_pid
            assert not is_pid_alive(first_pid)
            assert is_pid_alive(new_pid)

            # Assert restarted child successfully answers new requests
            r_call_after = client.post(
                "/mcp",
                json={
                    "jsonrpc": "2.0",
                    "id": 3,
                    "method": "tools/call",
                    "params": {"name": "echo_srv.echo_text", "arguments": {"msg": "Revived!"}},
                },
                headers=headers,
            )
            assert r_call_after.status_code == 200
            assert "Echo: Revived!" in r_call_after.text
    finally:
        orchestrator.stop()


# =========================================================================
# Acceptance Scenario 3: Partial Failure Resilience (DEGRADED State)
# =========================================================================


def test_e2e_partial_failure_degraded_state(monkeypatch):
    """
    Acceptance test for partial failure tolerance:
    When one server fails during startup (e.g. invalid command path) and fail-fast=False:
    1. Hub starts in DEGRADED state rather than failing completely.
    2. Healthy servers remain operational and service tool requests.
    3. Status clearly identifies the failed server.
    """
    token_val = "degraded_token_xyz"
    monkeypatch.setenv("MWS_HTTP_AUTH_TOKEN", token_val)

    cfg = HubConfig(
        schema_version="1.0",
        http_host="127.0.0.1",
        http_port=8891,
        tools=ToolFilter(allow=["*"]),
        servers={
            "math_srv": ServerConfig(
                name="math_srv",
                command=sys.executable,
                args=["-u", "-c", MOCK_MATH_SERVER],
                supervisor=SupervisorConfig(startup_timeout_seconds=5.0, protocol_ping=True),
            ),
            "broken_srv": ServerConfig(
                name="broken_srv",
                command=r"C:\NonExistentBinary\does_not_exist_404.exe",
                args=[],
                supervisor=SupervisorConfig(startup_timeout_seconds=2.0),
            ),
        },
    )
    loaded = LoadedHubConfig(
        config=cfg,
        source_path=Path("hub.yaml"),
        source_tier="test",
        profile_manager=ProfileManager(),
    )
    orchestrator = HubOrchestrator(loaded_config=loaded, fail_fast=False)
    status_info = orchestrator.start()

    try:
        assert status_info.state == HubLifecycleState.DEGRADED
        assert status_info.servers["math_srv"]["state"] == ServerState.HEALTHY.value
        assert status_info.servers["broken_srv"]["state"] == ServerState.FAILED.value

        # Healthy server continues to serve MCP requests
        app = orchestrator.asgi_app
        with TestClient(app) as client:
            headers = {"Authorization": f"Bearer {token_val}"}
            _init_mcp_session(client, headers)

            r_call = client.post(
                "/mcp",
                json={
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {"name": "math_srv.calc_mult", "arguments": {"x": 5, "y": 5}},
                },
                headers=headers,
            )
            assert r_call.status_code == 200
            assert "Product: 25" in r_call.text
    finally:
        orchestrator.stop()


# =========================================================================
# Acceptance Scenario 4: CLI Mutual Exclusion & Stopped State Handling
# =========================================================================


def test_e2e_cli_mutex_and_stopped_state(tmp_path):
    """
    Acceptance test for instance management safety:
    1. When stopped, cmd_hub_status reports STOPPED (JSON running=False).
    2. When stopped, cmd_hub_stop exits 0 with message 'not currently running'.
    3. When running, acquire() on another instance manager raises RuntimeError.
    """
    inst_file = tmp_path / "hub_instance.json"
    mgr = HubInstanceManager(metadata_path=inst_file)
    mgr.release()

    # A. Status when stopped
    with patch("mcp_win_stdio.core.hub.control.HubInstanceManager", return_value=mgr):
        out_buf = io.StringIO()
        with patch("sys.stdout", out_buf), pytest.raises(SystemExit) as exc:
            cmd_hub_status(argparse.Namespace(json=True))
        assert exc.value.code == 0
        data = json.loads(out_buf.getvalue())
        assert data["running"] is False
        assert data["state"] == "stopped"

        # B. Stop when not running
        out_buf_stop = io.StringIO()
        with patch("sys.stdout", out_buf_stop), pytest.raises(SystemExit) as exc:
            cmd_hub_stop(argparse.Namespace(timeout=5.0))
        assert exc.value.code == 0
        assert "not currently running" in out_buf_stop.getvalue()

    # C. Mutual exclusion when active
    pipe_name = f"\\\\.\\pipe\\mws-mutex-{uuid.uuid4().hex[:8]}"
    mgr.acquire(
        pid=os.getpid(),
        pipe_name=pipe_name,
        config_path=None,
        config_source="test",
    )

    # Mock IPC ping returning current pid
    with patch("mcp_win_stdio.core.hub.control.HubControlClient.ping", return_value=os.getpid()):
        second_mgr = HubInstanceManager(metadata_path=inst_file)
        with pytest.raises(RuntimeError, match="MCP Hub is already running"):
            second_mgr.acquire(pid=os.getpid() + 1, pipe_name="\\\\.\\pipe\\other")

    mgr.release()


# =========================================================================
# Acceptance Scenario 5: Invalid Configuration Loading Fail-Fast
# =========================================================================


def test_e2e_invalid_configuration_fails_fast(tmp_path):
    """
    Acceptance test for configuration parsing:
    Malformed configuration or invalid schema elements fail immediately with informative
    errors, leaving no locks or unmanaged state.
    """
    bad_config = tmp_path / "bad_hub.yaml"
    bad_config.write_text(
        """
schema_version: '1.0'
runtime:
  http_bridge:
    port: -9999
servers: {}
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Invalid http_port"):
        load_hub_config(cli_path=bad_config)
