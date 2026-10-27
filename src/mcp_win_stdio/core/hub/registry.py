"""
Hub Registry: Manages server registrations, schema validation, and atomic configuration reload.
"""

import copy
import json
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import yaml  # type: ignore[import-untyped]
except ImportError:
    yaml = None

from .models import HubConfig, ServerConfig, SupervisorConfig, ToolFilter


class RegistryValidationError(ValueError):
    """Raised when registry configuration fails validation."""

    pass


class HubRegistry:
    """
    Thread-safe registry for MCP server declarations with atomic reload guarantees.
    Returns defensive snapshots on reads to prevent caller mutation of internal state.
    Every state change advances generation under the registry lock.
    """

    def __init__(self, config: Optional[HubConfig] = None) -> None:
        self._lock = threading.RLock()
        self._config: HubConfig = copy.deepcopy(config) if config else HubConfig()
        self._generation: int = 1

    @property
    def config(self) -> HubConfig:
        with self._lock:
            return copy.deepcopy(self._config)

    def get_generation(self) -> int:
        with self._lock:
            return self._generation

    def load_from_dict(self, data: Dict[str, Any]) -> bool:
        """
        Atomically validate and update registry configuration from a dictionary.
        Returns True if configuration changed (advancing generation), False if identical.
        Raises RegistryValidationError if validation fails; previous config and generation remain unchanged.
        """
        try:
            candidate = HubConfig.from_dict(data)
            self._validate_candidate(candidate)
        except Exception as exc:
            raise RegistryValidationError(f"Configuration validation failed: {exc}") from exc

        with self._lock:
            if candidate == self._config:
                return False
            self._config = copy.deepcopy(candidate)
            self._generation += 1
            return True

    def load_from_file(self, path: Path) -> bool:
        """
        Atomically load and validate configuration from a YAML or JSON file.
        On failure, preserves the last active configuration and generation.
        """
        if not path.exists():
            raise FileNotFoundError(f"Configuration file does not exist: {path}")

        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()

            if path.suffix.lower() in (".yaml", ".yml") and yaml is not None:
                raw_data = yaml.safe_load(content)
            else:
                raw_data = json.loads(content)

            if not isinstance(raw_data, dict):
                raise RegistryValidationError("Root of configuration must be a dictionary.")

            return self.load_from_dict(raw_data)
        except RegistryValidationError:
            raise
        except Exception as exc:
            raise RegistryValidationError(f"Failed parsing configuration file '{path}': {exc}") from exc

    def _validate_candidate(self, candidate: HubConfig) -> None:
        """Enforce validation rules on candidate configuration."""
        if not candidate.schema_version:
            raise RegistryValidationError("schema_version is required.")

        for name, srv in candidate.servers.items():
            if not srv.name or srv.name != name:
                raise RegistryValidationError(f"Server key '{name}' does not match server.name '{srv.name}'.")
            if not srv.command:
                raise RegistryValidationError(f"Server '{name}' has an empty or missing command.")
            if srv.supervisor.startup_timeout_seconds <= 0:
                raise RegistryValidationError(
                    f"Server '{name}' startup_timeout_seconds must be positive, got {srv.supervisor.startup_timeout_seconds}"
                )

    def get_server(self, name: str) -> Optional[ServerConfig]:
        """Return a defensive copy of the registered server configuration."""
        clean = name.lower().strip()
        with self._lock:
            srv = self._config.servers.get(clean)
            return copy.deepcopy(srv) if srv else None

    def list_servers(self, enabled_only: bool = False) -> List[ServerConfig]:
        """Return defensive copies of all registered server configurations."""
        with self._lock:
            servers = list(self._config.servers.values())
            if enabled_only:
                return [copy.deepcopy(s) for s in servers if s.enabled]
            return [copy.deepcopy(s) for s in servers]

    def register_server(self, srv: ServerConfig) -> bool:
        """Register or update a server. Returns True and advances generation if changed."""
        clean = srv.name.lower().strip()
        with self._lock:
            existing = self._config.servers.get(clean)
            if existing == srv:
                return False
            self._config.servers[clean] = copy.deepcopy(srv)
            self._generation += 1
            return True

    def unregister_server(self, name: str) -> bool:
        """Unregister a server. Advances generation if the server was removed."""
        clean = name.lower().strip()
        with self._lock:
            if clean in self._config.servers:
                del self._config.servers[clean]
                self._generation += 1
                return True
            return False

    def is_server_enabled(self, name: str) -> bool:
        clean = name.lower().strip()
        with self._lock:
            srv = self._config.servers.get(clean)
            return srv.enabled if srv else False

    def set_server_enabled(self, name: str, enabled: bool) -> bool:
        """Enable or disable a server. Advances generation if enabled status changed."""
        clean = name.lower().strip()
        with self._lock:
            srv = self._config.servers.get(clean)
            if srv and srv.enabled != enabled:
                srv.enabled = enabled
                self._generation += 1
                return True
            return False


# Global default registry singleton
GLOBAL_HUB_REGISTRY = HubRegistry()
