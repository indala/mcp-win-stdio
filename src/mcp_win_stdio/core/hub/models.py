"""
Data models and typed configuration structures for the MCP Hub.
"""

import fnmatch
import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class SecretReference:
    """Reference to an external secret in a provider."""

    provider: str  # "env" | "win_cred_manager"
    key: str

    def to_dict(self) -> Dict[str, str]:
        return {"provider": self.provider, "key": self.key}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SecretReference":
        if not isinstance(data, dict):
            raise ValueError("SecretReference must be a dictionary")
        provider = data.get("provider", "env").lower().strip()
        if provider not in ("env", "win_cred_manager"):
            raise ValueError(f"Unsupported secret provider: '{provider}'. Supported: 'env', 'win_cred_manager'")
        key = data.get("key", "").strip()
        if not key:
            raise ValueError("SecretReference requires a non-empty 'key'")
        return cls(provider=provider, key=key)


@dataclass
class ProfileConfig:
    """Connection profile configuration with separated parameters and secret references."""

    name: str
    type: Optional[str] = None
    parameters: Dict[str, Any] = field(default_factory=dict)
    secrets: Dict[str, SecretReference] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        res: Dict[str, Any] = {"name": self.name}
        if self.type:
            res["type"] = self.type
        res.update(self.parameters)
        if self.secrets:
            res["secrets"] = {k: v.to_dict() for k, v in self.secrets.items()}
        return res

    @classmethod
    def from_dict(cls, name: str, data: Dict[str, Any]) -> "ProfileConfig":
        if not isinstance(data, dict):
            raise ValueError(f"Profile '{name}' must be a dictionary")
        p_type = data.get("type")
        params = {}
        secrets = {}

        for k, v in data.items():
            if k in ("name", "type"):
                continue
            if k == "secrets" and isinstance(v, dict):
                for sk, sv in v.items():
                    secrets[sk] = SecretReference.from_dict(sv)
            elif isinstance(v, dict) and "provider" in v and "key" in v:
                secrets[k] = SecretReference.from_dict(v)
            elif k.endswith("_env") and isinstance(v, str):
                secret_field = k[:-4]
                secrets[secret_field] = SecretReference(provider="env", key=v)
            else:
                params[k] = v

        return cls(name=name, type=p_type, parameters=params, secrets=secrets)


@dataclass
class ServerProfileManifest:
    """Manifest containing named profiles and the default profile for a server."""

    schema_version: str = "1.0"
    default_profile: Optional[str] = None
    profiles: Dict[str, ProfileConfig] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "default_profile": self.default_profile,
            "profiles": {name: p.to_dict() for name, p in self.profiles.items()},
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ServerProfileManifest":
        if not isinstance(data, dict):
            raise ValueError("ServerProfileManifest must be a dictionary")
        version = str(data.get("schema_version", "1.0"))
        default_prof = data.get("default_profile")
        raw_profiles = data.get("profiles", {})
        if not isinstance(raw_profiles, dict):
            raise ValueError("'profiles' field must be a dictionary of profile definitions")

        profiles = {}
        for pname, pdata in raw_profiles.items():
            profiles[pname] = ProfileConfig.from_dict(name=pname, data=pdata)

        if default_prof and default_prof not in profiles:
            raise ValueError(
                f"default_profile '{default_prof}' is not defined in the profiles dictionary"
            )

        return cls(
            schema_version=version,
            default_profile=default_prof,
            profiles=profiles,
        )


@dataclass
class SupervisorConfig:
    """Supervisor parameters for an individual MCP server."""

    startup_timeout_seconds: float = 15.0
    shutdown_grace_seconds: float = 5.0
    max_restart_retries: int = 3
    restart_backoff_seconds: float = 2.0
    protocol_ping: bool = True
    probe_timeout_seconds: float = 5.0

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> "SupervisorConfig":
        if not data:
            return cls()
        if not isinstance(data, dict):
            raise ValueError("Supervisor configuration must be a dictionary")

        startup = float(data.get("startup_timeout_seconds", 15.0))
        if startup <= 0:
            raise ValueError(f"startup_timeout_seconds must be positive, got {startup}")

        grace = float(data.get("shutdown_grace_seconds", 5.0))
        if grace < 0:
            raise ValueError(f"shutdown_grace_seconds cannot be negative, got {grace}")

        retries = int(data.get("max_restart_retries", 3))
        if retries < 0:
            raise ValueError(f"max_restart_retries cannot be negative, got {retries}")

        backoff = float(data.get("restart_backoff_seconds", 2.0))
        if backoff < 0:
            raise ValueError(f"restart_backoff_seconds cannot be negative, got {backoff}")

        raw_ping = data.get("protocol_ping", True)
        if not isinstance(raw_ping, bool):
            raise ValueError("protocol_ping must be a boolean")

        probe_timeout = float(data.get("probe_timeout_seconds", 5.0))
        if probe_timeout <= 0:
            raise ValueError(f"probe_timeout_seconds must be positive, got {probe_timeout}")

        return cls(
            startup_timeout_seconds=startup,
            shutdown_grace_seconds=grace,
            max_restart_retries=retries,
            restart_backoff_seconds=backoff,
            protocol_ping=raw_ping,
            probe_timeout_seconds=probe_timeout,
        )


