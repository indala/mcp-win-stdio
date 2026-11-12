"""
Comprehensive Unit Tests for Audit Logging, Preflight Validation, and Artifact Spilling.
"""

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from mcp_win_stdio.core.artifacts import (
    maybe_spill_to_artifact,
    prune_expired_artifacts,
    read_artifact_payload,
    write_artifact_atomically,
)
from mcp_win_stdio.core.audit import AUDIT_LOG_FILE, log_audit_event, redact_secrets
from mcp_win_stdio.core.workflows import validate_workflow_preflight


def test_redact_secrets():
    """Verify secrets and connection strings are masked cleanly."""
    uri = "postgresql://myuser:super_secret_pwd@127.0.0.1:5432/mydb"
    masked = redact_secrets(uri)
    assert "super_secret_pwd" not in masked
    assert "******" in masked

    args = {
        "password": "mypassword123",
        "api_key": "sk-1234567890",
        "token": "tok_abcdef",
        "nested": {"secret": "nested_secret_val"},
        "normal": "hello",
    }
    redacted = redact_secrets(args)
    assert redacted["password"] == "******"
    assert redacted["api_key"] == "******"
    assert redacted["token"] == "******"
    assert redacted["nested"]["secret"] == "******"
    assert redacted["normal"] == "hello"


def test_audit_logging(tmp_path):
    """Verify log_audit_event writes valid JSONL records."""
    log_audit_event(
        event_type="tool_call",
        server="db",
        tool="read_query",
        duration_ms=25.4,
        status="success",
        arguments={"sql": "SELECT 1;", "password": "sensitive_pwd"},
        session_id="test_sess_1",
    )
    assert AUDIT_LOG_FILE.exists()
    lines = AUDIT_LOG_FILE.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) > 0
    last_record = json.loads(lines[-1])
    assert last_record["server"] == "db"
    assert last_record["tool"] == "read_query"
    assert last_record["status"] == "success"
    assert last_record["arg_summary"]["password"] == "******"


def test_workflow_preflight_schema_and_ordering():
    """Verify preflight validator catches out-of-order references, undeclared params, and schema mismatches."""
    # 1. Invalid step ordering (step 1 references step 2 before it runs)
    wf_invalid_order = {
        "name": "bad_order",
        "steps": [
            {
                "id": "step1",
                "server": "ssh",
                "tool": "ssh_exec",
                "arguments": {"command": "echo {{ steps.step2.output }}"},
            },
            {
                "id": "step2",
                "server": "ssh",
                "tool": "ssh_exec",
                "arguments": {"command": "ls -la"},
            },
        ],
    }
    errors = validate_workflow_preflight(wf_invalid_order)
    assert len(errors) > 0
    assert any(e["type"] == "invalid_step_dependency" for e in errors)
    assert "before 'step2' has executed" in str(errors)

    # 2. Template-aware skip: valid workflow with dynamic template should pass
    wf_valid_with_templates = {
        "name": "valid_chain",
        "parameters": {
            "target_host": {"default": "dev-host"},
        },
        "steps": [
            {
                "id": "step1",
                "server": "ssh",
                "tool": "ssh_exec",
                "arguments": {"command": "echo 123", "host": "{{ target_host }}"},
            },
            {
                "id": "step2",
                "server": "ssh",
                "tool": "ssh_exec",
                "arguments": {"command": "echo {{ steps.step1.output }}", "host": "{{ target_host }}"},
            },
        ],
    }
    errors_valid = validate_workflow_preflight(wf_valid_with_templates)
    assert len(errors_valid) == 0


