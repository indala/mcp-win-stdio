"""
FastMCP Server definition for mws.
Universal Dynamic On-Demand MCP Gateway & Tool Router.
"""

from typing import Any, Dict, List, Optional

try:
    from mcp.server.mcpserver import MCPServer as FastMCP
except (ImportError, ModuleNotFoundError):
    from mcp.server.fastmcp import FastMCP  # type: ignore[import-not-found]

from mcp_win_stdio.core.context import GLOBAL_CONTEXT
from mcp_win_stdio.core.workflows import (
    delete_workflow as core_delete_workflow,
)
from mcp_win_stdio.core.workflows import (
    list_workflows as core_list_workflows,
)
from mcp_win_stdio.core.workflows import (
    run_workflow as core_run_workflow,
)
from mcp_win_stdio.core.workflows import (
    save_workflow as core_save_workflow,
)

from .catalog import (
    describe_tool as catalog_describe_tool,
)
from .catalog import (
    discover_available_servers,
    find_servers_for_tool,
    generate_compact_signature,
    get_server_catalog,
    normalize_arguments,
)
from .catalog import (
    search_tools as catalog_search_tools,
)
from .process_pool import GLOBAL_POOL

# The MCP server name is "mws"
mcp = FastMCP("mws")

# Sticky active server context across calls
_ACTIVE_SERVER: Optional[str] = None


@mcp.tool()
def use_server(server: str) -> Dict[str, Any]:
    """
    Switch or declare the active MCP server context for subsequent tool calls.
    Once set, agents can execute tools without providing the 'server' parameter.

    Args:
        server: Target MCP server name (e.g. 'db', 'excel', 'git', 'ssh', 'rag', 'word', 'tsc', 'arch').
    """
    global _ACTIVE_SERVER
    clean = server.lower().strip()
    available = discover_available_servers()
    if clean not in available:
        return {
            "success": False,
            "error": f"Unknown server '{server}'. Available servers: {list(available.keys())}",
        }
    _ACTIVE_SERVER = clean
    GLOBAL_CONTEXT.set("server", clean)
    return {
        "success": True,
        "message": f"Active server set to '{clean}'. Subsequent tool calls without 'server' will default to '{clean}'.",
        "active_server": clean,
    }


