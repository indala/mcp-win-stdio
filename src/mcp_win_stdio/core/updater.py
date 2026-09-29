"""
Automatic PyPI version checking and update engine for mcp-win-stdio.
"""

import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import urllib.request
from typing import Any, Dict, Optional, Tuple

from mcp_win_stdio.core.config import INDALA_DIR, ensure_workspace_dirs

VERSION_CACHE_FILE = INDALA_DIR / "version_cache.json"
PYPI_URL = "https://pypi.org/pypi/mcp-win-stdio/json"
CACHE_TTL_SECONDS = 21600  # 6 hours


def parse_version(ver_str: str) -> Tuple[int, ...]:
    """Parse semver-like version string into integer tuple for accurate comparison."""
    if not ver_str:
        return (0,)
    # Extract only numeric digit groups
    nums = re.findall(r"\d+", ver_str)
    return tuple(int(x) for x in nums) if nums else (0,)


def fetch_latest_pypi_version(timeout: float = 1.5) -> Optional[str]:
    """Fetch latest package version from PyPI with a strict timeout."""
    try:
        req = urllib.request.Request(
            PYPI_URL,
            headers={"User-Agent": "mcp-win-stdio-updater"}
        )
        with urllib.request.urlopen(req, timeout=timeout) as response:
            if response.status == 200:
                data = json.loads(response.read().decode("utf-8"))
                return data.get("info", {}).get("version")
    except Exception:
        pass
    return None


def get_cached_or_latest_version(force: bool = False, timeout: float = 1.5) -> Optional[str]:
    """Retrieve the latest version using local cache or live PyPI request."""
    ensure_workspace_dirs()
    now = time.time()

    # Read existing cache if valid
    if not force and VERSION_CACHE_FILE.exists():
        try:
            with open(VERSION_CACHE_FILE, "r", encoding="utf-8") as f:
                cached = json.load(f)
            last_checked = cached.get("last_checked", 0)
            latest_ver = cached.get("latest_version")
            if latest_ver and (now - last_checked) < CACHE_TTL_SECONDS:
                return latest_ver
        except Exception:
            pass

    # Fetch fresh from PyPI
    latest_ver = fetch_latest_pypi_version(timeout=timeout)
    if latest_ver:
        try:
            with open(VERSION_CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump({"last_checked": now, "latest_version": latest_ver}, f, indent=2)
        except Exception:
            pass
        return latest_ver

    # Fallback to cached version if PyPI request failed (e.g. offline)
    if VERSION_CACHE_FILE.exists():
        try:
            with open(VERSION_CACHE_FILE, "r", encoding="utf-8") as f:
                cached = json.load(f)
            return cached.get("latest_version")
        except Exception:
            pass

    return None


def check_for_update(current_version: str, force: bool = False) -> Optional[Tuple[str, str]]:
    """
    Check if a newer version exists on PyPI.
    Returns (current_version, latest_version) if an update is available, else None.
    """
    latest = get_cached_or_latest_version(force=force)
    if not latest:
        return None

    cur_tuple = parse_version(current_version)
    latest_tuple = parse_version(latest)

    if latest_tuple > cur_tuple:
        return (current_version, latest)
    return None


def format_update_banner(current_version: str, latest_version: str) -> str:
    """Format a stylish notification banner alerting the user to the update."""
    banner = [
        "┌" + "─" * 74 + "┐",
        f"│  ✨  UPDATE AVAILABLE: v{current_version} ➔ v{latest_version:<44}│",
        f"│  💡  Run 'mws update' or 'pip install --upgrade mcp-win-stdio' to update!  │",
        "└" + "─" * 74 + "┘",
    ]
    return "\n".join(banner)
