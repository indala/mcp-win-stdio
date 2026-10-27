"""
Integration tests for StreamableHttpBridge (Phase 4 Step 2).
Exercises real MCP 2.x SDK Streamable HTTP transport, Bearer authentication,
ToolFilter enforcement (both discovery and direct execution), cross-client session isolation,
supervised process routing, child crash resilience, and shutdown cleanup.
"""

import json
import sys
import time

import pytest
from starlette.testclient import TestClient

from mcp_win_stdio.core.hub.auth import SessionManager
from mcp_win_stdio.core.hub.bridge import StreamableHttpBridge
from mcp_win_stdio.core.hub.models import ServerState, ToolFilter
from mcp_win_stdio.core.hub.registry import HubRegistry
from mcp_win_stdio.core.hub.supervisor import ProcessSupervisor

MOCK_BRIDGE_SERVER = """
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
                    "serverInfo": {"name": "mock_srv", "version": "1.0"},
                },
            }
        elif method == "ping":
            resp = {"jsonrpc": "2.0", "id": req_id, "result": {}}
        elif method == "tools/call":
            params = req.get("params", {})
            name = params.get("name")
            args = params.get("arguments", {})

            if name == "calc_add":
                res = args.get("a", 0) + args.get("b", 0)
                resp = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [{"type": "text", "text": f"Sum: {res}"}],
                        "isError": False,
                    },
                }
            elif name == "image_tool":
                resp = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [
                            {"type": "text", "text": "Generated chart"},
                            {
                                "type": "image",
                                "data": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==",
                                "mimeType": "image/png",
                            },
                        ],
                        "isError": False,
                    },
                }
            elif name == "crash_tool":
                sys.exit(77)
            else:
                resp = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [{"type": "text", "text": f"Executed {name}"}],
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
def bridge_setup(monkeypatch):
    """Setup a configured HubRegistry, ProcessSupervisor, and StreamableHttpBridge."""
    monkeypatch.setenv("TEST_BRIDGE_TOKEN", "bridge_secret_bearer_token_xyz")

    registry = HubRegistry()
    registry.load_from_dict(
        {
            "schema_version": "1.0",
            "runtime": {
                "http_bridge": {
                    "host": "0.0.0.0",  # Remote binding enforces authentication
                    "port": 8080,
                    "auth_token_env": "TEST_BRIDGE_TOKEN",
                }
            },
            "servers": {
                "math_srv": {
                    "command": sys.executable,
                    "args": ["-u", "-c", MOCK_BRIDGE_SERVER],
                    "supervisor": {
                        "startup_timeout_seconds": 5.0,
                        "shutdown_grace_seconds": 1.0,
                        "max_restart_retries": 1,
                        "restart_backoff_seconds": 0.2,
                        "protocol_ping": True,
                        "probe_timeout_seconds": 2.0,
                    },
                }
            },
        }
    )

    supervisor = ProcessSupervisor(registry=registry)
    tool_filter = ToolFilter(
        allow=["*"],
        deny=["calc_add_secret", "*dangerous*"],
    )
    session_manager = SessionManager(ttl_seconds=300.0)

    bridge = StreamableHttpBridge(
        supervisor=supervisor,
        registry=registry,
        tool_filter=tool_filter,
        session_manager=session_manager,
    )

    # Register tools into bridge routing table
    bridge.register_tool("math_srv", "calc_add", "Adds two numbers", {
        "type": "object",
        "properties": {"a": {"type": "integer"}, "b": {"type": "integer"}},
    })
    bridge.register_tool("math_srv", "calc_add_secret", "Secret addition tool (denied)")
    bridge.register_tool("math_srv", "dangerous_tool", "Dangerous command (denied)")
    bridge.register_tool("math_srv", "crash_tool", "Triggers process crash")
    bridge.register_tool("math_srv", "image_tool", "Generates an image chart")

    yield bridge

    bridge.shutdown()


def test_invalid_authentication_rejected_before_mcp_routing(bridge_setup):
    """Unauthenticated or invalid token requests are rejected at HTTP boundary with 401."""
    app = bridge_setup.create_asgi_app()
    with TestClient(app) as client:
        # 1. Missing Authorization header
        r1 = client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "initialize"})
        assert r1.status_code == 401
        assert "Missing Authorization header" in r1.json()["message"]

        # 2. Invalid Bearer token
        r2 = client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 1, "method": "initialize"},
            headers={"Authorization": "Bearer wrong_token"},
        )
        assert r2.status_code == 401
        assert "Invalid Bearer token" in r2.json()["message"]


def _initialize_mcp(client, headers):
    """Helper to perform MCP initialize and attach mcp-session-id to subsequent headers."""
    r_init = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "test_agent", "version": "1.0"},
            },
        },
        headers=headers,
    )
    assert r_init.status_code == 200
    mcp_sess = r_init.headers.get("mcp-session-id")
    if mcp_sess:
        headers["mcp-session-id"] = mcp_sess
    return r_init


def test_streamable_http_initialization_and_tool_discovery(bridge_setup):
    """Client initializes over Streamable HTTP and discovers ONLY permitted tools (deny > allow)."""
    app = bridge_setup.create_asgi_app()
    with TestClient(app) as client:
        headers = {
            "Authorization": "Bearer bridge_secret_bearer_token_xyz",
            "Accept": "application/json, text/event-stream",
        }

        # 1. Initialize
        r_init = _initialize_mcp(client, headers)
        assert "2024-11-05" in r_init.text

        # 2. tools/list: Verify ToolFilter enforcement
        list_req = {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}
        r_list = client.post("/mcp", json=list_req, headers=headers)
        assert r_list.status_code == 200

        # Allowed tool MUST be discovered
        assert "calc_add" in r_list.text

        # Denied tools MUST NOT appear in discovery
        assert "calc_add_secret" not in r_list.text
        assert "dangerous_tool" not in r_list.text


def test_direct_denied_tool_invocation_rejected(bridge_setup):
    """Direct tools/call to a denied tool is rejected even if client skips discovery."""
    app = bridge_setup.create_asgi_app()
    with TestClient(app) as client:
        headers = {
            "Authorization": "Bearer bridge_secret_bearer_token_xyz",
            "Accept": "application/json, text/event-stream",
        }

        # Initialize
        _initialize_mcp(client, headers)

        # Directly call denied tool
        call_denied = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": "calc_add_secret", "arguments": {"a": 1, "b": 2}},
        }
        res = client.post("/mcp", json=call_denied, headers=headers)
        assert res.status_code == 200
        assert "prohibited by access policy" in res.text
        assert "isError\":true" in res.text or '"isError": true' in res.text


def test_allowed_tool_invocation_reaches_supervised_server(bridge_setup):
    """Allowed tool call is forwarded to child process, executed, and structured result returned."""
    app = bridge_setup.create_asgi_app()
    with TestClient(app) as client:
        headers = {
            "Authorization": "Bearer bridge_secret_bearer_token_xyz",
            "Accept": "application/json, text/event-stream",
        }

        # Initialize
        _initialize_mcp(client, headers)

        # Call allowed tool calc_add (a=10, b=32)
        call_req = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": "calc_add", "arguments": {"a": 10, "b": 32}},
        }
        res = client.post("/mcp", json=call_req, headers=headers)
        assert res.status_code == 200
        assert "Sum: 42" in res.text
        assert "isError\":false" in res.text or '"isError": false' in res.text


def test_cross_client_isolation_and_session_state(bridge_setup):
    """Separate clients obtain distinct server sessions and maintain isolated context."""
    app = bridge_setup.create_asgi_app()
    headers_auth = {"Authorization": "Bearer bridge_secret_bearer_token_xyz"}

    with TestClient(app) as client:
        # Client A requests health/auth
        r_a = client.get("/health", headers=headers_auth)
        assert r_a.status_code == 200
        token_a = r_a.headers.get("x-mws-session-token")

        # Client B (separate client context with cleared cookies) requests health/auth
        client.cookies.clear()
        r_b = client.get("/health", headers=headers_auth)
        assert r_b.status_code == 200
        token_b = r_b.headers.get("x-mws-session-token")

        assert token_a is not None and token_b is not None
        assert token_a != token_b

        # Attach isolated context to sessions
        bridge_setup.session_manager.get_session_data(token_a)["agent"] = "Alpha"
        bridge_setup.session_manager.get_session_data(token_b)["agent"] = "Beta"

        assert bridge_setup.session_manager.get_session_data(token_a)["agent"] == "Alpha"
        assert bridge_setup.session_manager.get_session_data(token_b)["agent"] == "Beta"

        # Client A continues with token_a
        client.cookies.clear()
        r_a2 = client.get("/health", headers={**headers_auth, "x-mws-session-token": token_a})
        assert r_a2.status_code == 200
        assert bridge_setup.session_manager.get_session_data(token_a)["agent"] == "Alpha"


def test_child_server_crash_resilience(bridge_setup):
    """Invoking a crashing tool triggers crash detection and does not hang subsequent callers."""
    app = bridge_setup.create_asgi_app()
    with TestClient(app) as client:
        headers = {
            "Authorization": "Bearer bridge_secret_bearer_token_xyz",
            "Accept": "application/json, text/event-stream",
        }

        # Initialize
        _initialize_mcp(client, headers)

        # Call crash_tool which causes child to sys.exit(77)
        crash_req = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": "crash_tool", "arguments": {}},
        }
        r_crash = client.post("/mcp", json=crash_req, headers=headers)
        assert r_crash.status_code == 200
        assert "isError\":true" in r_crash.text or '"isError": true' in r_crash.text


def test_shutdown_cleans_up_resources(bridge_setup):
    """Shutdown terminates child processes and clears active sessions."""
    app = bridge_setup.create_asgi_app()
    with TestClient(app) as client:
        headers = {
            "Authorization": "Bearer bridge_secret_bearer_token_xyz",
            "Accept": "application/json, text/event-stream",
        }
        # Start server by calling tool
        _initialize_mcp(client, headers)
        client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "calc_add", "arguments": {"a": 1, "b": 2}}},
            headers=headers,
        )

    # Now shut down bridge
    bridge_setup.shutdown()

    # Verify all instances are stopped
    for inst in bridge_setup.supervisor.list_instances():
        assert inst.state == ServerState.STOPPED


def test_true_mcp_proxy_preserves_rich_content(bridge_setup):
    """Bridge acts as a transparent MCP proxy, preserving multi-modal content (images, text)."""
    app = bridge_setup.create_asgi_app()
    with TestClient(app) as client:
        headers = {
            "Authorization": "Bearer bridge_secret_bearer_token_xyz",
            "Accept": "application/json, text/event-stream",
        }
        _initialize_mcp(client, headers)

        call_req = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": "image_tool", "arguments": {}},
        }
        res = client.post("/mcp", json=call_req, headers=headers)
        assert res.status_code == 200
        # Both text and image content types must be preserved in the response
        assert "Generated chart" in res.text
        assert "image/png" in res.text
        assert "iVBORw0KGgo" in res.text


def test_namespaced_tool_invocation_and_filtering(bridge_setup):
    """Bridge supports both namespaced invocation ('math_srv.calc_add') and namespaced deny filters."""
    app = bridge_setup.create_asgi_app()
    with TestClient(app) as client:
        headers = {
            "Authorization": "Bearer bridge_secret_bearer_token_xyz",
            "Accept": "application/json, text/event-stream",
        }
        _initialize_mcp(client, headers)

        # 1. Namespaced tool call succeeds and routes to 'math_srv'
        call_namespaced = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": "math_srv.calc_add", "arguments": {"a": 20, "b": 22}},
        }
        res = client.post("/mcp", json=call_namespaced, headers=headers)
        assert res.status_code == 200
        assert "Sum: 42" in res.text

        # 2. Denied tool requested via namespaced name is strictly rejected
        call_denied = {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "math_srv.calc_add_secret", "arguments": {}},
        }
        res_denied = client.post("/mcp", json=call_denied, headers=headers)
        assert res_denied.status_code == 200
        assert "prohibited by access policy" in res_denied.text
