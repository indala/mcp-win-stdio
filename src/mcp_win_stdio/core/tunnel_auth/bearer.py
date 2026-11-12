"""
Bearer token authentication provider for MWS remote tunnel.
Maintains backward compatibility with static Bearer credentials.
"""

import secrets
from typing import Any, Dict, Optional

from starlette.responses import JSONResponse

from .base import AuthProvider


class BearerAuthProvider(AuthProvider):
    """
    Validates incoming HTTP requests using a constant-time Bearer token check.
    """

    def __init__(self, token: Optional[str] = None):
        super().__init__(auth_mode="bearer")
        self.token = (token or secrets.token_urlsafe(32)).strip()

    async def authenticate(self, request: Any) -> Optional[Any]:
        auth_header = ""
        if hasattr(request, "headers") and request.headers is not None:
            for k, v in request.headers.items():
                if k.lower() == "authorization":
                    auth_header = v or ""
                    break

        if not auth_header.startswith("Bearer "):
            return JSONResponse(
                {
                    "error": "Unauthorized",
                    "message": "Missing or malformed Authorization header. Expected 'Bearer <token>'.",
                },
                status_code=401,
            )

        received_token = auth_header[7:].strip()
        if not secrets.compare_digest(received_token, self.token):
            return JSONResponse(
                {
                    "error": "Unauthorized",
                    "message": "Invalid Bearer token.",
                },
                status_code=401,
            )

        return None

    def get_client_config(self, public_url: str) -> Dict[str, Any]:
        mcp_endpoint = f"{public_url}/mcp" if public_url else ""
        return {
            "mcpServers": {
                "mws": {
                    "url": mcp_endpoint,
                    "headers": {
                        "Authorization": f"Bearer {self.token}",
                    },
                }
            }
        }

    async def shutdown(self) -> None:
        # Invalidate credential reference on shutdown
        self.token = ""
