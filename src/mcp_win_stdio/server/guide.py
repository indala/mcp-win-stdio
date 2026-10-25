"""
Interactive user and agent guide for mws server.
"""


def print_server_guide() -> None:
    """Print comprehensive guide and prompt recipes for mws server."""
    guide_text = """
================================================================================
   mws server (Universal On-Demand Gateway & Dynamic Tool Router)
================================================================================
mws is not just a CLI - it is itself the unified MCP Server!
Exposes 6 lightweight meta-tools (~400 tokens) to the agent instead of loading
150-200+ tools upfront into the LLM context. Child MCP processes (db, excel,
git, ssh, tsc, etc.) are lazily spawned on-demand and kept warm.

Available Tools (6 Meta-Tools):
--------------------------------------------------------------------------------
1. list_servers
   - Dynamically lists all installed and available MCP servers without hardcoding.
   - Shows running status ('active' / 'idle'), dynamic live tool counts, and summaries.
   - Args: include_tools (bool, default: False), refresh (bool, default: False)

2. search_tools
   - Search for tools across all servers using natural language keywords.
   - Returns complete JSON parameter schemas and docstrings only for matching tools.
   - Args: query (str), server (optional str), limit (int, default: 10)

3. describe_tool
   - Fetches the complete parameter schema, types, and docstring for a specific tool.
   - Args: server (str), tool_name (str)

4. call_tool
   - Transparently executes a tool on a child MCP server.
   - Lazily boots the server process if not running, proxies execution, and returns
     clean structured results protected from context overflow.
   - Args: server (str), tool_name (str), arguments (optional dict)

5. get_active_sessions
   - Lists active warm child MCP processes, their PIDs, uptime, idle time, and tool call count.

6. stop_server
   - Gracefully shuts down a running child process to release RAM or file locks.
   - Args: server (str)

--------------------------------------------------------------------------------
Quick Agent Configuration (Claude Desktop, Cursor, Antigravity, Cline):
--------------------------------------------------------------------------------
Just configure 'mws' directly:
{
  "mcpServers": {
    "mws": {
      "command": "mws",
      "args": ["server"]
    }
  }
}
================================================================================
"""
    print(guide_text)
