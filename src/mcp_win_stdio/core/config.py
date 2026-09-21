"""
Core configuration and single-source path management for mcp-win-stdio.
"""

import json
import os
from pathlib import Path
from typing import Any, Dict

# Standard single-source directory: ~/.mcp-win-stdio/
USER_HOME = Path.home()
INDALA_DIR = USER_HOME / ".mcp-win-stdio"
PLUGINS_DIR = INDALA_DIR / "plugins"
LOGS_DIR = INDALA_DIR / "logs"
EXPORTS_DIR = INDALA_DIR / "exports"
CONFIG_FILE = INDALA_DIR / "config.json"


def ensure_workspace_dirs() -> Dict[str, Path]:
    """Ensure all core directories exist and return paths."""
    for d in (INDALA_DIR, PLUGINS_DIR, LOGS_DIR, EXPORTS_DIR):
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
        "root": INDALA_DIR,
        "plugins": PLUGINS_DIR,
        "logs": LOGS_DIR,
        "exports": EXPORTS_DIR,
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
