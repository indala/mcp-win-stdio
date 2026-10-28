"""
Phase 6.2 Audit 2 — Tool Filter Evasion Defense Test Suite.
Deterministically validates:
  1. Case normalization and whitespace resilience across ToolFilter and ToolRouter.
  2. Prevention of casing evasion (e.g. 'CALC_ADD' vs 'calc_add').
  3. Prevention of namespaced deny bypass via unqualified queries ('add' when 'math.*' denied).
  4. Unified allow policy semantics for both unqualified ('tool') and namespaced ('server.tool') rules.
  5. Discovery filtering: tools matching deny rules or omitted from allow rules are hidden from tools/list.
  6. Invocation filtering: direct tools/call for denied tools is rejected with structured MCP error.
  7. Namespace syntax tricks (path separators, double dots, colons, nulls) safely rejected.
  8. Zero information leakage on unknown tool invocations.
  9. Canonical tool name preservation when dispatching to child processes.
"""

import json

import pytest
from mcp.types import Tool
from starlette.testclient import TestClient

from mcp_win_stdio.core.hub.auth import SessionManager
from mcp_win_stdio.core.hub.bridge import StreamableHttpBridge, ToolRouter
from mcp_win_stdio.core.hub.models import ToolFilter
from mcp_win_stdio.core.hub.registry import HubRegistry
from mcp_win_stdio.core.hub.supervisor import ProcessSupervisor

