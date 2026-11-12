"""
OAuth 2.0 / 2.1 Provider placeholder for Phase 2.
"""

from typing import Any, Dict, Optional

from .base import AuthProvider


class OAuthProvider(AuthProvider):
    """
    Placeholder for Phase 2 OAuth 2.0 / 2.1 provider (RFC 8414, RFC 9728, PKCE S256).
    """

    def __init__(self, **kwargs: Any):
        super().__init__(auth_mode="oauth")
        raise NotImplementedError(
            "OAuth authentication provider is reserved for Phase 2. "
            "Please use auth_mode='bearer' or auth_mode='none' in Phase 1."
        )

    async def authenticate(self, request: Any) -> Optional[Any]:
        raise NotImplementedError

    def get_client_config(self, public_url: str) -> Dict[str, Any]:
        raise NotImplementedError

    async def shutdown(self) -> None:
        pass
