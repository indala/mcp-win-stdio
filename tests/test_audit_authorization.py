"""
Automated regression tests verifying the two high-priority audit fixes:
1. DAG Workflow request-scoped authorization preservation across executor threads.
2. Capability proxy enforcement (resources/*, prompts/*) at target-server boundary.
"""

from unittest.mock import MagicMock, patch
import pytest

from mcp_win_stdio.core.config import CURRENT_PERMISSION_MODE
from mcp_win_stdio.core.permissions import (
    CURRENT_AUTH_MODE,
    CURRENT_ALLOW_SENSITIVE_READS,
    CURRENT_SCOPE_FILTER,
    ToolScopeFilter,
    UNAUTHENTICATED_RESTRICTED_TOOLS,
    check_capability_permission,
)
from mcp_win_stdio.core.workflows import run_workflow as core_run_workflow
from mcp_win_stdio.server.server import _proxy_server_capability


# =============================================================================
# 1. DAG Workflow Request Authorization Tests
# =============================================================================

def test_dag_workflow_inherits_read_only_permission_ceiling():
    """Verify DAG concurrent steps respect CURRENT_PERMISSION_MODE='read_only' and fail mutating steps."""
    wf_def = {
        "execution": "dag",
        "steps": [
            {
                "id": "step_write",
                "server": "db",
                "tool": "execute_query",
                "arguments": {"sql": "UPDATE users SET active = 1 WHERE id = 1"},
            }
        ],
    }

    # Simulate request-scoped read_only mode set by tunnel middleware
    perm_token = CURRENT_PERMISSION_MODE.set("read_only")
    try:
        from mcp_win_stdio.server.server import call_tool

        def _call_fn(s: str, t: str, a: dict) -> dict:
            return call_tool(name=t, arguments=a, server=s)

        res = core_run_workflow(name_or_def=wf_def, call_tool_fn=_call_fn)
        assert res["status"] in ("completed_with_errors", "halted_on_error")
        step_rec = res["trace"][0]
        assert step_rec["status"] == "error"
        err_msg = str(step_rec["output"])
        assert "Permission Denied" in err_msg or "read_only" in err_msg
    finally:
        CURRENT_PERMISSION_MODE.reset(perm_token)


def test_dag_workflow_inherits_scope_filter():
    """Verify DAG concurrent steps respect CURRENT_SCOPE_FILTER and reject disallowed servers."""
    wf_def = {
        "execution": "dag",
        "steps": [
            {
                "id": "step_excel",
                "server": "excel",
                "tool": "preview_sheet",
                "arguments": {"file_path": "test.xlsx"},
            },
            {
                "id": "step_db",
                "server": "db",
                "tool": "read_query",
                "arguments": {"sql": "SELECT 1"},
            },
        ],
    }

    # Scope restricted only to 'excel'
    scope = ToolScopeFilter(allow_servers={"excel"})
    scope_token = CURRENT_SCOPE_FILTER.set(scope)
    try:
        from mcp_win_stdio.server.server import call_tool

        mock_proc = MagicMock()
        mock_proc.call_tool.return_value = {"status": "ok", "rows": []}

        with patch("mcp_win_stdio.server.server.GLOBAL_POOL.get_or_spawn", return_value=mock_proc):
            def _call_fn(s: str, t: str, a: dict) -> dict:
                return call_tool(name=t, arguments=a, server=s)

            res = core_run_workflow(name_or_def=wf_def, call_tool_fn=_call_fn)

        # step_db must be denied by scope filter
        db_trace = next(s for s in res["trace"] if s["step_id"] == "step_db")
        assert db_trace["status"] == "error"
        assert "Scope Denied" in str(db_trace["output"])
    finally:
        CURRENT_SCOPE_FILTER.reset(scope_token)


def test_dag_workflow_inherits_unauthenticated_sensitive_reads_restriction():
    """Verify DAG steps under CURRENT_AUTH_MODE='none' without sensitive reads deny restricted tools."""
    wf_def = {
        "execution": "dag",
        "steps": [
            {
                "id": "step_sensitive",
                "server": "db",
                "tool": "read_query",
                "arguments": {"sql": "SELECT * FROM users"},
            }
        ],
    }

    auth_token = CURRENT_AUTH_MODE.set("none")
    sens_token = CURRENT_ALLOW_SENSITIVE_READS.set(False)
    try:
        from mcp_win_stdio.server.server import call_tool

        def _call_fn(s: str, t: str, a: dict) -> dict:
            return call_tool(name=t, arguments=a, server=s)

        res = core_run_workflow(name_or_def=wf_def, call_tool_fn=_call_fn)
        assert res["status"] in ("completed_with_errors", "halted_on_error")
        step_rec = res["trace"][0]
        assert step_rec["status"] == "error"
        err_msg = str(step_rec["output"])
        assert "Access Denied" in err_msg
        assert "restricted on unauthenticated public tunnels" in err_msg
    finally:
        CURRENT_AUTH_MODE.reset(auth_token)
        CURRENT_ALLOW_SENSITIVE_READS.reset(sens_token)


def test_dag_workflow_concurrent_isolation_no_context_collision():
    """Verify multiple concurrent DAG steps run simultaneously without context collisions or runtime errors."""
    import time

    wf_def = {
        "execution": "dag",
        "steps": [
            {"id": f"step_{i}", "server": "excel", "tool": "get_workbook_info", "arguments": {"file_path": f"t_{i}.xlsx"}}
            for i in range(6)
        ],
    }

    perm_token = CURRENT_PERMISSION_MODE.set("read_only")
    try:
        def _mock_call(s: str, t: str, a: dict) -> dict:
            time.sleep(0.01)
            # Verify the worker thread observes read_only
            assert CURRENT_PERMISSION_MODE.get() == "read_only"
            return {"status": "ok", "file": a.get("file_path")}

        res = core_run_workflow(name_or_def=wf_def, call_tool_fn=_mock_call)
        assert res["status"] == "success"
        assert res["steps_successful"] == 6
    finally:
        CURRENT_PERMISSION_MODE.reset(perm_token)


