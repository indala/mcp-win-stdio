"""
Core configuration and single-source path management for mcp-win-stdio.
"""

import json
from pathlib import Path
from typing import Any, Dict

# Standard single-source directory: ~/.mcp-win-stdio/
USER_HOME = Path.home()
USER_DIR = USER_HOME / ".mcp-win-stdio"
INDALA_DIR = USER_DIR  # Backwards compatibility alias
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


def ensure_workspace_dirs() -> Dict[str, Path]:
    """Ensure all core directories exist and return paths."""
    for d in (USER_DIR, PLUGINS_DIR, LOGS_DIR, EXPORTS_DIR, KEYS_DIR, WORKFLOWS_DIR):
        d.mkdir(parents=True, exist_ok=True)
    if not CONFIG_FILE.exists():
        default_config = {
            "version": "0.1.0",
            "default_client": "all",
            "installed_servers": {},
            "log_level": "INFO",
        }
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(default_config, f, indent=2)
    return {
        "root": USER_DIR,
        "plugins": PLUGINS_DIR,
        "logs": LOGS_DIR,
        "exports": EXPORTS_DIR,
        "keys": KEYS_DIR,
        "config": CONFIG_FILE,
    }


def load_config() -> Dict[str, Any]:
    """Load configuration from ~/.mcp-win-stdio/config.json."""
    ensure_workspace_dirs()
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_config(cfg: Dict[str, Any]) -> None:
    """Save configuration to ~/.mcp-win-stdio/config.json."""
    ensure_workspace_dirs()
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)