def test_artifact_spilling_and_pagination():
    """Verify large payloads spill to disk, preserve bounded previews, and support read_artifact."""
    # 1. Small payload -> never spilled
    small_data = {"status": "success", "rows": [{"id": 1, "name": "small"}]}
    spilled, res = maybe_spill_to_artifact(small_data, threshold_bytes=1000)
    assert spilled is False
    assert res == small_data

    # 2. Error payload -> NEVER spilled
    err_data = {"isError": True, "error": "Huge error " * 500}
    spilled_err, res_err = maybe_spill_to_artifact(err_data, threshold_bytes=100)
    assert spilled_err is False

    # 3. Large successful payload -> spilled with preview and artifact handle
    large_rows = [{"id": i, "val": f"data_{i}" * 50} for i in range(200)]
    large_data = {"status": "success", "rows": large_rows}
    spilled, stub = maybe_spill_to_artifact(large_data, threshold_bytes=1024)
    assert spilled is True
    assert "_artifact" in stub
    handle = stub["_artifact"]["handle"]
    assert handle.startswith("art_")
    assert stub["_artifact"]["total_items"] == 200
    assert len(stub["_artifact"]["preview"]["rows"]) <= 5

    # 4. Safe pagination via read_artifact_payload
    page1 = read_artifact_payload(handle=handle, offset=0, limit=10)
    assert page1["returned_items"] == 10
    assert page1["has_more"] is True
    assert page1["items"][0]["id"] == 0

    page2 = read_artifact_payload(handle=handle, offset=10, limit=10)
    assert page2["items"][0]["id"] == 10

    # 5. Query filtering
    filtered = read_artifact_payload(handle=handle, query="data_42")
    assert filtered["matched_items"] == 1
    assert filtered["items"][0]["id"] == 42

    # 6. Path traversal rejection
    malicious = read_artifact_payload(handle="../../secret")
    assert malicious.get("isError") is True
    assert "Invalid artifact handle" in malicious["error"]

    # 7. MCP capability collections retain useful previews and pagination
    resource_data = {"resources": [{"uri": f"file://{i}", "description": "x" * 100} for i in range(20)]}
    resource_spilled, resource_stub = maybe_spill_to_artifact(resource_data, threshold_bytes=1024)
    assert resource_spilled is True
    assert len(resource_stub["_artifact"]["preview"]["resources"]) <= 5
    resource_page = read_artifact_payload(resource_stub["_artifact"]["handle"], offset=5, limit=3)
    assert resource_page["total_items"] == 20
    assert resource_page["items"][0]["uri"] == "file://5"


def test_command_line_secret_redaction():
    """Verify inline command secrets like --password=123, -pSECRET, and PASSWORD=xyz are masked."""
    cmd1 = "mysql -u root -pMySecretPass123 -h localhost mydb"
    cmd2 = "pg_dump --password=supersecret -U postgres -d testdb"
    cmd3 = "export API_KEY=sk-abcdef123456789 && ./deploy.sh"

    masked1 = redact_secrets(cmd1)
    masked2 = redact_secrets(cmd2)
    masked3 = redact_secrets(cmd3)

    assert "MySecretPass123" not in masked1
    assert "-p******" in masked1

    assert "supersecret" not in masked2
    assert "--password=******" in masked2

    assert "sk-abcdef123456789" not in masked3
    assert "API_KEY=******" in masked3


def test_workflow_large_step_output_passed_in_memory_without_spill():
    """Verify workflow steps exchange raw in-memory data even when exceeding 32 KB."""
    from mcp_win_stdio.core.workflows import run_workflow

    large_list = [{"id": i, "content": f"blob_{i}" * 50} for i in range(500)]
    consumed_list = []

    def mock_caller(server, tool, args):
        if tool == "large_producer":
            return {"status": "success", "rows": large_list}
        elif tool == "consumer":
            consumed_list.extend(args.get("data", []))
            return {"status": "success", "consumed_count": len(args.get("data", []))}
        return {}

    wf = {
        "name": "large_chain",
        "steps": [
            {
                "id": "step1",
                "server": "db",
                "tool": "large_producer",
                "arguments": {},
            },
            {
                "id": "step2",
                "server": "db",
                "tool": "consumer",
                "arguments": {"data": "{{ steps.step1.rows }}"},
            },
        ],
    }

    res = run_workflow(wf, call_tool_fn=mock_caller)
    assert res["status"] == "success"
    # Verify Step 2 received the real list of 500 items, not an artifact handle stub!
    assert len(consumed_list) == 500
    assert consumed_list[499]["id"] == 499