@dataclass
class ServerConfig:
    """Configuration for a registered MCP server in hub.yaml."""

    name: str
    command: str
    args: List[str] = field(default_factory=list)
    enabled: bool = True
    env: Dict[str, str] = field(default_factory=dict)
    supervisor: SupervisorConfig = field(default_factory=SupervisorConfig)

    @classmethod
    def from_dict(cls, name: str, data: Dict[str, Any]) -> "ServerConfig":
        if not isinstance(data, dict):
            raise ValueError(f"Server configuration for '{name}' must be a dictionary")

        inner_name = data.get("name")
        if inner_name and str(inner_name).lower().strip() != name.lower().strip():
            raise ValueError(f"Server name in definition '{inner_name}' does not match dictionary key '{name}'")

        cmd = data.get("command")
        if not isinstance(cmd, str) or not cmd.strip():
            raise ValueError(f"Server '{name}' requires a valid non-empty string 'command'")

        raw_args = data.get("args", [])
        if not isinstance(raw_args, list) or not all(isinstance(x, str) for x in raw_args):
            raise ValueError(f"Server '{name}' args must strictly be a list of strings")

        raw_enabled = data.get("enabled", True)
        if not isinstance(raw_enabled, bool):
            raise ValueError(f"Server '{name}' enabled must be a boolean (True/False)")

        raw_env = data.get("env", {})
        if not isinstance(raw_env, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in raw_env.items()):
            raise ValueError(f"Server '{name}' env must strictly be a dictionary of string key-value pairs")

        supervisor = SupervisorConfig.from_dict(data.get("supervisor"))

        return cls(
            name=name.lower().strip(),
            command=cmd.strip(),
            args=list(raw_args),
            enabled=raw_enabled,
            env=dict(raw_env),
            supervisor=supervisor,
        )


@dataclass
class ToolFilter:
    """Tool filtering rules. Deny rules take strict precedence over allow rules."""

    allow: List[str] = field(default_factory=list)
    deny: List[str] = field(default_factory=list)

    def is_tool_allowed(self, tool_name: str) -> bool:
        """Evaluate allow/deny rules against tool_name. deny always overrides allow."""
        tool = tool_name.lower().strip()

        # 1. Deny check (strict precedence, supports glob patterns like '*', '*secret*', 'srv.*')
        for d in self.deny:
            pattern = d.lower().strip()
            if fnmatch.fnmatchcase(tool, pattern):
                return False

        # 2. Allow check (supports glob patterns)
        if not self.allow:
            return True

        for a in self.allow:
            pattern = a.lower().strip()
            if fnmatch.fnmatchcase(tool, pattern):
                return True

        return False

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> "ToolFilter":
        if not data:
            return cls()
        if not isinstance(data, dict):
            raise ValueError("ToolFilter configuration must be a dictionary")

        raw_allow = data.get("allow", [])
        if not isinstance(raw_allow, list) or not all(isinstance(x, str) for x in raw_allow):
            raise ValueError("ToolFilter 'allow' must strictly be a list of strings")

        raw_deny = data.get("deny", [])
        if not isinstance(raw_deny, list) or not all(isinstance(x, str) for x in raw_deny):
            raise ValueError("ToolFilter 'deny' must strictly be a list of strings")

        return cls(
            allow=[x.strip() for x in raw_allow],
            deny=[x.strip() for x in raw_deny],
        )


@dataclass
class ProjectConfig:
    """
    Project-level declarative configuration (.mws/config.yaml).
    Only profile bindings and tool filters are permitted.
    Command/executable declarations are strictly forbidden at all nesting levels.
    """

    schema_version: str = "1.0"
    profile_bindings: Dict[str, str] = field(default_factory=dict)
    tool_filters: ToolFilter = field(default_factory=ToolFilter)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ProjectConfig":
        if not isinstance(data, dict):
            raise ValueError("Project configuration must be a dictionary")

        # Security invariant: prevent project configs from defining executables at ANY nesting level
        cls._scan_forbidden_keys(data)

        version = str(data.get("schema_version", "1.0"))
        bindings = data.get("profile_bindings", {})
        if not isinstance(bindings, dict):
            raise ValueError("profile_bindings must be a dictionary of server -> profile_name")
        if not all(isinstance(k, str) and isinstance(v, str) for k, v in bindings.items()):
            raise ValueError("profile_bindings keys and values must strictly be strings")

        filters = ToolFilter.from_dict(data.get("tool_filters"))

        return cls(
            schema_version=version,
            profile_bindings={k.lower().strip(): v.strip() for k, v in bindings.items()},
            tool_filters=filters,
        )

    @classmethod
    def _scan_forbidden_keys(cls, node: Any) -> None:
        forbidden = {"command", "cmd", "args", "executable", "servers", "script"}
        if isinstance(node, dict):
            for k, v in node.items():
                if str(k).lower().strip() in forbidden:
                    raise ValueError(f"Security violation: Project config cannot specify executable key '{k}'")
                cls._scan_forbidden_keys(v)
        elif isinstance(node, list):
            for item in node:
                cls._scan_forbidden_keys(item)