MOCK_AUDIT_FILTER_SERVER = """
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
                    "serverInfo": {"name": "filter_srv", "version": "1.0"},
                },
            }
        elif method == "ping":
            resp = {"jsonrpc": "2.0", "id": req_id, "result": {}}
        elif method == "tools/call":
            params = req.get("params", {})
            name = params.get("name")
            args = params.get("arguments", {})
            resp = {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": f"Executed:{name}:{args.get('val', '')}"}],
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


def test_tool_filter_casing_and_whitespace_normalization():
    """
    Test that ToolFilter evaluates allow/deny rules case-insensitively and tolerates whitespace.
    """
    tf = ToolFilter(
        allow=["*"],
        deny=["calc_secret", "drop_table", "admin_*"],
    )

    # Denied variations of 'calc_secret'
    assert tf.is_tool_allowed("calc_secret") is False
    assert tf.is_tool_allowed("CALC_SECRET") is False
    assert tf.is_tool_allowed("Calc_Secret") is False
    assert tf.is_tool_allowed("  calc_secret  ") is False
    assert tf.is_tool_allowed("  CALC_SECRET  ") is False

    # Denied variations of glob 'admin_*'
    assert tf.is_tool_allowed("admin_reset") is False
    assert tf.is_tool_allowed("ADMIN_RESET") is False
    assert tf.is_tool_allowed("Admin_Reset") is False

    # Allowed tools
    assert tf.is_tool_allowed("calc_add") is True
    assert tf.is_tool_allowed("CALC_ADD") is True
    assert tf.is_tool_allowed("  calc_add  ") is True

    # Empty / None tool names
    assert tf.is_tool_allowed("") is False
    assert tf.is_tool_allowed("   ") is False
    assert tf.is_tool_allowed(None) is False  # type: ignore[arg-type]


def test_tool_filter_namespaced_deny_prevents_unqualified_evasion():
    """
    Verify that when 'math.*' or 'math.drop_data' is denied:
    An unqualified query for 'drop_data' belonging to server 'math' is strictly denied.
    """
    tf = ToolFilter(
        allow=["*"],
        deny=["math.drop_data", "admin.*"],
    )

    # Unqualified query with server context
    assert tf.is_tool_allowed("drop_data", server_name="math") is False
    assert tf.is_tool_allowed("DROP_DATA", server_name="MATH") is False
    assert tf.is_tool_allowed("  drop_data  ", server_name="  math  ") is False

    # Namespaced query with server context
    assert tf.is_tool_allowed("math.drop_data", server_name="math") is False
    assert tf.is_tool_allowed("MATH.DROP_DATA", server_name="math") is False

    # Glob deny on server 'admin.*'
    assert tf.is_tool_allowed("delete_user", server_name="admin") is False
    assert tf.is_tool_allowed("DELETE_USER", server_name="ADMIN") is False

    # Same tool name under different server should be allowed if not denied
    assert tf.is_tool_allowed("drop_data", server_name="analytics") is True


def test_tool_filter_allow_policy_with_namespaced_and_unqualified_rules():
    """
    Validates unified allow policy semantics:
      1. allow: ['math.add'] permits both 'math.add' and 'add' (under math server).
      2. allow: ['add'] permits both 'add' and 'math.add'.
      3. allow: ['math.*'] permits all math tools, denies tools from other servers.
    """
    # 1. Namespaced allow rule
    tf_namespaced = ToolFilter(allow=["math.add"], deny=[])
    assert tf_namespaced.is_tool_allowed("add", server_name="math") is True
    assert tf_namespaced.is_tool_allowed("math.add", server_name="math") is True
    assert tf_namespaced.is_tool_allowed("math.sub", server_name="math") is False
    assert tf_namespaced.is_tool_allowed("add", server_name="other") is False

    # 2. Unqualified allow rule
    tf_unqualified = ToolFilter(allow=["add"], deny=[])
    assert tf_unqualified.is_tool_allowed("add", server_name="math") is True
    assert tf_unqualified.is_tool_allowed("math.add", server_name="math") is True
    assert tf_unqualified.is_tool_allowed("sub", server_name="math") is False

    # 3. Server wildcard allow rule
    tf_wildcard = ToolFilter(allow=["math.*"], deny=[])
    assert tf_wildcard.is_tool_allowed("add", server_name="math") is True
    assert tf_wildcard.is_tool_allowed("sub", server_name="math") is True
    assert tf_wildcard.is_tool_allowed("add", server_name="analytics") is False


def test_tool_filter_deny_overrides_allow_strict_precedence():
    """
    Deny rules must strictly take precedence over allow rules under all combinations.
    """
    tf = ToolFilter(
        allow=["math.*", "calc_*"],
        deny=["math.calc_secret", "*dangerous*"],
    )

    assert tf.is_tool_allowed("calc_add", server_name="math") is True
    assert tf.is_tool_allowed("calc_secret", server_name="math") is False
    assert tf.is_tool_allowed("CALC_SECRET", server_name="MATH") is False
    assert tf.is_tool_allowed("dangerous_op", server_name="math") is False
    assert tf.is_tool_allowed("math.dangerous_op", server_name="math") is False


def test_tool_router_case_insensitivity_and_normalization():
    """
    Tests ToolRouter registration and lookup with varied casing and whitespace.
    """
    router = ToolRouter()
    tool_add = Tool(name="calcAdd", description="Adds numbers", inputSchema={"type": "object"})
    router.register_tool("math_srv", tool_add)

    # Lookup by exact name
    assert router.get_tool("calcAdd") is tool_add
    assert router.get_tool_server("calcAdd") == "math_srv"

    # Lookup by lowercase
    assert router.get_tool("calcadd") is tool_add
    assert router.get_tool_server("calcadd") == "math_srv"

    # Lookup by uppercase
    assert router.get_tool("CALCADD") is tool_add
    assert router.get_tool_server("CALCADD") == "math_srv"

    # Lookup by namespaced with mixed casing
    assert router.get_tool("math_srv.calcAdd") is tool_add
    assert router.get_tool("MATH_SRV.CALCADD") is tool_add
    assert router.get_tool_server("MATH_SRV.CALCADD") == "math_srv"

    # Lookup with surrounding whitespace
    assert router.get_tool("  calcAdd  ") is tool_add
    assert router.get_tool_server("  calcAdd  ") == "math_srv"


def test_tool_router_discovery_and_invocation_filtering():
    """
    Tests that ToolRouter.list_tools() strictly excludes denied tools and
    ToolRouter.is_tool_allowed() rejects bypass attempts.
    """
    router = ToolRouter()
    t1 = Tool(name="read_file", inputSchema={"type": "object"})
    t2 = Tool(name="write_file", inputSchema={"type": "object"})
    t3 = Tool(name="secret_file", inputSchema={"type": "object"})

    router.register_tool("fs_srv", t1)
    router.register_tool("fs_srv", t2)
    router.register_tool("fs_srv", t3)

    tf = ToolFilter(
        allow=["fs_srv.*"],
        deny=["*secret*", "fs_srv.write_file"],
    )

    # Discovery check: only 'read_file' should be visible
    allowed_tools = router.list_tools(tf)
    allowed_names = [t.name for t in allowed_tools]
    assert allowed_names == ["read_file"]
    assert "write_file" not in allowed_names
    assert "secret_file" not in allowed_names

    # Invocation checks
    assert router.is_tool_allowed("read_file", tf) is True
    assert router.is_tool_allowed("fs_srv.read_file", tf) is True
    assert router.is_tool_allowed("READ_FILE", tf) is True

    # Denied checks across all casings
    assert router.is_tool_allowed("write_file", tf) is False
    assert router.is_tool_allowed("WRITE_FILE", tf) is False
    assert router.is_tool_allowed("fs_srv.write_file", tf) is False
    assert router.is_tool_allowed("FS_SRV.WRITE_FILE", tf) is False
    assert router.is_tool_allowed("secret_file", tf) is False
    assert router.is_tool_allowed("SECRET_FILE", tf) is False


def test_boundary_tricks_and_injection_syntax():
    """
    Validates that path separators, colons, double dots, and nulls are cleanly handled.
    """
    router = ToolRouter()
    tool = Tool(name="safe_calc", inputSchema={"type": "object"})
    router.register_tool("math", tool)
    tf = ToolFilter(allow=["*"], deny=["math.safe_calc"])

    # Suspicious syntax should not match or resolve
    assert router.get_tool("math/safe_calc") is None
    assert router.get_tool("math\\safe_calc") is None
    assert router.get_tool("math:safe_calc") is None
    assert router.get_tool("math..safe_calc") is None
    assert router.get_tool("../math/safe_calc") is None
    assert router.get_tool("") is None
    assert router.get_tool("   ") is None
    assert router.get_tool(None) is None  # type: ignore[arg-type]


@pytest.fixture
def filter_test_bridge(monkeypatch, tmp_path):
    """Fixture providing a live StreamableHttpBridge with supervised mock server."""
    monkeypatch.setenv("FILTER_AUDIT_TOKEN", "audit_token_abc_123")
    script = tmp_path / "mock_filter_server.py"
    script.write_text(MOCK_AUDIT_FILTER_SERVER, encoding="utf-8")

    registry = HubRegistry()
    registry.load_from_dict(
        {
            "schema_version": "1.0",
            "runtime": {
                "http_bridge": {
                    "host": "127.0.0.1",
                    "port": 8080,
                    "auth_token_env": "FILTER_AUDIT_TOKEN",
                }
            },
            "servers": {
                "math_srv": {
                    "command": "python",
                    "args": [str(script)],
                    "enabled": True,
                }
            },
        }
    )

    supervisor = ProcessSupervisor(registry=registry, auto_start_monitor=False)
    tool_filter = ToolFilter(
        allow=["math_srv.*"],
        deny=["math_srv.secret_tool", "*dangerous*"],
    )
    session_manager = SessionManager(ttl_seconds=300.0)

    bridge = StreamableHttpBridge(
        supervisor=supervisor,
        registry=registry,
        tool_filter=tool_filter,
        session_manager=session_manager,
    )

    # Register tools
    t_add = Tool(name="calc_add", description="Adds numbers", inputSchema={"type": "object"})
    t_secret = Tool(name="secret_tool", description="Secret operation", inputSchema={"type": "object"})
    t_danger = Tool(name="dangerous_op", description="Dangerous operation", inputSchema={"type": "object"})

    bridge.register_tool("math_srv", t_add.name, t_add.description, t_add.input_schema)
    bridge.register_tool("math_srv", t_secret.name, t_secret.description, t_secret.input_schema)
    bridge.register_tool("math_srv", t_danger.name, t_danger.description, t_danger.input_schema)

    yield bridge

    bridge.shutdown()


def _parse_sse(res_text: str) -> dict:
    """Extract JSON object from SSE message body."""
    for line in res_text.splitlines():
        if line.startswith("data: "):
            return json.loads(line[6:].strip())
    return {}


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


def test_http_discovery_strictly_omits_denied_tools(filter_test_bridge):
    """
    Over Streamable HTTP, tools/list must strictly omit denied tools.
    """
    app = filter_test_bridge.create_asgi_app()
    with TestClient(app) as client:
        headers = {
            "Authorization": "Bearer audit_token_abc_123",
            "Accept": "application/json, text/event-stream",
        }

        # Initialize
        _initialize_mcp(client, headers)

        # Tools List
        list_req = {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}
        res_list = client.post("/mcp", json=list_req, headers=headers)
        assert res_list.status_code == 200
        data = _parse_sse(res_list.text)
        tools = data.get("result", {}).get("tools", [])
        tool_names = [t.get("name") for t in tools]

        assert "calc_add" in tool_names
        assert "secret_tool" not in tool_names
        assert "dangerous_op" not in tool_names


def test_http_direct_invocation_bypass_rejected_with_structured_mcp_error(filter_test_bridge):
    """
    Clients attempting to bypass discovery by calling denied tools directly must receive
    a structured MCP error ('Tool ... is prohibited by access policy') across all casing variations.
    """
    app = filter_test_bridge.create_asgi_app()
    with TestClient(app) as client:
        headers = {
            "Authorization": "Bearer audit_token_abc_123",
            "Accept": "application/json, text/event-stream",
        }

        # Initialize
        _initialize_mcp(client, headers)

        # 1. Direct call for denied tool (lowercase)
        call_req_lower = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": "secret_tool", "arguments": {"val": "1"}},
        }
        res_lower = client.post("/mcp", json=call_req_lower, headers=headers)
        assert res_lower.status_code == 200
        assert "prohibited by access policy" in res_lower.text
        data_lower = _parse_sse(res_lower.text)
        assert data_lower.get("result", {}).get("isError") is True

        # 2. Direct call for denied tool (uppercase evasion attempt)
        call_req_upper = {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "SECRET_TOOL", "arguments": {"val": "2"}},
        }
        res_upper = client.post("/mcp", json=call_req_upper, headers=headers)
        assert res_upper.status_code == 200
        assert "prohibited by access policy" in res_upper.text
        data_upper = _parse_sse(res_upper.text)
        assert data_upper.get("result", {}).get("isError") is True

        # 3. Direct call for namespaced denied tool (mixed case evasion attempt)
        call_req_ns = {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {"name": "Math_Srv.Secret_Tool", "arguments": {"val": "3"}},
        }
        res_ns = client.post("/mcp", json=call_req_ns, headers=headers)
        assert res_ns.status_code == 200
        assert "prohibited by access policy" in res_ns.text
        data_ns = _parse_sse(res_ns.text)
        assert data_ns.get("result", {}).get("isError") is True

        # 4. Direct call for glob-denied tool
        call_req_danger = {
            "jsonrpc": "2.0",
            "id": 5,
            "method": "tools/call",
            "params": {"name": "DANGEROUS_OP", "arguments": {}},
        }
        res_danger = client.post("/mcp", json=call_req_danger, headers=headers)
        assert res_danger.status_code == 200
        assert "prohibited by access policy" in res_danger.text
        data_danger = _parse_sse(res_danger.text)
        assert data_danger.get("result", {}).get("isError") is True


def test_http_unknown_tool_zero_information_leakage(filter_test_bridge):
    """
    Calls for unknown tools or path-injected tool names must return clean structured
    error results without disclosing server configs, script paths, or environment variables.
    """
    app = filter_test_bridge.create_asgi_app()
    with TestClient(app) as client:
        headers = {
            "Authorization": "Bearer audit_token_abc_123",
            "Accept": "application/json, text/event-stream",
        }

        # Initialize
        _initialize_mcp(client, headers)

        for suspicious in [
            "nonexistent_tool",
            "math_srv/calc_add",
            "math_srv\\calc_add",
            "../math_srv/calc_add",
            "math_srv..calc_add",
            "math_srv:calc_add",
        ]:
            call_req = {
                "jsonrpc": "2.0",
                "id": 99,
                "method": "tools/call",
                "params": {"name": suspicious, "arguments": {}},
            }
            res = client.post("/mcp", json=call_req, headers=headers)
            assert res.status_code == 200
            data = _parse_sse(res.text)
            assert data.get("result", {}).get("isError") is True
            # Confirm no internal script paths leaked
            assert "mock_filter_server.py" not in res.text
            assert "audit_token" not in res.text


def test_http_legitimate_casing_resolves_to_canonical_dispatch(filter_test_bridge):
    """
    Legitimate client calling 'CALC_ADD' or 'math_srv.calc_add' successfully resolves
    and dispatches to the supervisor with canonical tool name 'calc_add'.
    """
    app = filter_test_bridge.create_asgi_app()
    with TestClient(app) as client:
        headers = {
            "Authorization": "Bearer audit_token_abc_123",
            "Accept": "application/json, text/event-stream",
        }

        # Initialize
        _initialize_mcp(client, headers)

        # 1. Unqualified with uppercase
        call_upper = {
            "jsonrpc": "2.0",
            "id": 10,
            "method": "tools/call",
            "params": {"name": "CALC_ADD", "arguments": {"val": "100"}},
        }
        res_upper = client.post("/mcp", json=call_upper, headers=headers)
        assert res_upper.status_code == 200
        assert "Executed:calc_add:100" in res_upper.text

        # 2. Namespaced with mixed case
        call_ns = {
            "jsonrpc": "2.0",
            "id": 11,
            "method": "tools/call",
            "params": {"name": "Math_Srv.calc_add", "arguments": {"val": "200"}},
        }
        res_ns = client.post("/mcp", json=call_ns, headers=headers)
        assert res_ns.status_code == 200
        assert "Executed:calc_add:200" in res_ns.text


def test_cross_server_unqualified_name_collision_handling(tmp_path, monkeypatch):
    """
    Check 1: Cross-server collision defense.
    When two servers register tools with identical unqualified names (e.g. 'analyze'),
    unqualified lookup is marked ambiguous to prevent accidental silent execution on the wrong server.
    Namespaced invocation ('math_srv.analyze', 'science_srv.analyze') resolves cleanly.
    """
    router = ToolRouter()
    t_math = Tool(name="analyze", description="Math analysis", input_schema={"type": "object"})
    t_sci = Tool(name="analyze", description="Science analysis", input_schema={"type": "object"})

    router.register_tool("math_srv", t_math)
    router.register_tool("science_srv", t_sci)

    # Unqualified name is ambiguous
    assert router.is_ambiguous_tool("analyze") is True
    assert router.is_ambiguous_tool("ANALYZE") is True
    assert router.resolve_tool("analyze") == (None, None)

    # Namespaced lookups resolve unambiguously
    assert router.resolve_tool("math_srv.analyze") == (t_math, "math_srv")
    assert router.resolve_tool("MATH_SRV.ANALYZE") == (t_math, "math_srv")
    assert router.resolve_tool("science_srv.analyze") == (t_sci, "science_srv")
    assert router.resolve_tool("SCIENCE_SRV.ANALYZE") == (t_sci, "science_srv")

    # In HTTP bridge, calling ambiguous tool returns structured error advising qualification
    monkeypatch.setenv("COLLISION_TOKEN", "collision_secret_123")
    script = tmp_path / "mock_collision.py"
    script.write_text(MOCK_AUDIT_FILTER_SERVER, encoding="utf-8")

    reg = HubRegistry()
    reg.load_from_dict({
        "schema_version": "1.0",
        "runtime": {"http_bridge": {"host": "127.0.0.1", "port": 8080, "auth_token_env": "COLLISION_TOKEN"}},
        "servers": {
            "math_srv": {"command": "python", "args": [str(script)], "enabled": True},
            "science_srv": {"command": "python", "args": [str(script)], "enabled": True},
        },
    })
    sup = ProcessSupervisor(registry=reg, auto_start_monitor=False)
    bridge = StreamableHttpBridge(supervisor=sup, registry=reg, tool_filter=ToolFilter())
    bridge.register_tool("math_srv", t_math.name, t_math.description, t_math.input_schema)
    bridge.register_tool("science_srv", t_sci.name, t_sci.description, t_sci.input_schema)

    try:
        app = bridge.create_asgi_app()
        with TestClient(app) as client:
            headers = {"Authorization": "Bearer collision_secret_123", "Accept": "application/json, text/event-stream"}
            _initialize_mcp(client, headers)

            # Calling unqualified ambiguous tool is safely rejected
            res_ambig = client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "analyze"}}, headers=headers)
            assert res_ambig.status_code == 200
            data_ambig = _parse_sse(res_ambig.text)
            assert data_ambig.get("result", {}).get("isError") is True
            assert "Ambiguous tool 'analyze'" in res_ambig.text

            # Calling namespaced tool succeeds on intended server
            res_math = client.post("/mcp", json={"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "math_srv.analyze", "arguments": {"val": "m"}}}, headers=headers)
            assert res_math.status_code == 200
            assert "Executed:analyze:m" in res_math.text
    finally:
        bridge.shutdown()


def test_wildcard_namespace_combinations_and_empty_entries():
    """
    Check 2: Detailed wildcard, cross-qualification, overlap, and empty-entry semantics.
    """
    # 1. allow: ['math.*'] with deny: ['math.calc_add']
    tf1 = ToolFilter(allow=["math.*"], deny=["math.calc_add"])
    assert tf1.is_tool_allowed("calc_add", server_name="math") is False
    assert tf1.is_tool_allowed("math.calc_add", server_name="math") is False
    assert tf1.is_tool_allowed("calc_sub", server_name="math") is True
    assert tf1.is_tool_allowed("other_tool", server_name="other") is False

    # 2. allow: ['calc_add'] with deny: ['math.*'] (deny strictly overrides allow)
    tf2 = ToolFilter(allow=["calc_add"], deny=["math.*"])
    assert tf2.is_tool_allowed("calc_add", server_name="math") is False
    assert tf2.is_tool_allowed("calc_add", server_name="science") is True

    # 3. Deny rule matching unqualified name while request uses qualified name
    tf3 = ToolFilter(allow=["*"], deny=["drop_table"])
    assert tf3.is_tool_allowed("db.drop_table", server_name="db") is False
    assert tf3.is_tool_allowed("drop_table", server_name="db") is False

    # 4. Deny rule matching qualified name while request uses unqualified name
    tf4 = ToolFilter(allow=["*"], deny=["db.drop_table"])
    assert tf4.is_tool_allowed("drop_table", server_name="db") is False
    assert tf4.is_tool_allowed("drop_table", server_name="other") is True

    # 5. Overlapping server and tool names (e.g. server 'math', tool 'math')
    tf5 = ToolFilter(allow=["*"], deny=["math.*"])
    assert tf5.is_tool_allowed("math", server_name="math") is False  # 'math.math' matches 'math.*'
    assert tf5.is_tool_allowed("math", server_name="science") is True

    # 6. Empty and whitespace-only entries in allow / deny
    tf_empty = ToolFilter(allow=["", "   "], deny=["", "   "])
    # Whitespace-only allow retains default permit semantics (does not deny all)
    assert tf_empty.is_tool_allowed("calc_add", server_name="math") is True
    # Whitespace-only deny is skipped (does not match everything)
    assert tf_empty.is_tool_allowed("calc_sub", server_name="math") is True

    # 7. from_dict cleans empty entries
    tf_from_dict = ToolFilter.from_dict({"allow": ["", "  ", "math.*"], "deny": ["", "   ", "math.secret"]})
    assert tf_from_dict.allow == ["math.*"]
    assert tf_from_dict.deny == ["math.secret"]
    assert tf_from_dict.is_tool_allowed("calc_add", server_name="math") is True
    assert tf_from_dict.is_tool_allowed("secret", server_name="math") is False
