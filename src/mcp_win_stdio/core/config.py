"""
Core configuration, hierarchical configuration, and single-source path management for mcp-win-stdio.
"""

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

# Standard single-source directory: ~/.mcp-win-stdio/
USER_HOME = Path.home()
USER_DIR = USER_HOME / ".mcp-win-stdio"
USER_DIR_ALT = USER_HOME / ".mws"
PLUGINS_DIR = USER_DIR / "plugins"
LOGS_DIR = USER_DIR / "logs"
EXPORTS_DIR = USER_DIR / "exports"
KEYS_DIR = USER_DIR / "keys"
WORKFLOWS_DIR = USER_DIR / "workflows"
CONFIG_FILE = USER_DIR / "config.json"
DB_CONNECTIONS_FILE = USER_DIR / "db_connections.json"
SSH_HOSTS_FILE = USER_DIR / "ssh_hosts.json"
GIT_REPOS_FILE = USER_DIR / "git_repos.json"
TSC_PROJECTS_FILE = USER_DIR / "tsc_projects.json"
RAG_DATA_DIR = USER_DIR / "rag_stores"
SERVER_CUSTOM_FILE = USER_DIR / "server_custom.json"
SERVER_CACHE_FILE = USER_DIR / "server_cache.json"
HUB_FILE = USER_DIR / "hub.yaml"
HUB_FILE_JSON = USER_DIR / "hub.json"
SERVERS_DIR = USER_DIR / "servers"

DEFAULT_SYSTEM_CONFIG: Dict[str, Any] = {
    "version": "0.4.6",
    "mode": "read_write",              # "read_write" | "read_only"
    "safe_writes": True,               # blocks naked UPDATE/DELETE without WHERE and TRUNCATE without allow_unfiltered
    "require_confirm_on_prod": False,  # optional user prompt before executing on prod env (default false)
    "default_client": "all",
    "log_level": "INFO",
    "installed_servers": {},
    "tunnel": {
        "mode": "read_only",           # default remote security mode
        "port": 8080,                  # local bridge port
        "token": None,                 # optional static bearer token; if None, random token is generated
        "host": "127.0.0.1",
    },
}


def ensure_workspace_dirs() -> Dict[str, Path]:
    """Ensure all core directories exist and return paths."""
    for d in (USER_DIR, PLUGINS_DIR, LOGS_DIR, EXPORTS_DIR, KEYS_DIR, WORKFLOWS_DIR, SERVERS_DIR):
        d.mkdir(parents=True, exist_ok=True)
    if not CONFIG_FILE.exists():
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_SYSTEM_CONFIG, f, indent=2)
    return {
        "root": USER_DIR,
        "plugins": PLUGINS_DIR,
        "logs": LOGS_DIR,
        "exports": EXPORTS_DIR,
        "keys": KEYS_DIR,
        "config": CONFIG_FILE,
    }


def find_workspace_dir(start_path: Optional[Path] = None) -> Optional[Path]:
    """
    Find active workspace directory by walking up from start_path (or cwd).
    Looks for .mws, .mcp-win-stdio, .git, or .mcp.json markers.
    """
    curr = (start_path or Path.cwd()).resolve()
    for parent in [curr] + list(curr.parents):
        if (parent / ".mws").is_dir() or (parent / ".mcp-win-stdio").is_dir():
            return parent
        if (parent / ".mws" / "config.json").is_file() or (parent / ".mcp-win-stdio" / "config.json").is_file():
            return parent
        if (parent / ".mcp.json").is_file() or (parent / ".git").is_dir():
            return parent
    return None


def get_workspace_config_path(workspace_dir: Optional[Path] = None) -> Tuple[Optional[Path], bool]:
    """
    Return (config_path, exists) for the workspace scope.
    Checks .mws/config.json then .mcp-win-stdio/config.json.
    """
    ws = workspace_dir or find_workspace_dir()
    if not ws:
        return None, False

    mws_cfg = ws / ".mws" / "config.json"
    if mws_cfg.is_file():
        return mws_cfg, True

    legacy_cfg = ws / ".mcp-win-stdio" / "config.json"
    if legacy_cfg.is_file():
        return legacy_cfg, True

    # Default to .mws/config.json if neither exists yet
    return ws / ".mws" / "config.json", False


def load_config() -> Dict[str, Any]:
    """Load base global configuration from ~/.mcp-win-stdio/config.json."""
    ensure_workspace_dirs()
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            merged = dict(DEFAULT_SYSTEM_CONFIG)
            merged.update(data)
            return merged
    except Exception:
        return dict(DEFAULT_SYSTEM_CONFIG)


def save_config(cfg: Dict[str, Any], scope: str = "global", workspace_dir: Optional[Path] = None) -> Path:
    """
    Save configuration to either global or workspace scope.
    scope: 'global' | 'workspace'
    """
    if scope.lower() == "workspace":
        target_path, _ = get_workspace_config_path(workspace_dir)
        if not target_path:
            ws = workspace_dir or Path.cwd()
            target_path = ws / ".mws" / "config.json"
        target_path.parent.mkdir(parents=True, exist_ok=True)
        with open(target_path, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
        return target_path

    ensure_workspace_dirs()
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)
    return CONFIG_FILE


def load_workspace_config(workspace_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Load configuration strictly from workspace .mws/config.json (or .mcp-win-stdio/config.json)."""
    cfg_path, exists = get_workspace_config_path(workspace_dir)
    if exists and cfg_path:
        try:
            with open(cfg_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def load_hierarchical_config(workspace_dir: Optional[Path] = None) -> Dict[str, Any]:
    """
    Load resolved configuration merging Global (~/.mcp-win-stdio/config.json)
    with Workspace (.mws/config.json or .mcp-win-stdio/config.json).
    Workspace values override global values.
    """
    global_cfg = load_config()
    ws_cfg = load_workspace_config(workspace_dir)
    cfg_path, ws_exists = get_workspace_config_path(workspace_dir)

    merged = dict(global_cfg)
    for k, v in ws_cfg.items():
        if isinstance(v, dict) and isinstance(merged.get(k), dict):
            sub = dict(merged[k])
            sub.update(v)
            merged[k] = sub
        else:
            merged[k] = v

    merged["_resolved_sources"] = {
        "global_path": str(CONFIG_FILE),
        "workspace_path": str(cfg_path) if cfg_path else None,
        "workspace_active": ws_exists,
    }
    return merged


def get_effective_mode(workspace_dir: Optional[Path] = None) -> str:
    """Return effective access mode ('read_write' or 'read_only') from hierarchical config."""
    cfg = load_hierarchical_config(workspace_dir)
    return cfg.get("mode", "read_write").lower().strip()


def is_safe_writes_enabled(workspace_dir: Optional[Path] = None) -> bool:
    """Check if safe_writes guardrail is enabled (default True)."""
    cfg = load_hierarchical_config(workspace_dir)
    return bool(cfg.get("safe_writes", True))


def is_require_confirm_on_prod_enabled(workspace_dir: Optional[Path] = None) -> bool:
    """Check if require_confirm_on_prod is enabled (default False)."""
    cfg = load_hierarchical_config(workspace_dir)
    return bool(cfg.get("require_confirm_on_prod", False))


def get_tunnel_config(workspace_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Return effective tunnel configuration merged from hierarchical config."""
    cfg = load_hierarchical_config(workspace_dir)
    default_tunnel = dict(DEFAULT_SYSTEM_CONFIG["tunnel"])
    tunnel_cfg = cfg.get("tunnel")
    if isinstance(tunnel_cfg, dict):
        default_tunnel.update(tunnel_cfg)
    return default_tunnel


