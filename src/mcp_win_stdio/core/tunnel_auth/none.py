"""
Unauthenticated provider for MWS remote tunnel.
Permits direct access for clients like ChatGPT (custom MCP without auth).
Mandates read_only permissions server-side.
"""

from typing import Any, Dict, Optional

from .base import AuthProvider


class NoneAuthProvider(AuthProvider):
    """
    Allows unauthenticated access to the MCP HTTP endpoint.
    Strictly requires read_only permissions at the gateway boundary.
    """

    def __init__(self):
        super().__init__(auth_mode="none")

    @property
    def requires_read_only(self) -> bool:
        """Unauthenticated tunnels are strictly restricted to read_only tools."""
        return True

    async def authenticate(self, request: Any) -> Optional[Any]:
        # Unauthenticated: allow all requests through
        return None

    def get_client_config(self, public_url: str) -> Dict[str, Any]:
        mcp_endpoint = f"{public_url}/mcp" if public_url else ""
        return {
            "mcpServers": {
                "mws": {
                    "url": mcp_endpoint,
                }
            }
        }

    async def shutdown(self) -> None:
        pass
