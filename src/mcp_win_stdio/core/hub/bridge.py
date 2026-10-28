"""
Streamable HTTP Gateway Bridge for MCP Hub.
Connects FastMCP/MCPServer Streamable HTTP transport with BearerAuthMiddleware,
enforces ToolFilter (deny > allow) at both discovery and invocation boundaries,
and routes tool calls to supervised child processes.
"""

import ipaddress
import json
import logging
from typing import Any, Callable, Dict, List, Optional, Set

from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import (
    CallToolRequestParams,
    CallToolResult,
    ListToolsResult,
    PaginatedRequestParams,
    TextContent,
    Tool,
)
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from mcp_win_stdio.core.hub.auth import BearerAuthMiddleware, SessionManager
from mcp_win_stdio.core.hub.models import ServerConfig, ToolFilter
from mcp_win_stdio.core.hub.profiles import ProfileManager
from mcp_win_stdio.core.hub.registry import HubRegistry
from mcp_win_stdio.core.hub.secrets import redact_sensitive_data
from mcp_win_stdio.core.hub.supervisor import ProcessSupervisor

logger = logging.getLogger(__name__)


class ToolRouter:
    """
    Registry and routing table for MCP tools.
    Maps tool names to their owning server and applies ToolFilter policies.
    Supports both unqualified ('tool') and namespaced ('server.tool') identifiers.
    """

    def __init__(self) -> None:
        self._tools: Dict[str, Tool] = {}
        self._tool_to_server: Dict[str, str] = {}

    def register_tool(self, server_name: str, tool: Tool) -> None:
        """Register a tool definition associated with an owning server."""
        clean_srv = server_name.lower().strip()
        # Unqualified mapping
        self._tools[tool.name] = tool
        self._tool_to_server[tool.name] = clean_srv
        # Namespaced mapping
        namespaced_name = f"{clean_srv}.{tool.name}"
        self._tools[namespaced_name] = tool
        self._tool_to_server[namespaced_name] = clean_srv

    def get_tool(self, tool_name: str) -> Optional[Tool]:
        """Look up tool metadata by name."""
        return self._tools.get(tool_name)

    def get_tool_server(self, tool_name: str) -> Optional[str]:
        """Resolve the owning server name for a given tool."""
        return self._tool_to_server.get(tool_name)

    def is_tool_allowed(self, tool_name: str, tool_filter: Optional[ToolFilter] = None) -> bool:
        """
        Check whether a tool is permitted to execute.
        Deny rules strictly override allow rules.
        Evaluates both unqualified ('tool') and namespaced ('server.tool') identifiers.
        """
        if not tool_filter:
            return True

        srv = self.get_tool_server(tool_name)
        base_name = tool_name.split(".", 1)[1] if (srv and tool_name.startswith(f"{srv}.")) else tool_name

        # Deny rule check on base name
        if not tool_filter.is_tool_allowed(base_name):
            return False

        # Deny rule check on namespaced name
        if srv:
            namespaced = f"{srv}.{base_name}"
            if not tool_filter.is_tool_allowed(namespaced):
                return False

        return True

    def list_tools(self, tool_filter: Optional[ToolFilter] = None) -> List[Tool]:
        """
        List all permitted tools under the active tool filter.
        Tools matching deny rules are strictly omitted from discovery.
        """
        result = []
        seen: Set[str] = set()
        for name, tool in self._tools.items():
            if not self.is_tool_allowed(name, tool_filter):
                continue
            if tool.name not in seen:
                seen.add(tool.name)
                result.append(tool)
        return result


