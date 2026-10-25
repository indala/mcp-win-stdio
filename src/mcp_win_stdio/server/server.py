"""
FastMCP Server definition for mws.
Universal Dynamic On-Demand MCP Gateway & Tool Router.
"""

from typing import Any, Dict, List, Optional

try:
    from mcp.server.mcpserver import MCPServer as FastMCP
except (ImportError, ModuleNotFoundError):
    from mcp.server.fastmcp import FastMCP  # type: ignore[import-not-found]

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
def search_tools(query: str, server: Optional[str] = None, limit: int = 10) -> List[Dict[str, Any]]:
    """
    Search for tools across all available MCP servers using natural language keywords.
    Returns complete JSON parameter schemas and docstrings for only the matching tools,
    saving thousands of tokens compared to loading all tools eagerly.

    Args:
        query: Search keywords (e.g. 'read excel range', 'postgres table ddl', 'git branch').
        server: Optional server filter (e.g. 'excel', 'db', 'git', 'ssh', 'tsc').
        limit: Maximum number of matching tools to return (default: 10).
    """
    return catalog_search_tools(query=query, server=server, limit=limit)


@mcp.tool()
def describe_tool(server: str, tool_name: str) -> Dict[str, Any]:
    """
    Get full parameter schema, data types, required fields, and docstring for a specific tool.

    Args:
        server: The target server name (e.g. 'db', 'excel', 'git', 'ssh', 'tsc').
        tool_name: The exact tool name (e.g. 'read_query', 'get_workbook_info').
    """
    res = catalog_describe_tool(server, tool_name)
    if not res:
        return {
            "error": f"Tool '{tool_name}' not found on server '{server}'. Use search_tools to discover available tools."
        }
    return res


@mcp.tool()
def call_tool(server: str, tool_name: str, arguments: Optional[Dict[str, Any]] = None) -> Any:
    """
    Execute a tool dynamically on a target MCP server.
    Spawns the child server process on-demand if not already running,
    forwards the execution, and returns structured results with context protection.
    Automatically normalizes parameter aliases and camelCase names.

    Args:
        server: The target server name (e.g. 'db', 'excel', 'word', 'tsc', 'ssh', 'git').
        tool_name: The tool name to execute (e.g. 'list_connections', 'get_workbook_info').
        arguments: Dictionary of arguments matching the tool's parameter schema.
    """
    clean_server = server.lower().strip()
    norm_args = normalize_arguments(clean_server, tool_name, arguments or {})
    proc = GLOBAL_POOL.get_or_spawn(clean_server)
    res = proc.call_tool(tool_name, norm_args)

    # If tool call failed, enrich with schema guidance to enable immediate self-correction
    if isinstance(res, dict) and res.get("isError"):
        meta = catalog_describe_tool(clean_server, tool_name)
        if meta:
            params = meta.get("parameters", {})
            sig = generate_compact_signature(tool_name, params)
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
) -> Dict[str, Any]:
    """
    Execute a saved multi-step composite workflow in a single atomic invocation.
    Pipes variables and step outputs forward, halts safely on failure, and returns
    a full execution trace with timing metrics.

    Args:
        name: Name of the workflow to execute.
        parameters: Optional dictionary of parameter values to pass into the workflow.
    """
    return core_run_workflow(
        name_or_def=name,
        parameters=parameters,
        call_tool_fn=lambda s, t, a: call_tool(s, t, a),
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