@mcp.tool()
def manage_context(
    action: str = "get",
    type: Optional[str] = None,
    value: Optional[str] = None,
    session_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Manage scoped session context stacks (server, db_connection, ssh_host, workspace, workbook).
    Context values are automatically injected into subsequent tool calls, eliminating argument repetition.
    Independent stacks ensure changing a database connection never alters an SSH host or workspace.
    Sessions are completely isolated by 'session_id' to prevent cross-agent interference.

    Actions:
      - 'get':    Get active context value for a type, or snapshot of all if type is omitted.
      - 'set':    Set or replace active value for a context type.
      - 'push':   Push a new temporary value onto stack (preserves previous value for later pop).
      - 'pop':    Pop active value from stack, restoring previous context.
      - 'clear':  Clear a specific context stack or all stacks.

    Supported Types:
      - 'server':        Active MCP server namespace (e.g. 'db', 'excel', 'ssh', 'git', 'arch').
      - 'db_connection': Active database connection alias (e.g. 'postgres_prod', 'ijitest').
      - 'ssh_host':      Active remote SSH host alias (e.g. 'hostinger-prod', 'staging').
      - 'workspace':     Active project/workspace directory.
      - 'workbook':      Active Excel workbook file.
    """
    global _ACTIVE_SERVER
    act = action.lower().strip()
    session = GLOBAL_CONTEXT.get_session(session_id)

    if act == "get":
        if not type:
            return {"status": "success", "session_id": session.session_id, "contexts": session.snapshot()}
        return {
            "status": "success",
            "session_id": session.session_id,
            "type": type,
            "active": session.get(type),
        }
    elif act == "set":
        if not type or value is None:
            return {"status": "error", "error": "Both 'type' and 'value' are required for 'set'."}
        session.set(type, value)
        if type.lower().strip() == "server" and (not session_id or session_id == "default"):
            _ACTIVE_SERVER = value.lower().strip()
        return {
            "status": "success",
            "session_id": session.session_id,
            "message": f"Context '{type}' set to '{value}'.",
            "active": value,
        }
    elif act == "push":
        if not type or value is None:
            return {"status": "error", "error": "Both 'type' and 'value' are required for 'push'."}
        session.push(type, value)
        if type.lower().strip() == "server" and (not session_id or session_id == "default"):
            _ACTIVE_SERVER = value.lower().strip()
        return {
            "status": "success",
            "session_id": session.session_id,
            "message": f"Context '{type}' pushed '{value}' onto stack.",
            "active": value,
            "depth": len(session._stacks.get(type.lower().strip(), [])),
        }
    elif act == "pop":
        if not type:
            return {"status": "error", "error": "'type' is required for 'pop'."}
        removed = session.pop(type)
        new_active = session.get(type)
        if type.lower().strip() == "server" and (not session_id or session_id == "default"):
            _ACTIVE_SERVER = new_active
        return {
            "status": "success",
            "session_id": session.session_id,
            "popped": removed,
            "active": new_active,
            "message": f"Context '{type}' popped '{removed}'. Restored previous context: '{new_active}'.",
        }
    elif act == "clear":
        session.clear(type)
        if (not type or type.lower().strip() == "server") and (not session_id or session_id == "default"):
            _ACTIVE_SERVER = None
        return {
            "status": "success",
            "session_id": session.session_id,
            "message": f"Context '{type}' cleared." if type else "All contexts cleared.",
        }
    else:
        return {
            "status": "error",
            "error": f"Unknown action '{action}'. Supported actions: 'get', 'set', 'push', 'pop', 'clear'.",
        }


@mcp.tool()
def list_servers(
    server: Optional[str] = None,
    include_tools: bool = False,
    include_signatures: bool = False,
    refresh: bool = False,
) -> Dict[str, Any]:
    """
    Dynamically lists all available MCP servers or inspects a specific server.
    Returns installed status, real-time execution status ('active' if running, 'inactive' if dormant),
    dynamic tool counts, and capability descriptions.

    Args:
        server: Optional server name to inspect (e.g. 'excel', 'db', 'tsc'). When provided, only returns that server.
        include_tools: If True, includes tool names for each server.
        include_signatures: If True (with include_tools), includes compact parameter signatures for each tool.
        refresh: If True, forces re-probing of server tools.
    """
    return get_server_catalog(
        server=server,
        include_tools=include_tools,
        include_signatures=include_signatures,
        refresh=refresh,
    )


@mcp.tool()
def search_tools(
    query: str,
    server: Optional[str] = None,
    limit: int = 10,
    detail: bool = False,
) -> List[Dict[str, Any]]:
    """
    Search for tools across all available MCP servers using natural language keywords.
    Returns compact signatures by default (saving context tokens), or full schemas when detail=True.

    Args:
        query: Search keywords (e.g. 'read excel range', 'postgres table ddl', 'git branch').
        server: Optional server filter (e.g. 'excel', 'db', 'git', 'ssh', 'tsc', 'arch').
        limit: Maximum number of matching tools to return (default: 10).
        detail: If True, includes full JSON parameter schemas. Default False returns compact signatures.
    """
    return catalog_search_tools(query=query, server=server, limit=limit, detail=detail)


@mcp.tool()
def describe_tool(server: str, tool_name: str) -> Dict[str, Any]:
    """
    Get full parameter schema, data types, required fields, and docstring for a specific tool.

    Args:
        server: The target server name (e.g. 'db', 'excel', 'git', 'ssh', 'tsc', 'arch').
        tool_name: The exact tool name (e.g. 'read_query', 'get_workbook_info').
    """
    res = catalog_describe_tool(server, tool_name)
    if not res:
        return {
            "error": f"Tool '{tool_name}' not found on server '{server}'. Use search_tools to discover available tools."
        }
    return res


@mcp.tool()
def call_tool(
    server: Optional[str] = None,
    tool_name: Optional[str] = None,
    arguments: Optional[Dict[str, Any]] = None,
    tool: Optional[str] = None,
    session_id: Optional[str] = None,
) -> Any:
    """
    Execute a tool dynamically on a target MCP server with smart auto-routing and context stack inheritance.
    Spawns the child server process on-demand if not already running,
    forwards the execution, and returns structured results with context protection.
    Automatically normalizes parameter aliases and camelCase names.

    Smart Routing & Context Stack:
    - If 'server' is omitted, 'call_tool' automatically routes using the active server or tool catalog.
    - Contextual parameters ('connection', 'host', 'workspace', 'workbook') are auto-injected from session context.
    - Supports dot notation (e.g. 'db.read_query', 'excel.preview_sheet').
    - Accepts either 'tool_name' or 'tool'.
    - Sessions are isolated by 'session_id' to prevent multi-agent crosstalk.

    Args:
        server: Optional target server name (e.g. 'db', 'excel', 'word', 'tsc', 'ssh', 'git', 'arch').
        tool_name: The tool name to execute (e.g. 'read_query', 'preview_sheet', 'get_workbook_info').
        arguments: Dictionary of arguments matching the tool's parameter schema.
        tool: Alias for tool_name.
        session_id: Optional session identifier for isolated multi-client context stacks.
    """
    global _ACTIVE_SERVER

    # Accept 'tool' if tool_name is not explicitly passed
    raw_tool = tool_name or tool
    target_tool = str(raw_tool or "").strip()
    target_server = (server or "").lower().strip()

    available_servers = discover_available_servers()
    session = GLOBAL_CONTEXT.get_session(session_id)

    # 1. Handle dot notation (e.g. 'db.read_query' or 'excel.preview_sheet')
    if "." in target_tool:
        prefix, actual_tool = target_tool.split(".", 1)
        if prefix.lower() in available_servers:
            target_server = prefix.lower()
            target_tool = actual_tool

    # 2. If tool_name was omitted but server was passed, check if server is actually a tool name
    if not target_tool and target_server:
        if target_server not in available_servers:
            matching = find_servers_for_tool(target_server)
            if matching:
                target_tool = target_server
                target_server = matching[0]

    if not target_tool:
        return {
            "isError": True,
            "error": "Missing 'tool_name' parameter. Please specify the name of the tool to execute.",
        }

    # 3. If target_server is still missing, check active server context from session
    active_ctx_server = session.get("server") or _ACTIVE_SERVER
    if not target_server:
        if active_ctx_server and active_ctx_server in available_servers:
            candidates = find_servers_for_tool(target_tool)
            if active_ctx_server in candidates:
                target_server = active_ctx_server

        # Otherwise resolve via unique global catalog match
        if not target_server:
            candidates = find_servers_for_tool(target_tool)
            if len(candidates) == 1:
                target_server = candidates[0]
            elif len(candidates) > 1:
                if active_ctx_server in candidates:
                    target_server = active_ctx_server
                else:
                    return {
                        "isError": True,
                        "error": f"Tool '{target_tool}' exists on multiple servers: {candidates}. Please specify 'server' or call use_server().",
                        "candidate_servers": candidates,
                        "active_server": active_ctx_server,
                    }
            else:
                return {
                    "isError": True,
                    "error": f"Tool '{target_tool}' was not found on any registered MCP server. Use search_tools('{target_tool}') to find available tools.",
                }

    # 4. Context resolution: auto-inject contextual params (connection, host, workspace, workbook)
    meta = catalog_describe_tool(target_server, target_tool)
    expected_params = []
    if meta and isinstance(meta.get("parameters"), dict):
        expected_params = list(meta["parameters"].get("properties", {}).keys())

    merged_args = dict(arguments or {})
    resolved_args, injected = session.resolve_arguments(
        server=target_server,
        tool_name=target_tool,
        arguments=merged_args,
        expected_params=expected_params,
    )

    norm_args = normalize_arguments(target_server, target_tool, resolved_args)
    proc = GLOBAL_POOL.get_or_spawn(target_server)
    res = proc.call_tool(target_tool, norm_args)

    # If tool call failed, enrich with schema guidance to enable immediate self-correction
    if isinstance(res, dict) and res.get("isError"):
        if meta:
            params = meta.get("parameters", {})
            sig = generate_compact_signature(target_tool, params)
            req = params.get("required", []) if isinstance(params, dict) else []
            props = list(params.get("properties", {}).keys()) if isinstance(params, dict) else []
            res["expected_signature"] = sig
            res["required_parameters"] = req
            res["available_parameters"] = props

    return res


@mcp.tool()
def get_active_sessions() -> List[Dict[str, Any]]:
    """
    Returns live metrics on all active warm child MCP processes:
    PID, uptime in seconds, idle duration, and total tool calls executed.
    """
    return GLOBAL_POOL.get_active_sessions()


@mcp.tool()
def stop_server(server: str) -> Dict[str, Any]:
    """
    Gracefully shuts down an active warm child MCP process to immediately release RAM and file locks.

    Args:
        server: Server name to terminate (e.g. 'excel', 'db').
    """
    clean_server = server.lower().strip()
    stopped = GLOBAL_POOL.stop_server(clean_server)
    return {
        "server": clean_server,
        "stopped": stopped,
        "message": f"Server '{clean_server}' process terminated." if stopped else f"Server '{clean_server}' was not running.",
    }


@mcp.tool()
def list_workflows(scope: str = "all") -> List[Dict[str, Any]]:
    """
    List all reusable custom workflows discovered in the current workspace (.mws/workflows/)
    and global user configuration (~/.mcp-win-stdio/workflows/).

    Args:
        scope: Filter by scope: 'all' (default), 'project', or 'global'.
    """
    return core_list_workflows(scope=scope)


@mcp.tool()
def save_workflow(
    name: str,
    definition: Dict[str, Any],
    scope: str = "project",
) -> Dict[str, Any]:
    """
    Save a custom multi-step workflow recipe for future zero-latency execution.
    Composite workflows allow agents and users to chain multiple MCP tools together without
    burning context or waiting for round-trip LLM turns.

    Args:
        name: Unique workflow identifier (e.g. 'deploy_staging', 'sync_master_data').
        definition: Workflow dictionary containing 'title', 'description', 'parameters', and 'steps'.
                    Each step must specify 'server', 'tool', and 'arguments' (with optional {{ param }} templating).
        scope: Where to store: 'project' (default, in .mws/workflows/) or 'global' (in ~/.mcp-win-stdio/workflows/).
    """
    return core_save_workflow(name=name, definition=definition, scope=scope)


@mcp.tool()
def run_workflow(
    name: str,
    parameters: Optional[Dict[str, Any]] = None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """
    Execute a saved multi-step composite workflow in a single atomic invocation.
    Pipes variables and step outputs forward, halts safely on failure, supports
    recovery steps, dry_run previews, and returns a full execution trace with timing metrics.

    Args:
        name: Name of the workflow to execute.
        parameters: Optional dictionary of parameter values to pass into the workflow.
        dry_run: If True, resolves variables and returns the projected execution plan without invoking tools.
    """
    return core_run_workflow(
        name_or_def=name,
        parameters=parameters,
        call_tool_fn=lambda s, t, a: call_tool(s, t, a),
        dry_run=dry_run,
    )


@mcp.tool()
def delete_workflow(name: str, scope: Optional[str] = None) -> Dict[str, Any]:
    """
    Delete a saved custom workflow.

    Args:
        name: Name of the workflow to delete.
        scope: Optional scope filter ('project' or 'global').
    """
    return core_delete_workflow(name=name, scope=scope)


def main():
    mcp.run()


if __name__ == "__main__":
    main()
