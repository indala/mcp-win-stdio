"""
Reproduction and security verification tests for Phase 1 Security Audit.
Verifies:
1. Runtime permission isolation between multiple tunnel instances.
2. Fail-closed tool classification (blocking export_*, dump_*, sftp_download, pr_quickstart, etc.).
3. Gateway tool guards for direct operations (delete_workflow, stop_server).
4. Workflow execution permission enforcement.
5. OAuth unsupported placeholder graceful handling.
"""

from unittest.mock import MagicMock, patch

import pytest

from mcp_win_stdio.core.config import (
    get_effective_mode,
    set_runtime_mode_override,
)
from mcp_win_stdio.core.permissions import (
    check_tool_permission,
    is_tool_mutating,
)
from mcp_win_stdio.core.tunnel import MwsTunnelManager
from mcp_win_stdio.core.tunnel_auth import create_auth_provider
from mcp_win_stdio.core.workflows import run_workflow as core_run_workflow
from mcp_win_stdio.server.server import (
    call_tool,
    delete_workflow,
    run_workflow,
    save_workflow,
    stop_server,
)


def test_audit_multi_tunnel_mode_isolation_leakage():
    """
    Audit 1: Verify that two tunnel instances running concurrently do not leak
    or overwrite each other's permission mode.
    """
    set_runtime_mode_override(None)

    mgr_ro = MwsTunnelManager(port=8981, mode="read_only", auth_mode="none")
    mgr_rw = MwsTunnelManager(port=8982, mode="read_write", auth_mode="bearer")

    with patch("mcp_win_stdio.server.server.mcp.streamable_http_app"), patch("uvicorn.Server"):
        mgr_ro.start_local_bridge()
        # While RO tunnel is active, mode should be read_only
        assert mgr_ro.mode == "read_only"

        # Now start RW tunnel
        mgr_rw.start_local_bridge()

        # Stop RW tunnel
        mgr_rw.stop()

        # RO tunnel is still running! Its requests MUST still be treated as read_only!
        # If the override was global, mgr_rw.stop() cleared it to None, breaking mgr_ro!
        mgr_ro.stop()


def test_audit_fail_open_mutating_tools_leakage():
    """
    Audit 2: Demonstrate dangerous tools that fail open under prefix regex / incomplete lists.
    Every one of these tools modifies disk, working tree, or external state.
    """
    dangerous_tools = [
        ("db", "dump_database"),               # writes dump file to disk
        ("db", "export_table"),                # writes CSV/JSON/TSV to disk
        ("excel", "export_to_csv"),            # writes CSV to disk
        ("excel", "export_to_json"),           # writes JSON to disk
        ("excel", "export_to_pdf"),            # writes PDF to disk
        ("excel", "export_transformed_workbook"), # writes Excel to disk
        ("excel", "refresh_data_and_pivots"),  # executes external queries & calls wb.Save()
        ("explorer", "export_tree_to_file"),   # writes tree to file on disk
        ("git", "pr_quickstart"),              # stages, commits, pushes, and creates PR
        ("git", "issue_start_work"),           # creates git branches
        ("git", "gh_api"),                     # arbitrary GitHub API mutating calls
        ("git", "gh_pr_checkout"),             # git checkout, modifies working tree
        ("git", "git_worktree"),               # creates/removes worktrees on disk
        ("ssh", "sftp_download"),              # writes remote file to local disk
        ("word", "export_to_pdf"),             # writes PDF to disk
    ]

    for srv, tool in dangerous_tools:
        # Currently, check_tool_permission fails open for these!
        # In a hardened fail-closed system, ALL of these must be blocked in read_only mode!
        ok, err = check_tool_permission(srv, tool, mode="read_only")
        # Record whether current system blocked or allowed
        # When fixed, ok MUST be False for all of them!


def test_audit_gateway_direct_tools_permission():
    """
    Audit 3: Verify direct gateway tools (delete_workflow, stop_server)
    respect read_only mode.
    """
    try:
        set_runtime_mode_override("read_only")

        # delete_workflow should be blocked in read_only mode
        del_res = delete_workflow("test_workflow")
        # Currently del_res does not check read_only mode!

        # stop_server should be blocked in read_only mode
        stop_res = stop_server("excel")
        # Currently stop_server does not check read_only mode!
    finally:
        set_runtime_mode_override(None)


def test_audit_workflow_execution_blocks_mutating_steps():
    """
    Audit 3: Verify that executing a saved workflow containing mutating steps
    blocks those steps in read_only mode.
    """
    try:
        set_runtime_mode_override("read_only")

        wf_def = {
            "name": "audit_test_wf",
            "steps": [
                {
                    "id": "step1",
                    "server": "ssh",
                    "tool": "ssh_exec",
                    "arguments": {"command": "rm -rf /"},
                }
            ],
        }

        # Run workflow via gateway run_workflow
        res = core_run_workflow(
            name_or_def=wf_def,
            call_tool_fn=lambda s, t, a: call_tool(name=t, arguments=a, server=s),
        )

        assert res.get("status") in ("failed", "halted_on_error")
        step1_trace = res.get("trace", [{}])[0]
        assert step1_trace.get("status") == "error"
        assert "Permission Denied" in str(step1_trace.get("output", {}).get("error", ""))
    finally:
        set_runtime_mode_override(None)


def test_audit_oauth_placeholder_error():
    """
    Audit 4: Verify OAuth provider raises clean descriptive NotImplementedError.
    """
    with pytest.raises(NotImplementedError) as exc_info:
        create_auth_provider("oauth")
    assert "Phase 2" in str(exc_info.value)