@dataclass
class HubConfig:
    """Complete global hub configuration (hub.yaml)."""

    schema_version: str = "1.0"
    mode: str = "hybrid"
    control_socket: str = r"\\.\pipe\mws-control"
    http_host: str = "127.0.0.1"
    http_port: int = 8080
    http_auth_token_env: str = "MWS_HTTP_AUTH_TOKEN"
    servers: Dict[str, ServerConfig] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "HubConfig":
        if not isinstance(data, dict):
            raise ValueError("Hub configuration must be a dictionary")
        version = str(data.get("schema_version", "1.0"))
        runtime = data.get("runtime", {})
        if not isinstance(runtime, dict):
            runtime = {}

        mode = runtime.get("mode", "hybrid").lower().strip()
        if mode not in ("hybrid", "embedded", "daemon"):
            raise ValueError(f"Invalid runtime mode '{mode}'. Must be one of: 'hybrid', 'embedded', 'daemon'")

        control_socket = runtime.get("control_socket", r"\\.\pipe\mws-control")

        http = runtime.get("http_bridge", {})
        if not isinstance(http, dict):
            http = {}
        http_host = str(http.get("host", "127.0.0.1")).strip()
        http_port = int(http.get("port", 8080))
        if not (1 <= http_port <= 65535):
            raise ValueError(f"Invalid http_port '{http_port}'. Must be between 1 and 65535")

        http_token_env = str(http.get("auth_token_env", "MWS_HTTP_AUTH_TOKEN")).strip()

        # Security invariant: Remote binding requires an explicit non-empty auth token variable
        # and requires that environment variable to be set and non-empty at runtime.
        if http_host not in ("127.0.0.1", "localhost", "::1"):
            if not http_token_env:
                raise ValueError(
                    f"Remote HTTP host binding '{http_host}' strictly requires a non-empty 'auth_token_env' for authentication."
                )
            token_val = os.environ.get(http_token_env, "").strip()
            if not token_val:
                raise ValueError(
                    f"Remote HTTP host binding '{http_host}' requires environment variable '{http_token_env}' to be set and non-empty."
                )

        raw_servers = data.get("servers", {})
        if not isinstance(raw_servers, dict):
            raise ValueError("'servers' field must be a dictionary of server configs")

        servers = {}
        for sname, sdata in raw_servers.items():
            servers[sname.lower().strip()] = ServerConfig.from_dict(name=sname, data=sdata)

        return cls(
            schema_version=version,
            mode=mode,
            control_socket=control_socket,
            http_host=http_host,
            http_port=http_port,
            http_auth_token_env=http_token_env,
            servers=servers,
        )


class ServerState(str, Enum):
    """Lifecycle states of a supervised MCP server instance."""

    STOPPED = "stopped"
    STARTING = "starting"
    INITIALIZING = "initializing"
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    FAILED = "failed"
    STOPPING = "stopping"


@dataclass(frozen=True)
class ProcessInstanceInfo:
    """Immutable snapshot of a supervised server process instance."""

    instance_id: int
    server_name: str
    pid: Optional[int]
    state: ServerState
    started_at: Optional[float] = None
    last_heartbeat: Optional[float] = None
    restart_count: int = 0
    consecutive_crashes: int = 0
    last_exit_code: Optional[int] = None
    last_error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "instance_id": self.instance_id,
            "server_name": self.server_name,
            "pid": self.pid,
            "state": self.state.value,
            "started_at": self.started_at,
            "last_heartbeat": self.last_heartbeat,
            "restart_count": self.restart_count,
            "consecutive_crashes": self.consecutive_crashes,
            "last_exit_code": self.last_exit_code,
            "last_error": self.last_error,
        }


@dataclass(frozen=True)
class LifecycleEvent:
    """Event emitted upon state transition of a supervised instance."""

    server_name: str
    instance_id: int
    old_state: ServerState
    new_state: ServerState
    timestamp: float
    reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "server_name": self.server_name,
            "instance_id": self.instance_id,
            "old_state": self.old_state.value,
            "new_state": self.new_state.value,
            "timestamp": self.timestamp,
            "reason": self.reason,
        }