class StreamableHttpBridge:
    """
    Hosts the MCP Hub over Streamable HTTP.
    Integrates Bearer authentication, session management, tool filtering,
    and supervised subprocess routing.
    """

    def __init__(
        self,
        supervisor: ProcessSupervisor,
        registry: HubRegistry,
        profile_manager: Optional[ProfileManager] = None,
        session_manager: Optional[SessionManager] = None,
        tool_filter: Optional[ToolFilter] = None,
        transport_security: Optional[TransportSecuritySettings] = None,
    ):
        self.supervisor = supervisor
        self.registry = registry
        self.profile_manager = profile_manager
        self.session_manager = session_manager or SessionManager()
        self.tool_filter = tool_filter
        self.router = ToolRouter()

        # Enable DNS rebinding protection and origin restrictions by default for local hub
        if transport_security is None:
            allowed_hosts = [
                "127.0.0.1:*",
                "127.0.0.1",
                "localhost:*",
                "localhost",
                "[::1]:*",
                "[::1]",
                "testserver",
                "testserver:*",
            ]
            allowed_origins = [
                "http://127.0.0.1:*",
                "http://127.0.0.1",
                "http://localhost:*",
                "http://localhost",
                "http://[::1]:*",
                "http://[::1]",
                "http://testserver",
                "http://testserver:*",
                "https://127.0.0.1:*",
                "https://localhost:*",
                "https://[::1]:*",
            ]
            cfg_host = getattr(getattr(registry, "config", None), "http_host", None)
            # Security invariant: Only genuinely validated loopback IP addresses are permitted.
            # External hostnames, wildcard binds (0.0.0.0), and invalid IP strings are strictly rejected.
            if cfg_host:
                try:
                    ip_obj = ipaddress.ip_address(cfg_host.strip("[]"))
                    if ip_obj.is_loopback and cfg_host not in allowed_hosts:
                        allowed_hosts.extend([f"{cfg_host}:*", cfg_host])
                        allowed_origins.extend([f"http://{cfg_host}:*", f"https://{cfg_host}:*"])
                except ValueError:
                    pass

            transport_security = TransportSecuritySettings(
                enable_dns_rebinding_protection=True,
                allowed_hosts=allowed_hosts,
                allowed_origins=allowed_origins,
            )
        self.transport_security = transport_security

        # Initialize core MCPServer instance
        self.mcp = MCPServer("mws")

        # Hook low-level request handlers for custom routing and filtering
        self.mcp._lowlevel_server.add_request_handler(
            "tools/list",
            PaginatedRequestParams,
            self._handle_list_tools,
        )
        self.mcp._lowlevel_server.add_request_handler(
            "tools/call",
            CallToolRequestParams,
            self._handle_call_tool,
        )

    def register_tool(
        self,
        server_name: str,
        name: str,
        description: str = "",
        input_schema: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Register a tool definition into the Hub routing table."""
        tool = Tool(
            name=name,
            description=description,
            inputSchema=input_schema or {"type": "object", "properties": {}},
        )
        self.router.register_tool(server_name, tool)

    async def _handle_list_tools(
        self,
        ctx: Any,
        params: Optional[PaginatedRequestParams] = None,
    ) -> ListToolsResult:
        """
        Discovery handler: Returns only tools permitted by the active ToolFilter.
        Denied tools are completely hidden from discovery.
        """
        effective_filter = self.tool_filter
        tools = self.router.list_tools(effective_filter)
        return ListToolsResult(tools=tools)

    async def _handle_call_tool(
        self,
        ctx: Any,
        params: CallToolRequestParams,
    ) -> CallToolResult:
        """
        Invocation handler: Strictly enforces ToolFilter and executes tools via supervisor.
        Rejection rules:
          1. Direct invocation of denied tools is rejected (even if client skips discovery).
          2. Unknown tools are rejected without leaking server configurations.
          3. Process crashes or execution timeouts are handled gracefully.
        """
        tool_name = params.name

        # 1. Enforce ToolFilter at invocation boundary
        if not self.router.is_tool_allowed(tool_name, self.tool_filter):
            return CallToolResult(
                isError=True,
                content=[
                    TextContent(
                        type="text",
                        text=f"Tool '{tool_name}' is prohibited by access policy.",
                    )
                ],
            )

        # 2. Resolve owning server and un-prefixed tool name
        server_name = self.router.get_tool_server(tool_name)
        if not server_name:
            return CallToolResult(
                isError=True,
                content=[
                    TextContent(
                        type="text",
                        text=f"Unknown tool '{tool_name}'.",
                    )
                ],
            )

        # Strip namespace prefix if caller invoked as 'server.tool'
        if "." in tool_name and tool_name.startswith(f"{server_name}."):
            target_tool_name = tool_name[len(server_name) + 1:]
        else:
            target_tool_name = tool_name

        # 3. Dispatch to ProcessSupervisor
        try:
            raw_result = self.supervisor.call_tool(
                server_name=server_name,
                tool_name=target_tool_name,
                arguments=params.arguments or {},
            )
        except Exception as exc:
            safe_err = redact_sensitive_data(str(exc))
            logger.warning("Tool execution error for '%s' on '%s': %s", tool_name, server_name, safe_err)
            return CallToolResult(
                isError=True,
                content=[TextContent(type="text", text=safe_err)],
            )

        # 4. Return as true MCP CallToolResult proxy, preserving rich content types (images, resources, etc.)
        if isinstance(raw_result, dict):
            try:
                return CallToolResult.model_validate(raw_result)
            except Exception:
                pass

        # Fallback formatting for non-standard child outputs
        content_items: List[TextContent] = []
        if isinstance(raw_result, dict) and "content" in raw_result:
            for item in raw_result["content"]:
                if isinstance(item, dict):
                    txt = item.get("text", "")
                    content_items.append(TextContent(type="text", text=txt))
                elif isinstance(item, str):
                    content_items.append(TextContent(type="text", text=item))
        elif isinstance(raw_result, str):
            content_items.append(TextContent(type="text", text=raw_result))
        else:
            content_items.append(TextContent(type="text", text=json.dumps(raw_result)))

        is_error = False
        if isinstance(raw_result, dict):
            is_error = bool(raw_result.get("isError", False))

        return CallToolResult(
            isError=is_error,
            content=content_items,
        )

    def create_asgi_app(self) -> Callable[..., Any]:
        """
        Build the full ASGI application.
        Wraps the FastMCP Streamable HTTP app with health endpoints and BearerAuthMiddleware.
        """
        # Base Starlette app from MCP SDK
        mcp_starlette = self.mcp.streamable_http_app(
            transport_security=self.transport_security,
        )

        # Attach health endpoints
        async def health_endpoint(request: Request) -> JSONResponse:
            instances = self.supervisor.list_instances()
            return JSONResponse(
                {
                    "status": "ok",
                    "servers_count": len(instances),
                    "active_sessions": self.session_manager.active_session_count(),
                }
            )

        mcp_starlette.routes.append(Route("/health", health_endpoint, methods=["GET"]))
        mcp_starlette.routes.append(Route("/status", health_endpoint, methods=["GET"]))

        # Wrap with BearerAuthMiddleware
        cfg = self.registry.config
        auth_app = BearerAuthMiddleware(
            app=mcp_starlette,
            auth_token_env=cfg.http_auth_token_env,
            bind_host=cfg.http_host,
            session_manager=self.session_manager,
            health_routes={"/health", "/status"},
            allow_loopback_health_unauthenticated=True,
        )
        return auth_app

    def shutdown(self) -> None:
        """Shut down supervisor and clean up active sessions."""
        self.supervisor.shutdown()
        self.session_manager.cleanup_idle()

    def __enter__(self) -> "StreamableHttpBridge":
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.shutdown()
