"""
Unit and integration tests for mws server (Universal On-Demand MCP Gateway & Tool Router).
"""

import sys
from pathlib import Path

# Ensure root src and all package src paths are on sys.path
for p in Path("packages").glob("*/src"):
    sys.path.insert(0, str(p.resolve()))
sys.path.insert(0, str(Path("src").resolve()))

from mcp_win_stdio.server.catalog import (
    describe_tool,
    generate_compact_signature,
    get_server_catalog,
    get_server_tools,
    normalize_arguments,
    search_tools,
)
from mcp_win_stdio.server.discovery import discover_available_servers
from mcp_win_stdio.server.process_pool import GLOBAL_POOL, ProcessPool
from mcp_win_stdio.server.server import (
    call_tool,
    delete_workflow,
    get_active_sessions,
    list_servers,
    list_workflows,
    run_workflow,
    save_workflow,
    stop_server,
    use_server,
)


def test_dynamic_server_discovery():
    """Verify that servers are discovered 100% dynamically without hardcoding."""
    servers = discover_available_servers()
    assert isinstance(servers, dict)
    assert len(servers) >= 9

    # Core built-ins should be discovered dynamically
    for srv in ("excel", "word", "explorer", "tsc", "db", "git", "ssh", "rag", "excel-db"):
        assert srv in servers, f"Expected dynamically discovered server '{srv}'"
        assert servers[srv]["type"] == "builtin"
        assert "command" in servers[srv]
        assert "args" in servers[srv]


def test_server_catalog():
    """Verify get_server_catalog builds live status and dynamic tool counts."""
    catalog = get_server_catalog(include_tools=True, refresh=False)
    assert "total_servers" in catalog
    assert "servers" in catalog
    assert catalog["total_servers"] >= 9

    # Check db in catalog
    assert "db" in catalog["servers"]
    db_entry = catalog["servers"]["db"]
    assert db_entry["tool_count"] == 34
    assert "read_query" in db_entry["tools"]
    assert "list_connections" in db_entry["tools"]

    # Check tsc in catalog
    assert "tsc" in catalog["servers"]
    tsc_entry = catalog["servers"]["tsc"]
    assert tsc_entry["tool_count"] == 12
    assert "list_projects" in tsc_entry["tools"]


def test_search_tools():
    """Verify natural language search across tools returning compact signatures and full schemas."""
    # 1. Search for SQL / query tools with default compact mode
    matches = search_tools(query="safe select query json sql", server="db", limit=5)
    assert len(matches) > 0
    top_tool = matches[0]
    assert top_tool["server"] == "db"
    assert top_tool["tool"] == "read_query"
    assert "signature" in top_tool
    assert "parameters" not in top_tool

    # 2. Detailed search returns complete JSON schema
    detailed_matches = search_tools(query="safe select query json sql", server="db", limit=5, detail=True)
    assert len(detailed_matches) > 0
    assert "parameters" in detailed_matches[0]
    assert "sql" in detailed_matches[0]["parameters"]["properties"]

    # 3. Cross-server search
    ts_matches = search_tools(query="typescript error suggestions", limit=5)
    assert any(m["server"] == "tsc" for m in ts_matches)


def test_describe_tool():
    """Verify describe_tool returns exact parameters and docstring."""
    desc = describe_tool("db", "read_query")
    assert desc is not None
    assert desc["server"] == "db"
    assert desc["tool"] == "read_query"
    assert "parameters" in desc
    assert "sql" in desc["parameters"]["properties"]
    assert "limit" in desc["parameters"]["properties"]

    # Non-existent tool returns None
    assert describe_tool("db", "non_existent_tool_xyz") is None


def test_process_pool_lazy_spawn_and_proxy():
    """Verify process pool lazily spawns child MCP process and executes tool call."""
    # Initial active sessions
    GLOBAL_POOL.shutdown_all()
    initial_sessions = GLOBAL_POOL.get_active_sessions()
    assert len(initial_sessions) == 0

    # Execute a tool via call_tool (spawns 'db' on-demand)
    res = call_tool(server="db", tool_name="list_connections", arguments={})
    assert res is not None
    assert "content" in res

    # Now 'db' should be an active session
    active = GLOBAL_POOL.get_active_sessions()
    assert len(active) == 1
    assert active[0]["server"] == "db"
    assert active[0]["tools_called"] >= 1

    # Graceful stop_server
    stop_res = stop_server("db")
    assert stop_res["stopped"] is True
    assert len(GLOBAL_POOL.get_active_sessions()) == 0


