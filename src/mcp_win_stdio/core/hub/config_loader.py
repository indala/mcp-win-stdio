"""
Central Configuration Loader for MCP Hub.
Discovers, validates, and loads hub.yaml configuration following a strict 5-tier
precedence ladder, and bridges existing connection profiles (~/.mcp-win-stdio/)
into ProfileManager without duplicating connection credentials.
"""

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Tuple, Union

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore[assignment]

from mcp_win_stdio.core.config import (
    DB_CONNECTIONS_FILE,
    SSH_HOSTS_FILE,
    USER_DIR,
)
from mcp_win_stdio.core.hub.models import (
    HubConfig,
    ProfileConfig,
    ServerProfileManifest,
)
from mcp_win_stdio.core.hub.profiles import ProfileManager

logger = logging.getLogger(__name__)

DEFAULT_HUB_YAML_TEMPLATE = """# ==============================================================================
# mcp-win-stdio Hub Configuration (hub.yaml)
# Schema Version: 1.0
# ==============================================================================

schema_version: "1.0"

runtime:
  mode: hybrid  # hybrid | embedded | daemon
  control_socket: "\\\\\\\\.\\\\pipe\\\\mws-control"
  http_bridge:
    host: 127.0.0.1  # Loopback by default for security
    port: 8080
    auth_token_env: MWS_HTTP_AUTH_TOKEN

tools:
  allow:
    - "*"
  deny:
    - "*secret*"

servers: {}
"""


@dataclass(frozen=True)
class LoadedHubConfig:
    """Holds the validated HubConfig along with its discovery metadata and profile manager."""

    config: HubConfig
    source_path: Optional[Path]
    source_tier: str
    profile_manager: ProfileManager


def resolve_config_path(
    cli_path: Optional[Union[str, Path]] = None,
    cwd: Optional[Path] = None,
    user_dir: Optional[Path] = None,
) -> Tuple[Optional[Path], str]:
    """
    Resolve the selected hub configuration file using strict 5-tier precedence:
      Tier 1: Explicit CLI path (--config PATH)
      Tier 2: Environment variable (MWS_HUB_CONFIG)
      Tier 3: Project-local (.mws/hub.yaml, .mws/hub.yml, hub.yaml, hub.yml)
      Tier 4: User-global (~/.mcp-win-stdio/hub.yaml, hub.json)
      Tier 5: Implicit default fallback (loopback default)

    Explicit paths (Tier 1 & 2) that do not exist raise FileNotFoundError immediately.
    If both YAML and legacy JSON exist in user-global directory, YAML takes precedence
    and a warning is logged.
    """
    # Tier 1: Explicit CLI argument
    if cli_path is not None:
        p = Path(cli_path).resolve()
        if not p.exists():
            raise FileNotFoundError(f"Explicitly specified configuration file not found: '{cli_path}'")
        return p, "cli_argument"

    # Tier 2: Environment variable MWS_HUB_CONFIG
    env_config = os.environ.get("MWS_HUB_CONFIG", "").strip()
    if env_config:
        p = Path(env_config).resolve()
        if not p.exists():
            raise FileNotFoundError(
                f"Configuration file specified in MWS_HUB_CONFIG not found: '{env_config}'"
            )
        return p, "environment_variable"

    # Tier 3: Project-local discovery in cwd
    base_cwd = (cwd or Path.cwd()).resolve()
    project_candidates = [
        base_cwd / ".mws" / "hub.yaml",
        base_cwd / ".mws" / "hub.yml",
        base_cwd / "hub.yaml",
        base_cwd / "hub.yml",
    ]
    for cand in project_candidates:
        if cand.is_file():
            return cand, "project_local"

    # Tier 4: User-global discovery in user_dir
    base_user_dir = (user_dir or USER_DIR).resolve()
    yaml_candidates = [
        base_user_dir / "hub.yaml",
        base_user_dir / "hub.yml",
    ]
    yaml_found: Optional[Path] = None
    for cand in yaml_candidates:
        if cand.is_file():
            yaml_found = cand
            break

    json_cand = base_user_dir / "hub.json"
    json_found = json_cand.is_file()

    if yaml_found and json_found:
        logger.warning(
            "Both '%s' and '%s' exist in user directory; '%s' takes precedence.",
            yaml_found,
            json_cand,
            yaml_found,
        )
        return yaml_found, "user_global"
    elif yaml_found:
        return yaml_found, "user_global"
    elif json_found:
        return json_cand, "user_global_legacy"

    # Tier 5: Implicit default fallback
    return None, "default_implicit"


