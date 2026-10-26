"""
Unit tests for mws composite workflow engine.
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

from mcp_win_stdio.cli import cmd_workflow
from mcp_win_stdio.core.workflows import (
    delete_workflow,
    list_workflows,
    load_workflow,
    resolve_template_value,
    run_workflow,
    save_workflow,
)


def test_resolve_template_value():
    context = {
        "host": "production-api",
        "port": 8080,
        "steps": {
            "get_users": {
                "status": "success",
                "count": 42,
                "users": [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}],
            }
        },
    }

    # 1. String interpolation
    assert resolve_template_value("Host is {{ host }} on port {{ port }}", context) == "Host is production-api on port 8080"

    # 2. Full object resolution (preserves type)
    users = resolve_template_value("{{ steps.get_users.users }}", context)
    assert isinstance(users, list)
    assert len(users) == 2
    assert users[0]["name"] == "Alice"

    # 3. Numeric resolution
    assert resolve_template_value("{{ steps.get_users.count }}", context) == 42

    # 4. Nested dict & list resolution
    raw_dict = {
        "target": "{{ host }}",
        "items": ["prefix_{{ port }}", "{{ steps.get_users.count }}"],
    }
    resolved_dict = resolve_template_value(raw_dict, context)
    assert resolved_dict["target"] == "production-api"
    assert resolved_dict["items"] == ["prefix_8080", 42]

    # 5. Missing variable kept intact
    assert resolve_template_value("Value {{ missing }}", context) == "Value {{ missing }}"


def test_workflow_lifecycle():
    with tempfile.TemporaryDirectory() as tmpdir:
        proj_root = Path(tmpdir)

        sample_def = {
            "title": "SSH Deployment Pipeline",
            "description": "Builds and deploys application via SSH",
            "parameters": {
                "host": {"type": "string", "default": "staging-01"},
            },
            "steps": [
                {
                    "id": "step_check",
                    "server": "ssh",
                    "tool": "test_host",
                    "arguments": {"host": "{{ host }}"},
                },
                {
                    "id": "step_pull",
                    "server": "ssh",
                    "tool": "ssh_exec",
                    "arguments": {"host": "{{ host }}", "command": "git pull"},
                },
            ],
        }

        # 1. Save workflow in project scope
        res_save = save_workflow("deploy_staging", sample_def, scope="project", project_root=proj_root)
        assert res_save["status"] == "success"
        assert res_save["steps_count"] == 2
        assert Path(res_save["path"]).exists()

        # 2. List workflows
        wfs = list_workflows(project_root=proj_root)
        matched = [w for w in wfs if w["name"] == "deploy_staging"]
        assert len(matched) == 1
        assert matched[0]["steps_count"] == 2
        assert matched[0]["scope"] == "project"

        # 3. Load workflow
        loaded = load_workflow("deploy_staging", project_root=proj_root)
        assert loaded is not None
        assert loaded["title"] == "SSH Deployment Pipeline"
        assert len(loaded["steps"]) == 2

        # 4. Delete workflow
        res_del = delete_workflow("deploy_staging", project_root=proj_root)
        assert res_del["deleted"] is True
        assert not Path(res_save["path"]).exists()


def test_run_workflow_execution_and_piping():
    wf_def = {
        "name": "data_pipeline",
        "parameters": {
            "source_table": {"type": "string", "default": "orders"},
        },
        "steps": [
            {
                "id": "fetch_data",
                "server": "db",
                "tool": "read_query",
                "arguments": {"query": "SELECT * FROM {{ source_table }}"},
                "halt_on_failure": True,
            },
            {
                "id": "export_excel",
                "server": "excel",
                "tool": "create_workbook",
                "arguments": {
                    "source": "{{ steps.fetch_data.rows }}",
                    "title": "Export of {{ source_table }}",
                },
                "halt_on_failure": True,
            },
        ],
    }

    calls = []

    def mock_caller(server: str, tool: str, args: dict):
        calls.append((server, tool, args))
        if tool == "read_query":
            return {"status": "success", "rows": [{"order_id": 101, "amount": 250}]}
        elif tool == "create_workbook":
            return {"status": "success", "file": "orders.xlsx"}
        return {}

    # Run with default parameter
    res = run_workflow(wf_def, call_tool_fn=mock_caller)
    assert res["status"] == "success"
    assert res["steps_completed"] == 2
    assert len(calls) == 2

    # Verify first call received default param
    assert calls[0] == ("db", "read_query", {"query": "SELECT * FROM orders"})

    # Verify second call received piped output from first call
    assert calls[1] == (
        "excel",
        "create_workbook",
        {
            "source": [{"order_id": 101, "amount": 250}],
            "title": "Export of orders",
        },
    )


def test_run_workflow_halt_on_error():
    wf_def = {
        "name": "failing_pipeline",
        "steps": [
            {
                "id": "step1",
                "server": "ssh",
                "tool": "test_host",
                "arguments": {"host": "bad-host"},
                "halt_on_failure": True,
            },
            {
                "id": "step2",
                "server": "ssh",
                "tool": "ssh_exec",
                "arguments": {"command": "echo should not run"},
            },
        ],
    }

    def failing_caller(server: str, tool: str, args: dict):
        if tool == "test_host":
            return {"isError": True, "error": "Connection timed out"}
        return {"status": "success"}

    res = run_workflow(wf_def, call_tool_fn=failing_caller)
    assert res["status"] == "halted_on_error"
    assert res["failed_step"] == "step1"
    assert res["steps_completed"] == 0
    assert len(res["trace"]) == 1
    assert res["trace"][0]["status"] == "error"


def test_cli_workflow_commands(capsys):
    with tempfile.TemporaryDirectory() as tmpdir:
        proj_root = Path(tmpdir)
        save_workflow(
            "cli_test_wf",
            {
                "title": "CLI Test Workflow",
                "steps": [{"server": "tsc", "tool": "get_error_summary"}],
            },
            scope="project",
            project_root=proj_root,
        )

        # Mock args for list
        args_list = MagicMock()
        args_list.wf_action = "list"
        args_list.wf_name = None

        import os
        old_cwd = os.getcwd()
        try:
            os.chdir(tmpdir)
            cmd_workflow(args_list)
            captured = capsys.readouterr().out
            assert "cli_test_wf" in captured
            assert "CLI Test Workflow" in captured

            # Test view
            args_view = MagicMock()
            args_view.wf_action = "view"
            args_view.wf_name = "cli_test_wf"
            cmd_workflow(args_view)
            captured_view = capsys.readouterr().out
            parsed = json.loads(captured_view)
            assert parsed["title"] == "CLI Test Workflow"

            # Test delete
            args_del = MagicMock()
            args_del.wf_action = "delete"
            args_del.wf_name = "cli_test_wf"
            cmd_workflow(args_del)
            captured_del = capsys.readouterr().out
            assert "deleted" in captured_del.lower()
        finally:
            os.chdir(old_cwd)


def test_workflow_dry_run_and_output_piping():
    wf_def = {
        "title": "Build and Deploy",
        "parameters": {"env": {"type": "string", "default": "staging"}},
        "steps": [
            {
                "id": "get_sha",
                "server": "git",
                "tool": "git_log",
                "arguments": {"limit": 1},
            },
            {
                "id": "deploy",
                "server": "ssh",
                "tool": "ssh_exec",
                "arguments": {
                    "command": "deploy.sh --env {{ env }} --commit {{ steps.get_sha.output.sha }}"
                },
            },
        ],
    }

    # 1. Test dry_run execution
    dry_res = run_workflow(wf_def, parameters={"env": "production"}, dry_run=True)
    assert dry_res["status"] == "dry_run_plan"
    assert dry_res["dry_run"] is True
    assert len(dry_res["plan"]) == 2
    assert "deploy.sh --env production" in dry_res["plan"][1]["resolved_arguments"]["command"]
    assert "<unresolved_runtime_output: steps.get_sha.output.sha>" in dry_res["plan"][1]["resolved_arguments"]["command"]

    # 2. Test actual piping with mock caller
    def mock_caller(server, tool, args):
        if tool == "git_log":
            return {"sha": "c0ffee123", "author": "developer"}
        if tool == "ssh_exec":
            return {"stdout": f"Successfully executed {args['command']}"}
        return {}

    run_res = run_workflow(wf_def, parameters={"env": "prod"}, call_tool_fn=mock_caller)
    assert run_res["status"] == "success"
    assert len(run_res["trace"]) == 2
    # Check that {{ steps.get_sha.output.sha }} resolved to c0ffee123
    assert "deploy.sh --env prod --commit c0ffee123" in run_res["trace"][1]["output"]["stdout"]


def test_workflow_error_handling_and_recovery():
    # Test on_failure recovery step and continue_on_error
    wf_def = {
        "title": "Fault Tolerant Workflow",
        "steps": [
            {
                "id": "step_fail",
                "server": "db",
                "tool": "read_query",
                "arguments": {"query": "SELECT * FROM missing_table"},
                "continue_on_error": True,
                "on_failure": {
                    "server": "db",
                    "tool": "read_query",
                    "arguments": {"query": "SELECT 'recovered' as status"},
                },
            },
            {
                "id": "step_followup",
                "server": "explorer",
                "tool": "workspace_summary",
                "arguments": {"path": "."},
            },
        ],
    }

    def mock_caller(server, tool, args):
        if "missing_table" in args.get("query", ""):
            return {"isError": True, "error": "relation missing_table does not exist"}
        if "recovered" in args.get("query", ""):
            return {"status": "success", "recovered": True}
        return {"summary": "workspace ok"}

    res = run_workflow(wf_def, call_tool_fn=mock_caller)
    assert res["status"] == "completed_with_errors"
    assert len(res["trace"]) == 2
    assert res["trace"][0]["status"] == "error"
    assert "recovery" in res["trace"][0]
    assert res["trace"][0]["recovery"]["status"] == "success"
    assert res["trace"][1]["status"] == "success"

