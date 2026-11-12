"""
Base AuthProvider interface for MWS remote tunnel authentication.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional


class AuthProvider(ABC):
    """
    Abstract base class for MWS tunnel authentication providers.
    Decouples authentication mechanics from tunnel lifecycle and tool execution.
    """

    def __init__(self, auth_mode: str):
        self.auth_mode = auth_mode

    @property
    def requires_read_only(self) -> bool:
        """Indicates whether this auth mode strictly mandates read_only permissions."""
        return False

    @abstractmethod
    async def authenticate(self, request: Any) -> Optional[Any]:
        """
        Authenticate an incoming HTTP request.
        Returns None if request is accepted, or an HTTP response (e.g. JSONResponse 401) if rejected.
        """
        raise NotImplementedError

    @abstractmethod
    def get_client_config(self, public_url: str) -> Dict[str, Any]:
        """
        Return the client configuration dictionary appropriate for this authentication mode.
        """
        raise NotImplementedError

    async def shutdown(self) -> None:
        """Clean up provider credentials, timers, or session state on tunnel stop."""
        pass