def sync_connection_profiles(
    profile_manager: ProfileManager,
    user_dir: Optional[Path] = None,
) -> None:
    """
    Load established connection profiles from ~/.mcp-win-stdio/ (db_connections.json,
    ssh_hosts.json) and register them as ServerProfileManifests in ProfileManager.
    Guarantees zero duplication of credentials into hub.yaml.
    """
    base_user_dir = (user_dir or USER_DIR).resolve()

    # 1. Database Connections -> 'db' & 'excel-db' servers
    db_file = base_user_dir / "db_connections.json" if user_dir else DB_CONNECTIONS_FILE
    if db_file.exists():
        try:
            with open(db_file, "r", encoding="utf-8") as f:
                db_data = json.load(f)
            if isinstance(db_data, dict):
                connections = db_data.get("connections", {})
                default_alias = db_data.get("default")
                if connections and isinstance(connections, dict):
                    profiles: Dict[str, ProfileConfig] = {}
                    for alias, cdata in connections.items():
                        if isinstance(cdata, dict):
                            profiles[alias] = ProfileConfig.from_dict(alias, cdata)
                        elif isinstance(cdata, str):
                            profiles[alias] = ProfileConfig(name=alias, parameters={"url": cdata})

                    manifest = ServerProfileManifest(
                        default_profile=default_alias,
                        profiles=profiles,
                    )
                    profile_manager.register_manifest("db", manifest)
                    profile_manager.register_manifest("excel-db", manifest)
        except Exception as e:
            logger.warning("Failed loading database connection profiles from '%s': %s", db_file, e)

    # 2. SSH Remote Hosts -> 'ssh' server
    ssh_file = base_user_dir / "ssh_hosts.json" if user_dir else SSH_HOSTS_FILE
    if ssh_file.exists():
        try:
            with open(ssh_file, "r", encoding="utf-8") as f:
                ssh_data = json.load(f)
            if isinstance(ssh_data, dict):
                hosts = ssh_data.get("hosts", {})
                default_alias = ssh_data.get("default") or ssh_data.get("active_host")
                if hosts and isinstance(hosts, dict):
                    profiles = {}
                    for alias, hdata in hosts.items():
                        if isinstance(hdata, dict):
                            profiles[alias] = ProfileConfig.from_dict(alias, hdata)

                    manifest = ServerProfileManifest(
                        default_profile=default_alias,
                        profiles=profiles,
                    )
                    profile_manager.register_manifest("ssh", manifest)
        except Exception as e:
            logger.warning("Failed loading SSH host profiles from '%s': %s", ssh_file, e)


def load_hub_config(
    cli_path: Optional[Union[str, Path]] = None,
    cwd: Optional[Path] = None,
    user_dir: Optional[Path] = None,
    profile_manager: Optional[ProfileManager] = None,
) -> LoadedHubConfig:
    """
    Discover, load, and validate the hub configuration.
    Bridges existing connection profiles into ProfileManager and returns LoadedHubConfig.
    """
    config_path, source_tier = resolve_config_path(
        cli_path=cli_path,
        cwd=cwd,
        user_dir=user_dir,
    )

    if config_path is not None:
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception as e:
            raise ValueError(f"Failed reading configuration file '{config_path}': {e}") from e

        if config_path.suffix.lower() in (".yaml", ".yml"):
            if yaml is None:
                raise ImportError("PyYAML is required to parse YAML hub configuration files.")
            try:
                raw_data = yaml.safe_load(content)
            except Exception as e:
                raise ValueError(f"Invalid YAML in configuration file '{config_path}': {e}") from e
        else:
            try:
                raw_data = json.loads(content)
            except Exception as e:
                raise ValueError(f"Invalid JSON in configuration file '{config_path}': {e}") from e

        if not isinstance(raw_data, dict):
            raise ValueError(f"Root of configuration file '{config_path}' must be a dictionary.")

        hub_config = HubConfig.from_dict(raw_data)
    else:
        # Default safe configuration (loopback, 8080, no servers blindly enabled)
        hub_config = HubConfig()

    pm = profile_manager or ProfileManager()
    sync_connection_profiles(pm, user_dir=user_dir)

    return LoadedHubConfig(
        config=hub_config,
        source_path=config_path,
        source_tier=source_tier,
        profile_manager=pm,
    )


def generate_default_hub_config(
    target_path: Optional[Union[str, Path]] = None,
    overwrite: bool = False,
) -> str:
    """
    Generate a well-documented default hub.yaml template.
    If target_path is specified, writes to disk (failing closed if file exists and overwrite=False).
    Returns the template string.
    """
    template = DEFAULT_HUB_YAML_TEMPLATE

    if target_path is not None:
        p = Path(target_path).resolve()
        if p.exists() and not overwrite:
            raise FileExistsError(
                f"Configuration template already exists at '{p}'. Set overwrite=True to overwrite."
            )
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            f.write(template)

    return template
