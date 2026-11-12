"""
MWS Remote Tunnel Authentication Providers.
Provides modular, decoupled authentication implementations for MWS public HTTP tunnels.
"""

from typing import Optional

from .base import AuthProvider
from .bearer import BearerAuthProvider
from .none import NoneAuthProvider
from .oauth import OAuthProvider


def create_auth_provider(auth_mode: str = "bearer", token: Optional[str] = None, **kwargs) -> AuthProvider:
    """
    Factory function to initialize the requested AuthProvider.
    Supported auth_modes: 'bearer', 'none', 'oauth'.
    """
    mode = (auth_mode or "bearer").lower().strip()
    if mode == "bearer":
        return BearerAuthProvider(token=token)
    elif mode == "none":
        return NoneAuthProvider(allow_sensitive_reads=bool(kwargs.get("allow_sensitive_reads", False)))
    elif mode == "oauth":
        return OAuthProvider(**kwargs)
    else:
        raise ValueError(f"Unknown auth_mode '{auth_mode}'. Supported modes: 'bearer', 'none', 'oauth'")


__all__ = [
    "AuthProvider",
    "BearerAuthProvider",
    "NoneAuthProvider",
    "OAuthProvider",
    "create_auth_provider",
]
