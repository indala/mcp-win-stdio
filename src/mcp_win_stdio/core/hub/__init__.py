"""
Hub core subsystem: Registry, Configuration, Profiles, and Secrets management.
"""

from .auth import BearerAuthMiddleware, SessionManager
from .bridge import StreamableHttpBridge, ToolRouter
from .config_loader import (
    LoadedHubConfig,
    generate_default_hub_config,
    load_hub_config,
    resolve_config_path,
    sync_connection_profiles,
)
from .control import (
    HubControlClient,
    HubControlServer,
    HubInstanceManager,
    HubInstanceMetadata,
    is_pid_alive,
)
from .lifecycle import (
    VALID_TRANSITIONS,
    InvalidStateTransitionError,
    ProcessInstance,
)
from .models import (
    HubConfig,
    LifecycleEvent,
    ProcessInstanceInfo,
    ProfileConfig,
    ProjectConfig,
    SecretReference,
    ServerConfig,
    ServerProfileManifest,
    ServerState,
    SupervisorConfig,
    ToolFilter,
)
from .orchestrator import (
    HubLifecycleState,
    HubOrchestrator,
    HubStatusInfo,
)
from .profiles import ProfileManager, ProfileNotFoundError
from .registry import HubRegistry, RegistryValidationError
from .secrets import (
    EnvSecretProvider,
    SecretProvider,
    SecretRegistry,
    WindowsCredentialManagerProvider,
    redact_sensitive_data,
)
from .security import (
    WindowsSecurityError,
    get_current_user_sid,
    secure_directory,
    secure_file,
    verify_security_descriptor,
    write_secure_json_file,
)
from .supervisor import ProcessSupervisor, ServerNotFoundError
from .win32_job import Win32JobObject

__all__ = [
    "BearerAuthMiddleware",
    "EnvSecretProvider",
    "HubConfig",
    "HubControlClient",
    "HubControlServer",
    "HubInstanceMetadata",
    "HubInstanceManager",
    "HubLifecycleState",
    "HubOrchestrator",
    "HubRegistry",
    "HubStatusInfo",
    "InvalidStateTransitionError",
    "LifecycleEvent",
    "LoadedHubConfig",
    "ProcessInstance",
    "ProcessInstanceInfo",
    "ProcessSupervisor",
    "ProfileConfig",
    "ProfileManager",
    "ProfileNotFoundError",
    "ProjectConfig",
    "RegistryValidationError",
    "SecretProvider",
    "SecretReference",
    "SecretRegistry",
    "ServerConfig",
    "ServerNotFoundError",
    "ServerProfileManifest",
    "ServerState",
    "SessionManager",
    "StreamableHttpBridge",
    "SupervisorConfig",
    "ToolFilter",
    "ToolRouter",
    "VALID_TRANSITIONS",
    "Win32JobObject",
    "WindowsCredentialManagerProvider",
    "WindowsSecurityError",
    "generate_default_hub_config",
    "get_current_user_sid",
    "is_pid_alive",
    "load_hub_config",
    "redact_sensitive_data",
    "resolve_config_path",
    "secure_directory",
    "secure_file",
    "sync_connection_profiles",
    "verify_security_descriptor",
    "write_secure_json_file",
]
