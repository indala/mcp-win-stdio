"""
Streamable HTTP Gateway Bridge for MCP Hub.
Connects FastMCP/MCPServer Streamable HTTP transport with BearerAuthMiddleware,
enforces ToolFilter (deny > allow) at both discovery and invocation boundaries,
and routes tool calls to supervised child processes.
"""

import ipaddress
import json
import logging
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

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
    Immune to casing variations, whitespace tricks, and namespace evasion.
    Prevents cross-server unqualified collisions.
    """

    def __init__(self) -> None:
        self._tools: Dict[str, Tool] = {}
        self._tool_to_server: Dict[str, str] = {}
        self._normalized_tools: Dict[str, Tool] = {}
        self._normalized_tool_to_server: Dict[str, str] = {}
        self._ambiguous_tools: Set[str] = set()

    def register_tool(self, server_name: str, tool: Tool) -> None:
        """Register a tool definition associated with an owning server."""
        clean_srv = server_name.lower().strip()
        raw_name = tool.name.strip()
        lower_name = raw_name.lower()

        # Track cross-server unqualified name collisions to prevent silent resolution to wrong server
        existing_srv = self._normalized_tool_to_server.get(lower_name)
        if existing_srv is not None and existing_srv != clean_srv:
            self._ambiguous_tools.add(lower_name)

        # Unqualified mapping (raw and normalized)
        self._tools[raw_name] = tool
        self._tool_to_server[raw_name] = clean_srv
        self._normalized_tools[lower_name] = tool
        self._normalized_tool_to_server[lower_name] = clean_srv

        # Namespaced mapping (raw and normalized)
        namespaced_raw = f"{clean_srv}.{raw_name}"
        namespaced_lower = f"{clean_srv}.{lower_name}"
        self._tools[namespaced_raw] = tool
        self._tool_to_server[namespaced_raw] = clean_srv
        self._normalized_tools[namespaced_lower] = tool
        self._normalized_tool_to_server[namespaced_lower] = clean_srv

    def is_ambiguous_tool(self, tool_name: str) -> bool:
        """Returns True if the tool name is an unqualified name registered by multiple servers."""
        if not tool_name or not isinstance(tool_name, str):
            return False
        clean = tool_name.strip().lower()
        return clean in self._ambiguous_tools

    def resolve_tool(self, tool_name: str) -> Tuple[Optional[Tool], Optional[str]]:
        """
        Resolves a caller-requested tool name to a single unique registered Tool
        and its owning server name.
        Returns (None, None) if unknown, malformed, or ambiguous across servers.
        """
        if not tool_name or not isinstance(tool_name, str):
            return None, None
        clean = tool_name.strip().lower()
        if not clean or clean in self._ambiguous_tools:
            return None, None

        tool = self._normalized_tools.get(clean) or self._tools.get(tool_name)
        srv = self._normalized_tool_to_server.get(clean) or self._tool_to_server.get(tool_name)
        if tool is not None and srv is not None:
            return tool, srv
        return None, None

    def get_tool(self, tool_name: str) -> Optional[Tool]:
        """Look up tool metadata by name (case-insensitive and whitespace-tolerant)."""
        tool, _ = self.resolve_tool(tool_name)
        return tool

    def get_tool_server(self, tool_name: str) -> Optional[str]:
        """Resolve the owning server name for a given tool (case-insensitive and whitespace-tolerant)."""
        _, srv = self.resolve_tool(tool_name)
        return srv

    def is_tool_allowed(self, tool_name: str, tool_filter: Optional[ToolFilter] = None) -> bool:
        """
        Check whether a tool is permitted to execute.
        Deny rules strictly override allow rules.
        Evaluates both unqualified ('tool') and namespaced ('server.tool') representations.
        Case-insensitive and whitespace-tolerant.
        """
        if not tool_filter:
            return True
        if not tool_name or not isinstance(tool_name, str):
            return False

        clean = tool_name.strip().lower()
        if not clean:
            return False

        # If it resolves to a registered tool, authorize against that canonical identity
        tool, srv = self.resolve_tool(clean)
        if tool is not None and srv is not None:
            return tool_filter.is_tool_allowed(tool.name, server_name=srv)

        # Fallback for patterns or namespaced strings before/without registration
        srv = self._normalized_tool_to_server.get(clean)
        return tool_filter.is_tool_allowed(clean, server_name=srv)

    def list_tools(self, tool_filter: Optional[ToolFilter] = None) -> List[Tool]:
        """
        List all permitted tools under the active tool filter.
        Tools matching deny rules are strictly omitted from discovery.
        """
        result = []
        seen: Set[str] = set()
        for name, tool in self._tools.items():
            srv = self._tool_to_server.get(name)
            if tool_filter and not tool_filter.is_tool_allowed(tool.name, server_name=srv):
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
        Invocation handler: Resolves, authorizes, and executes tools via supervisor.
        Execution sequence:
          1. Validate and resolve requested name to a single unique registered tool and owning server.
          2. Check for ambiguity (cross-server collision) and reject with clear guidance.
          3. Enforce ToolFilter against the resolved canonical tool and server identity.
          4. Dispatch that exact canonical tool to the supervisor.
          5. Handle unhandled tool errors or process crashes with data redaction.
        """
        raw_name = getattr(params, "name", "")
        tool_name = (raw_name or "").strip()
        if not tool_name:
            return CallToolResult(
                isError=True,
                content=[TextContent(type="text", text="Tool name cannot be empty.")],
            )

        # 1. Check for cross-server ambiguity
        if self.router.is_ambiguous_tool(tool_name):
            return CallToolResult(
                isError=True,
                content=[
                    TextContent(
                        type="text",
                        text=f"Ambiguous tool '{tool_name}'. Multiple servers provide this tool; use a namespaced name (e.g. 'server.{tool_name}').",
                    )
                ],
            )

        # 2. Resolve requested name to unique registered Tool and owning server
        canonical_tool, server_name = self.router.resolve_tool(tool_name)
        if not canonical_tool or not server_name:
            # Check if this unknown/unresolved name was explicitly denied to avoid disclosure
            if self.tool_filter and not self.tool_filter.is_tool_allowed(tool_name):
                return CallToolResult(
                    isError=True,
                    content=[
                        TextContent(
                            type="text",
                            text=f"Tool '{tool_name}' is prohibited by access policy.",
                        )
                    ],
                )
            return CallToolResult(
                isError=True,
                content=[
                    TextContent(
                        type="text",
                        text=f"Unknown tool '{tool_name}'.",
                    )
                ],
            )

        # 3. Apply ToolFilter to the resolved canonical tool name and server identity
        if self.tool_filter and not self.tool_filter.is_tool_allowed(canonical_tool.name, server_name=server_name):
            return CallToolResult(
                isError=True,
                content=[
                    TextContent(
                        type="text",
                        text=f"Tool '{tool_name}' is prohibited by access policy.",
                    )
                ],
            )

        # 4. Dispatch the exact authorized canonical tool
        try:
            raw_result = self.supervisor.call_tool(
                server_name=server_name,
                tool_name=canonical_tool.name,
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