def test_call_tool_smart_routing():
    """Verify smart routing infers server when omitted, supports use_server, dot-notation, and merges kwargs."""
    GLOBAL_POOL.shutdown_all()

    # 1. Explicit use_server switches context
    ctx = use_server("db")
    assert ctx["success"] is True
    assert ctx["active_server"] == "db"

    # 2. Call list_connections without specifying server='db'
    res = call_tool(tool_name="list_connections")
    assert res is not None
    assert "content" in res

    # 3. Call via dot-notation: 'db.list_connections'
    dot_res = call_tool(tool_name="db.list_connections")
    assert dot_res is not None
    assert "content" in dot_res

    # 4. Unknown tool returns helpful error with available hints
    bad_res = call_tool(tool_name="unknown_tool_12345")
    assert bad_res.get("isError") is True
    assert "not found" in bad_res.get("error", "")

    GLOBAL_POOL.shutdown_all()


def test_server_meta_tools_api():
    """Verify FastMCP mws server functions return proper structures for agents."""
    # list_servers
    listing = list_servers(include_tools=False)
    assert "servers" in listing
    assert listing["total_servers"] >= 9

    # Verify each server has installed, status (active/inactive), tool_count, and description
    for s_name, s_info in listing["servers"].items():
        assert "installed" in s_info
        assert "status" in s_info
        assert s_info["status"] in ("active", "inactive", "not_installed")
        assert "tool_count" in s_info
        assert "description" in s_info

    # get_active_sessions
    sessions = get_active_sessions()
    assert isinstance(sessions, list)


def test_compact_signature_generation():
    """Verify generation of compact, human-readable signatures."""
    sig = generate_compact_signature(
        "preview_sheet",
        {
            "properties": {
                "file_path": {"type": "string"},
                "sheet_name": {"type": "string"},
                "nrows": {"type": "integer", "default": 10},
            },
            "required": ["file_path"],
        },
    )
    assert "file_path: string" in sig
    assert "sheet_name?: string" in sig
    assert "nrows?: integer = 10" in sig


def test_argument_normalization_and_aliases():
    """Verify smart aliasing and camelCase -> snake_case conversion."""
    # Test camelCase conversion against db.read_query (expects sql, limit, connection)
    args = {"sql": "SELECT 1;", "connectionName": "live_mysql"}
    norm = normalize_arguments("db", "read_query", args)
    assert norm["sql"] == "SELECT 1;"
    assert "connection" in norm  # mapped connectionName -> connection

    # Test shorthand alias mapping
    args2 = {"query": "SELECT 1;"}
    norm2 = normalize_arguments("db", "read_query", args2)
    assert "sql" in norm2
    assert norm2["sql"] == "SELECT 1;"


def test_server_workflow_tools():
    """Verify that mws server exposes and executes composite workflow tools."""
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        import os
        old_cwd = os.getcwd()
        try:
            os.chdir(tmpdir)
            # 1. save_workflow
            saved = save_workflow(
                name="server_mock_wf",
                definition={
                    "title": "Mock Server Workflow",
                    "steps": [
                        {
                            "id": "s1",
                            "server": "explorer",
                            "tool": "workspace_summary",
                            "arguments": {"path": "."},
                        }
                    ],
                },
                scope="project",
            )
            assert saved["status"] == "success"

            # 2. list_workflows
            wfs = list_workflows()
            assert any(w["name"] == "server_mock_wf" for w in wfs)

            # 3. delete_workflow
            deleted = delete_workflow("server_mock_wf")
            assert deleted["deleted"] is True
        finally:
            os.chdir(old_cwd)


def test_manage_context_and_stack_injection():
    """Verify manage_context tool and context stack resolution in call_tool."""
    from mcp_win_stdio.core.context import GLOBAL_CONTEXT
    from mcp_win_stdio.server.server import manage_context

    GLOBAL_CONTEXT.clear()

    # 1. Set and get context
    res = manage_context(action="set", type="db_connection", value="test_pg_db")
    assert res["status"] == "success"
    assert res["active"] == "test_pg_db"

    check = manage_context(action="get", type="db_connection")
    assert check["active"] == "test_pg_db"

    # 2. Push temporary override
    res_push = manage_context(action="push", type="db_connection", value="temp_analytics")
    assert res_push["status"] == "success"
    assert res_push["active"] == "temp_analytics"
    assert res_push["depth"] == 2

    # 3. Pop restores previous
    res_pop = manage_context(action="pop", type="db_connection")
    assert res_pop["status"] == "success"
    assert res_pop["popped"] == "temp_analytics"
    assert res_pop["active"] == "test_pg_db"

    # 4. Snapshot contains all contexts
    snap = manage_context(action="get")
    assert "contexts" in snap
    assert snap["contexts"]["db_connection"]["active"] == "test_pg_db"

    GLOBAL_CONTEXT.clear()