# =============================================================================
# 2. Capability Proxy Target-Server Boundary Tests
# =============================================================================

@pytest.mark.parametrize("method", ["resources/read", "prompts/get", "resources/list"])
def test_capability_proxy_blocks_disallowed_server_scope(method):
    """Verify capabilities fail with Scope Error when target server is blocked by allowlist or denylist."""
    # Test 1: Blocked via allowlist
    scope_allow = ToolScopeFilter(allow_servers={"excel"})
    token1 = CURRENT_SCOPE_FILTER.set(scope_allow)
    try:
        with patch("mcp_win_stdio.server.server.GLOBAL_POOL") as mock_pool:
            res = _proxy_server_capability("db", method, {"uri": "schema://users"})
            assert res.get("isError") is True
            assert "Scope Error" in res.get("error", "")
            mock_pool.get_or_spawn.assert_not_called()
    finally:
        CURRENT_SCOPE_FILTER.reset(token1)

    # Test 2: Blocked via denylist
    scope_deny = ToolScopeFilter(disallow_servers={"ssh"})
    token2 = CURRENT_SCOPE_FILTER.set(scope_deny)
    try:
        with patch("mcp_win_stdio.server.server.GLOBAL_POOL") as mock_pool:
            res = _proxy_server_capability("ssh", method, {"name": "deploy_prompt"})
            assert res.get("isError") is True
            assert "Scope Error" in res.get("error", "")
            mock_pool.get_or_spawn.assert_not_called()
    finally:
        CURRENT_SCOPE_FILTER.reset(token2)


# Collect all servers represented in UNAUTHENTICATED_RESTRICTED_TOOLS plus ssh
ALL_SENSITIVE_SERVERS = sorted({s for s, _ in UNAUTHENTICATED_RESTRICTED_TOOLS} | {"ssh"})


@pytest.mark.parametrize("server", ALL_SENSITIVE_SERVERS)
@pytest.mark.parametrize("method", ["resources/read", "prompts/get"])
def test_capability_proxy_unauthenticated_tunnel_blocks_sensitive_servers(server, method):
    """Verify --auth none without allow_sensitive_reads blocks resources/read and prompts/get across all sensitive servers."""
    auth_token = CURRENT_AUTH_MODE.set("none")
    sens_token = CURRENT_ALLOW_SENSITIVE_READS.set(False)
    try:
        with patch("mcp_win_stdio.server.server.GLOBAL_POOL") as mock_pool:
            res = _proxy_server_capability(server, method, {"uri": f"{server}://data"})
            assert res.get("isError") is True
            assert "Access Denied" in res.get("error", "")
            assert "restricted on unauthenticated public tunnels" in res.get("error", "")
            mock_pool.get_or_spawn.assert_not_called()
    finally:
        CURRENT_AUTH_MODE.reset(auth_token)
        CURRENT_ALLOW_SENSITIVE_READS.reset(sens_token)


@pytest.mark.parametrize("server", ALL_SENSITIVE_SERVERS)
@pytest.mark.parametrize("method", ["resources/list", "prompts/list"])
def test_capability_proxy_unauthenticated_tunnel_permits_safe_metadata_discovery(server, method):
    """Verify --auth none permits metadata inspection (resources/list, prompts/list) and reaches the child server."""
    auth_token = CURRENT_AUTH_MODE.set("none")
    sens_token = CURRENT_ALLOW_SENSITIVE_READS.set(False)
    params = {"cursor": None}
    try:
        mock_proc = MagicMock()
        mock_proc.request_capability.return_value = {"status": "ok", "items": []}
        with patch("mcp_win_stdio.server.server.GLOBAL_POOL.get_or_spawn", return_value=mock_proc):
            res = _proxy_server_capability(server, method, params)
            assert res.get("isError") is not True
            mock_proc.request_capability.assert_called_once_with(method, params)
    finally:
        CURRENT_AUTH_MODE.reset(auth_token)
        CURRENT_ALLOW_SENSITIVE_READS.reset(sens_token)


@pytest.mark.parametrize("server", ALL_SENSITIVE_SERVERS)
@pytest.mark.parametrize("method", ["resources/read", "prompts/get"])
def test_capability_proxy_unauthenticated_tunnel_allows_when_explicitly_granted(server, method):
    """Verify --auth none with CURRENT_ALLOW_SENSITIVE_READS=True permits capability reads and reaches the child server."""
    auth_token = CURRENT_AUTH_MODE.set("none")
    sens_token = CURRENT_ALLOW_SENSITIVE_READS.set(True)
    params = {"uri": f"{server}://data"} if method == "resources/read" else {"name": "test_prompt", "arguments": {}}
    try:
        mock_proc = MagicMock()
        mock_proc.request_capability.return_value = {"status": "ok", "contents": []}
        with patch("mcp_win_stdio.server.server.GLOBAL_POOL.get_or_spawn", return_value=mock_proc):
            res = _proxy_server_capability(server, method, params)
            assert res.get("isError") is not True
            mock_proc.request_capability.assert_called_once_with(method, params)
    finally:
        CURRENT_AUTH_MODE.reset(auth_token)
        CURRENT_ALLOW_SENSITIVE_READS.reset(sens_token)
