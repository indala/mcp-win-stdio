#!/usr/bin/env python3
"""
TypeScript Diagnostic Watcher MCP Server (Python Edition).
Runs background tsc compiler watchers for target projects, maintaining an in-memory
diagnostic cache for instantaneous (0ms latency) TypeScript error inspection.
"""

import atexit
import json
import ntpath
import os
import re
import shutil
import subprocess
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

try:
    from mcp.server.mcpserver import MCPServer as FastMCP
except (ImportError, ModuleNotFoundError):
    from mcp.server.fastmcp import FastMCP  # type: ignore[import-not-found]

try:
    from mcp_win_stdio.core.config import USER_DIR, ensure_workspace_dirs
except Exception:
    USER_DIR = Path.home() / ".mcp-win-stdio"

    def ensure_workspace_dirs() -> Dict[str, Path]:
        USER_DIR.mkdir(parents=True, exist_ok=True)
        return {"root": USER_DIR}

mcp = FastMCP("tsc-mcp")

# Persistent TypeScript projects configuration
TSC_CONFIG_DIR = USER_DIR
TSC_PROJECTS_FILE = TSC_CONFIG_DIR / "tsc_projects.json"
_ACTIVE_PROJECT: Optional[str] = None

# Global in-memory cache and watcher state
# tsconfig_path -> { "process": Popen, "thread": Thread, "project_dir": str, "errors": list, "pending_errors": list, "status": str, "last_updated": str }
WATCHED_PROJECTS: Dict[str, Dict[str, Any]] = {}
CACHE_LOCK = threading.Lock()

# Regex to parse standard tsc compiler output line
# Example: src/components/App.tsx(42,15): error TS2322: Type 'string' is not assignable to type 'number'.
ERROR_REGEX = re.compile(r"^([^(]+)\((\d+),(\d+)\):\s*(error|warning)\s*(TS\d+):\s*(.+)$")
_WINDOWS_DRIVE_ROOT = re.compile(r"^[A-Za-z]:[\\/]*$")


def is_home_or_root_dir(p: Union[str, os.PathLike]) -> bool:
    """
    Check if path is the user home directory, root drive, or Windows system/AppData directory.
    Cross-platform safe: Windows drive roots (e.g. 'C:\\', 'D:/') are recognized even on Linux.
    """
    if not p:
        return False
    raw = os.fspath(p).strip()

    # Treat Windows drive roots as roots on every platform (Linux, macOS, Windows)
    if _WINDOWS_DRIVE_ROOT.fullmatch(raw):
        return True

    # Normalize Windows-style paths for callers that pass equivalent forms (e.g. C:\)
    normalized_windows = ntpath.normpath(raw)
    if _WINDOWS_DRIVE_ROOT.fullmatch(normalized_windows):
        return True

    try:
        resolved = Path(raw).expanduser().resolve()
        home = Path.home().resolve()

        # POSIX root or drive root
        if resolved.parent == resolved or resolved == home:
            return True

        # Parent of home (e.g. /home or C:\Users)
        if resolved == home.parent:
            return True

        resolved_str = str(resolved).lower()

        # Check against common system environment paths
        for env_var in (
            "APPDATA",
            "LOCALAPPDATA",
            "TEMP",
            "TMP",
            "WINDIR",
            "SYSTEMROOT",
            "PROGRAMFILES",
            "PROGRAMFILES(X86)",
        ):
            val = os.environ.get(env_var)
            if val:
                val_resolved = str(Path(val).resolve()).lower()
                if (
                    resolved_str == val_resolved
                    or resolved_str.startswith(val_resolved + "\\")
                    or resolved_str.startswith(val_resolved + "/")
                ):
                    return True

        # Check path parts directly for AppData or Windows system directories
        parts_lower = [part.lower() for part in resolved.parts]
        if any(part in ("appdata", "application data", "windows", "system32") for part in parts_lower):
            return True

    except Exception:
        pass

    return False


def _load_tsc_projects() -> Dict[str, Any]:
    """Load persistent TypeScript projects configuration from ~/.mcp-win-stdio/tsc_projects.json."""
    ensure_workspace_dirs()
    if not TSC_PROJECTS_FILE.exists():
        return {"active_project": None, "projects": {}}
    try:
        with open(TSC_PROJECTS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if not isinstance(data, dict):
                return {"active_project": None, "projects": {}}
            if "projects" not in data or not isinstance(data["projects"], dict):
                data["projects"] = {}
            return data
    except Exception:
        return {"active_project": None, "projects": {}}


def _save_tsc_projects(data: Dict[str, Any]) -> None:
    """Save persistent TypeScript projects configuration to ~/.mcp-win-stdio/tsc_projects.json."""
    ensure_workspace_dirs()
    try:
        with open(TSC_PROJECTS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass


def get_active_project_name() -> Optional[str]:
    """Get the currently active sticky project alias or name."""
    global _ACTIVE_PROJECT
    if _ACTIVE_PROJECT:
        return _ACTIVE_PROJECT
    saved = _load_tsc_projects()
    active = saved.get("active_project")
    if active:
        _ACTIVE_PROJECT = active
        return active
    return None


def set_active_project_name(name: Optional[str]) -> None:
    """Set the active sticky project alias and persist it."""
    global _ACTIVE_PROJECT
    _ACTIVE_PROJECT = name
    saved = _load_tsc_projects()
    saved["active_project"] = name
    _save_tsc_projects(saved)


def resolve_project_info(target: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Resolve project information by alias name, directory path, or active project context.
    Returns dict with keys: 'alias', 'path', 'auto_watch', 'description', etc., or None.
    """
    saved = _load_tsc_projects()
    projects = saved.get("projects", {})

    if target:
        clean = str(target).strip()
        # 1. Match alias case-insensitively
        for alias, info in projects.items():
            if alias.lower() == clean.lower():
                return info

        # 2. Match registered path
        norm_target = normalize_path(clean).lower()
        for alias, info in projects.items():
            if normalize_path(info.get("path", "")).lower() == norm_target:
                return info

        # 3. Direct directory path containing tsconfig.json
        if os.path.isdir(clean):
            abs_p = normalize_path(os.path.abspath(clean))
            return {
                "alias": Path(abs_p).name or "project",
                "path": abs_p,
                "auto_watch": True,
                "description": "Ad-hoc project path",
            }
        return None

    # No target passed -> resolve from active context
    active_name = get_active_project_name()
    if active_name and active_name in projects:
        return projects[active_name]

    # Environment variable fallback
    env_dir = os.environ.get("TSC_WATCH_DIR") or os.environ.get("PROJECT_ROOT")
    if env_dir and os.path.isdir(env_dir) and not is_home_or_root_dir(env_dir):
        abs_env = normalize_path(os.path.abspath(env_dir))
        return {
            "alias": Path(abs_env).name or "env-project",
            "path": abs_env,
            "auto_watch": True,
            "description": "Environment variable project",
        }

    return None


def stop_watching_project(target_dir_or_config: str) -> List[str]:
    """Terminate and unregister background watchers for a given project directory or tsconfig path."""
    norm_target = normalize_path(target_dir_or_config).lower()
    stopped = []
    with CACHE_LOCK:
        for cfg_path, data in list(WATCHED_PROJECTS.items()):
            p_dir = data.get("project_dir", "").lower()
            c_path = cfg_path.lower()
            if (
                c_path == norm_target
                or p_dir == norm_target
                or p_dir.startswith(norm_target + "/")
                or norm_target.startswith(p_dir + "/")
            ):
                proc = data.get("process")
                if proc:
                    try:
                        proc.terminate()
                        try:
                            proc.wait(timeout=1.0)
                        except Exception:
                            proc.kill()
                    except Exception:
                        pass
                stopped.append(cfg_path)
                WATCHED_PROJECTS.pop(cfg_path, None)
    return stopped


def get_default_watch_dir() -> Optional[str]:
    """
    Get active project directory from dynamic ~/.mcp-win-stdio/tsc_projects.json or fallback.
    Returns None if not configured or if configured to a system/home/AppData directory.
    NOTE: Does NOT default to cwd or admin home to avoid unintended scans.
    """
    try:
        active_name = get_active_project_name()
        if active_name:
            proj = resolve_project_info(active_name)
            if proj and proj.get("path"):
                p_path = proj["path"]
                if os.path.isdir(p_path) and not is_home_or_root_dir(p_path):
                    return p_path
    except Exception:
        pass

    # Check ~/.mcp-win-stdio/config.json
    try:
        from mcp_win_stdio.core.config import load_config

        cfg = load_config()
        stored_dir = cfg.get("tsc_watch_dir")
        if stored_dir:
            abs_stored = os.path.abspath(stored_dir)
            if os.path.isdir(abs_stored) and not is_home_or_root_dir(abs_stored):
                return abs_stored
    except Exception:
        pass

    # Legacy environment variable fallback only if dynamic config is empty
    env_dir = (
        os.environ.get("TSC_WATCH_DIR")
        or os.environ.get("PROJECT_ROOT")
        or os.environ.get("WORKSPACE_ROOT")
        or os.environ.get("WORKSPACE_FOLDER")
    )
    if env_dir:
        abs_env = os.path.abspath(env_dir)
        if os.path.isdir(abs_env) and not is_home_or_root_dir(abs_env):
            return abs_env

    # Auto-detect IDE workspace from current process directory if it contains tsconfigs
    try:
        cwd = os.getcwd()
        if os.path.isdir(cwd) and not is_home_or_root_dir(cwd):
            if find_tsconfigs(cwd):
                return os.path.abspath(cwd)
    except Exception:
        pass

    return None


def check_tsc_available(project_dir: Optional[str] = None) -> Dict[str, Any]:
    """
    Check if TypeScript compiler (tsc) is available locally in project or globally on PATH.
    Returns:
        dict with keys: 'available' (bool), 'command' (list of str or None), 'type' (str), 'error' (str), 'guidance' (str)
    """
    # 1. Check local project node_modules/typescript/bin/tsc
    if project_dir:
        local_tsc_js = Path(project_dir) / "node_modules" / "typescript" / "bin" / "tsc"
        if local_tsc_js.exists():
            node_bin = shutil.which("node") or "node"
            return {
                "available": True,
                "command": [node_bin, str(local_tsc_js)],
                "type": "project_local_js",
                "path": str(local_tsc_js),
            }

        # 2. Local node_modules/.bin/tsc.cmd on Windows
        local_tsc_cmd = Path(project_dir) / "node_modules" / ".bin" / "tsc.cmd"
        if local_tsc_cmd.exists():
            return {
                "available": True,
                "command": [str(local_tsc_cmd)],
                "type": "project_local_cmd",
                "path": str(local_tsc_cmd),
            }

    # 3. Global tsc on PATH
    global_tsc = shutil.which("tsc")
    if global_tsc:
        return {
            "available": True,
            "command": [global_tsc],
            "type": "global_tsc",
            "path": global_tsc,
        }

    # 4. Fallback to npx tsc
    npx_bin = shutil.which("npx")
    if npx_bin:
        return {
            "available": True,
            "command": [npx_bin, "tsc"],
            "type": "npx_tsc",
            "path": npx_bin,
        }

    return {
        "available": False,
        "command": None,
        "type": "missing",
        "error": "TypeScript compiler ('tsc') not detected on system or inside project node_modules.",
        "guidance": (
            "To enable TypeScript diagnostics, install TypeScript:\n"
            "  1. Project-local (recommended): npm install -D typescript\n"
            "  2. Global: npm install -g typescript\n"
            "  3. Ensure Node.js is installed: winget install --id OpenJS.NodeJS -e"
        ),
    }


def normalize_path(p: str) -> str:
    """Normalize absolute filesystem path with forward slashes without mangling drive letters."""
    if not p:
        return ""
    p_str = str(p).strip()
    return os.path.abspath(p_str).replace("\\", "/")


def normalize_relpath(p: str) -> str:
    """Normalize relative path with forward slashes without expanding to cwd."""
    if not p:
        return ""
    return str(p).strip().replace("\\", "/")


def find_tsconfigs(base_dir: str, max_depth: int = 4) -> List[str]:
    """Find all tsconfig.json files skipping heavy build/vendor folders."""
    ignore_dirs = {
        "node_modules",
        ".git",
        ".next",
        ".nuxt",
        "dist",
        "build",
        "out",
        ".output",
        "target",
        "bin",
        "obj",
        "__pycache__",
        ".cache",
        "coverage",
        ".turbo",
        "appdata",
        ".vscode",
        ".gemini",
        ".cursor",
        ".cargo",
        ".rustup",
        "venv",
        ".venv",
        "env",
        ".env",
        "site-packages",
        "local settings",
        "application data",
    }
    configs = []
    base_p = Path(base_dir)
    if not base_p.exists():
        return configs

    # Safety: do not deeply crawl user profile root or root drive
    if is_home_or_root_dir(base_dir):
        direct_cfg = base_p / "tsconfig.json"
        if direct_cfg.exists():
            return [str(direct_cfg)]
        return configs

    for root, dirs, files in os.walk(base_dir):
        # Prune ignored directories in-place
        dirs[:] = [d for d in dirs if d.lower() not in ignore_dirs and not d.startswith(".")]
        rel_depth = len(Path(root).relative_to(base_p).parts)
        if rel_depth > max_depth:
            dirs.clear()
            continue

        if "tsconfig.json" in files:
            configs.append(os.path.join(root, "tsconfig.json"))

    return configs


def resolve_tsc_command(project_dir: str) -> Optional[List[str]]:
    """Find local or global tsc binary."""
    # 1. Local project node_modules/typescript/bin/tsc
    local_tsc_js = Path(project_dir) / "node_modules" / "typescript" / "bin" / "tsc"
    if local_tsc_js.exists():
        node_bin = shutil.which("node") or "node"
        return [node_bin, str(local_tsc_js)]

    # 2. Local node_modules/.bin/tsc.cmd on Windows
    local_tsc_cmd = Path(project_dir) / "node_modules" / ".bin" / "tsc.cmd"
    if local_tsc_cmd.exists():
        return [str(local_tsc_cmd)]

    # 3. Global tsc on PATH
    global_tsc = shutil.which("tsc")
    if global_tsc:
        return [global_tsc]

    # 4. Fallback to npx tsc
    npx_bin = shutil.which("npx")
    if npx_bin:
        return [npx_bin, "tsc"]

    return None


def parse_tsc_line(line: str, project_dir: str, root_dir: str) -> Optional[Dict[str, Any]]:
    """Parse single tsc diagnostic error line into structured dict."""
    trimmed = line.strip()
    match = ERROR_REGEX.match(trimmed)
    if not match:
        return None

    raw_file, line_num, col_num, severity, code, message = match.groups()
    abs_path = os.path.abspath(raw_file if os.path.isabs(raw_file) else os.path.join(project_dir, raw_file))
    try:
        rel_path = os.path.relpath(abs_path, root_dir)
    except Exception:
        rel_path = abs_path

    return {
        "file": normalize_path(abs_path),
        "relative_path": normalize_relpath(rel_path),
        "line": int(line_num),
        "column": int(col_num),
        "severity": severity.lower(),
        "code": code,
        "message": message.strip(),
    }


def _watcher_loop(tsconfig_path: str, root_dir: str, cmd_base: Optional[List[str]] = None) -> None:
    """Worker thread running tsc --noEmit --watch in background."""
    project_dir = os.path.dirname(tsconfig_path)
    if not cmd_base:
        tsc_check = check_tsc_available(project_dir)
        cmd_base = tsc_check.get("command")

    if not cmd_base:
        with CACHE_LOCK:
            if tsconfig_path in WATCHED_PROJECTS:
                WATCHED_PROJECTS[tsconfig_path]["status"] = "error: tsc compiler not found (install typescript)"
                ready_ev = WATCHED_PROJECTS[tsconfig_path].get("ready_event")
                if ready_ev:
                    ready_ev.set()
        return

    full_cmd = cmd_base + ["--noEmit", "--watch", "--preserveWatchOutput", "-p", tsconfig_path]

    try:
        # Create background process without opening visible window
        startupinfo = None
        if os.name == "nt":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

        proc = subprocess.Popen(
            full_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            text=True,
            bufsize=1,
            cwd=project_dir,
            startupinfo=startupinfo,
        )

        with CACHE_LOCK:
            if tsconfig_path in WATCHED_PROJECTS:
                WATCHED_PROJECTS[tsconfig_path]["process"] = proc
                WATCHED_PROJECTS[tsconfig_path]["status"] = "compiling"
                WATCHED_PROJECTS[tsconfig_path]["start_time"] = time.time()

        pending_errors: List[Dict[str, Any]] = []

        if proc.stdout:
            for raw_line in proc.stdout:
                line = raw_line.rstrip()
                if not line:
                    continue

                # Check completion markers
                if "Found 0 errors." in line or ("Found " in line and "Watching for file changes." in line):
                    with CACHE_LOCK:
                        if tsconfig_path in WATCHED_PROJECTS:
                            st = WATCHED_PROJECTS[tsconfig_path].get("start_time", time.time())
                            WATCHED_PROJECTS[tsconfig_path]["errors"] = list(pending_errors)
                            WATCHED_PROJECTS[tsconfig_path]["status"] = "ready"
                            WATCHED_PROJECTS[tsconfig_path]["compile_duration_s"] = round(time.time() - st, 2)
                            WATCHED_PROJECTS[tsconfig_path]["last_updated"] = datetime.now(timezone.utc).isoformat()
                            ready_ev = WATCHED_PROJECTS[tsconfig_path].get("ready_event")
                            if ready_ev:
                                ready_ev.set()
                    pending_errors = []
                elif "Starting compilation in watch mode..." in line or "File change detected." in line:
                    with CACHE_LOCK:
                        if tsconfig_path in WATCHED_PROJECTS:
                            WATCHED_PROJECTS[tsconfig_path]["status"] = "compiling"
                            WATCHED_PROJECTS[tsconfig_path]["start_time"] = time.time()
                    pending_errors = []
                else:
                    err = parse_tsc_line(line, project_dir, root_dir)
                    if err:
                        pending_errors.append(err)
                    elif pending_errors and (line.startswith(" ") or line.startswith("\t")):
                        # Multi-line diagnostic message continuation
                        pending_errors[-1]["message"] += "\n" + line.strip()

    except Exception as e:
        with CACHE_LOCK:
            if tsconfig_path in WATCHED_PROJECTS:
                WATCHED_PROJECTS[tsconfig_path]["status"] = f"error: {str(e)}"
                ready_ev = WATCHED_PROJECTS[tsconfig_path].get("ready_event")
                if ready_ev:
                    ready_ev.set()
    finally:
        with CACHE_LOCK:
            if tsconfig_path in WATCHED_PROJECTS:
                ready_ev = WATCHED_PROJECTS[tsconfig_path].get("ready_event")
                if ready_ev and not ready_ev.is_set():
                    ready_ev.set()


def wait_for_projects_compilation(configs: List[str], timeout: float = 30.0) -> bool:
    """
    Wait for all specified project configs to finish their initial compilation pass.
    Returns True if all projects compiled within the timeout, False otherwise.
    """
    start = time.time()
    for cfg in configs:
        norm_cfg = normalize_path(cfg)
        ready_ev = None
        with CACHE_LOCK:
            if norm_cfg in WATCHED_PROJECTS:
                ready_ev = WATCHED_PROJECTS[norm_cfg].get("ready_event")
        if ready_ev:
            elapsed = time.time() - start
            remaining = max(0.1, timeout - elapsed)
            if elapsed >= timeout or not ready_ev.wait(timeout=remaining):
                return False
    return True


def start_watching_project(target_dir: str, cmd_base: Optional[List[str]] = None) -> List[str]:
    """
    Scan and start background watchers for all tsconfig.json in target_dir.
    Verifies tsc compiler availability BEFORE scanning directory tree.
    """
    abs_root = os.path.abspath(target_dir)

    # Safety: Refuse to scan user home, root drive, or AppData
    if is_home_or_root_dir(abs_root):
        return []

    # Verify tsc compiler is available BEFORE scanning filesystem
    if not cmd_base:
        tsc_check = check_tsc_available(abs_root)
        if not tsc_check["available"]:
            return []
        cmd_base = tsc_check["command"]

    configs = find_tsconfigs(abs_root)

    for cfg in configs:
        norm_cfg = normalize_path(cfg)
        try:
            rel_cfg = os.path.relpath(cfg, abs_root)
        except Exception:
            rel_cfg = os.path.basename(cfg)

        with CACHE_LOCK:
            if norm_cfg in WATCHED_PROJECTS and WATCHED_PROJECTS[norm_cfg].get("process"):
                # Already watching
                continue

            WATCHED_PROJECTS[norm_cfg] = {
                "project_dir": normalize_path(os.path.dirname(cfg)),
                "tsconfig_path": norm_cfg,
                "relative_config": normalize_relpath(rel_cfg),
                "errors": [],
                "status": "compiling",
                "last_updated": datetime.now(timezone.utc).isoformat(),
                "process": None,
                "cmd_base": cmd_base,
                "ready_event": threading.Event(),
                "start_time": time.time(),
                "compile_duration_s": None,
            }

        t = threading.Thread(target=_watcher_loop, args=(norm_cfg, abs_root, cmd_base), daemon=True)
        t.start()

    return configs


# Cleanup processes on exit
def _cleanup_watchers():
    with CACHE_LOCK:
        for srv in WATCHED_PROJECTS.values():
            proc = srv.get("process")
            if proc:
                try:
                    proc.terminate()
                except Exception:
                    pass


atexit.register(_cleanup_watchers)

def _initialize_projects_on_startup() -> None:
    """Initialize watchers from dynamic config and environment fallbacks."""
    try:
        saved = _load_tsc_projects()
        active = saved.get("active_project")
        projects = saved.get("projects", {})

        # 1. Fallback / migration: if TSC_WATCH_DIR or PROJECT_ROOT is set and not yet registered
        env_dir = os.environ.get("TSC_WATCH_DIR") or os.environ.get("PROJECT_ROOT")
        if env_dir:
            abs_env = os.path.abspath(env_dir)
            if os.path.isdir(abs_env) and not is_home_or_root_dir(abs_env):
                norm_env = normalize_path(abs_env)
                if not any(normalize_path(p.get("path", "")).lower() == norm_env.lower() for p in projects.values()):
                    alias = Path(abs_env).name or "workspace"
                    unique_alias = alias
                    idx = 1
                    while unique_alias in projects:
                        unique_alias = f"{alias}-{idx}"
                        idx += 1
                    projects[unique_alias] = {
                        "path": norm_env,
                        "alias": unique_alias,
                        "auto_watch": True,
                        "description": "Configured via environment variable",
                        "registered_at": datetime.now(timezone.utc).isoformat(),
                    }
                    if not active:
                        active = unique_alias
                    saved["projects"] = projects
                    saved["active_project"] = active
                    _save_tsc_projects(saved)

        if active and active in projects:
            set_active_project_name(active)

        # 2. Auto-watch registered projects
        for alias, pinfo in projects.items():
            if pinfo.get("auto_watch", True):
                p_path = pinfo.get("path")
                if p_path and os.path.isdir(p_path) and not is_home_or_root_dir(p_path):
                    tsc_check = check_tsc_available(p_path)
                    if tsc_check.get("available"):
                        start_watching_project(p_path, cmd_base=tsc_check.get("command"))

        # 3. Check ~/.mcp-win-stdio/config.json fallback
        if not projects:
            init_root = get_default_watch_dir()
            if init_root and os.path.isdir(init_root) and not is_home_or_root_dir(init_root):
                tsc_check = check_tsc_available(init_root)
                if tsc_check.get("available"):
                    start_watching_project(init_root, cmd_base=tsc_check.get("command"))
    except Exception:
        pass


_initialize_projects_on_startup()


def _format_tsc_error(err: Dict[str, Any], max_msg_chars: int = 300) -> Dict[str, Any]:
    """Format individual TypeScript error, truncating giant generic type signatures to protect agent context window."""
    msg = str(err.get("message", "")).strip()
    is_truncated = False
    if len(msg) > max_msg_chars:
        msg = msg[:max_msg_chars] + "... [type signature truncated]"
        is_truncated = True

    formatted = {
        "file": err.get("relative_path") or err.get("file"),
        "line": err.get("line"),
        "column": err.get("column"),
        "severity": err.get("severity", "error"),
        "code": err.get("code"),
        "message": msg,
    }
    if is_truncated:
        formatted["is_message_truncated"] = True
    return formatted


# ==============================================================================
# 1. Project & Workspace Management Tools (Dynamic Config)
# ==============================================================================


@mcp.tool()
def list_projects() -> Dict[str, Any]:
    """
    List all configured TypeScript projects (from ~/.mcp-win-stdio/tsc_projects.json and active watchers),
    indicating the active sticky project, watcher status, error count, compiler, and tsconfig paths.
    """
    saved = _load_tsc_projects()
    active_name = get_active_project_name()
    projects_dict = saved.get("projects", {})

    results = []
    with CACHE_LOCK:
        for alias, info in projects_dict.items():
            p_path = info.get("path", "")
            norm_p = normalize_path(p_path).lower() if p_path else ""

            matched_cfgs = []
            proj_errors = 0
            status = "stopped"
            last_updated = None

            for cfg_path, data in WATCHED_PROJECTS.items():
                d_proj = data.get("project_dir", "").lower()
                if d_proj == norm_p or d_proj.startswith(norm_p + "/") or norm_p.startswith(d_proj + "/"):
                    matched_cfgs.append(data.get("relative_config", cfg_path))
                    proj_errors += len(data.get("errors", []))
                    c_status = data.get("status", "unknown")
                    if c_status == "compiling":
                        status = "compiling"
                    elif c_status == "ready" and status != "compiling":
                        status = "ready"
                    elif c_status.startswith("error") and status not in ("compiling", "ready"):
                        status = c_status
                    last_updated = data.get("last_updated") or last_updated

            if not matched_cfgs and info.get("auto_watch", True):
                status = "standby"

            tsc_check = check_tsc_available(p_path) if p_path and os.path.exists(p_path) else {"type": "not_checked"}

            results.append(
                {
                    "alias": alias,
                    "path": p_path,
                    "isActive": alias == active_name,
                    "autoWatch": info.get("auto_watch", True),
                    "description": info.get("description"),
                    "status": status,
                    "tsconfigCount": len(matched_cfgs),
                    "tsconfigs": matched_cfgs,
                    "errorCount": proj_errors,
                    "compiler": tsc_check.get("type", "unknown"),
                    "lastUpdated": last_updated,
                }
            )

        # Ad-hoc watched projects not yet registered
        for cfg_path, data in WATCHED_PROJECTS.items():
            d_proj = data.get("project_dir", "")
            norm_d = normalize_path(d_proj).lower()
            already_covered = any(normalize_path(p.get("path", "")).lower() == norm_d for p in projects_dict.values())
            if not already_covered:
                alias = Path(d_proj).name or "adhoc"
                results.append(
                    {
                        "alias": f"{alias} (unregistered)",
                        "path": d_proj,
                        "isActive": False,
                        "autoWatch": False,
                        "description": "Ad-hoc watched project",
                        "status": data.get("status", "unknown"),
                        "tsconfigCount": 1,
                        "tsconfigs": [data.get("relative_config", cfg_path)],
                        "errorCount": len(data.get("errors", [])),
                        "compiler": "active",
                        "lastUpdated": data.get("last_updated"),
                    }
                )

    if not results:
        return {
            "activeProject": active_name,
            "totalProjects": 0,
            "projects": [],
            "status": "standby",
            "message": "No TypeScript projects are currently registered. Call add_project(project_path, alias='...') to register and monitor a project.",
        }

    return {
        "activeProject": active_name,
        "totalProjects": len(results),
        "status": "standby" if not results else "active",
        "projects": results,
    }


@mcp.tool()
def use_project(project: str) -> Dict[str, Any]:
    """
    Switch the active default TypeScript project context. All subsequent diagnostic queries
    (get_tsc_errors, get_file_errors, get_error_summary) will target this project automatically
    when project is not specified.

    Args:
        project: Project alias name (e.g. 'frontend', 'web') or filesystem directory path to switch to.
    """
    clean_target = project.strip()
    saved = _load_tsc_projects()
    projects = saved.get("projects", {})

    matched_alias = None
    for alias in projects:
        if alias.lower() == clean_target.lower():
            matched_alias = alias
            break

    if not matched_alias:
        norm_target = normalize_path(clean_target).lower()
        for alias, info in projects.items():
            if normalize_path(info.get("path", "")).lower() == norm_target:
                matched_alias = alias
                break

    if not matched_alias and os.path.isdir(clean_target):
        abs_p = os.path.abspath(clean_target)
        if not is_home_or_root_dir(abs_p):
            cfgs = find_tsconfigs(abs_p)
            if cfgs:
                alias = Path(abs_p).name or "project"
                idx = 1
                unique_alias = alias
                while unique_alias in projects:
                    unique_alias = f"{alias}-{idx}"
                    idx += 1
                matched_alias = unique_alias
                projects[matched_alias] = {
                    "path": normalize_path(abs_p),
                    "alias": matched_alias,
                    "auto_watch": True,
                    "description": "Auto-registered on use_project",
                    "registered_at": datetime.now(timezone.utc).isoformat(),
                }
                saved["projects"] = projects
                tsc_check = check_tsc_available(abs_p)
                if tsc_check.get("available"):
                    start_watching_project(abs_p, cmd_base=tsc_check.get("command"))

    if not matched_alias:
        return {
            "success": False,
            "error": f"Project '{project}' not found in registered projects.",
            "available_projects": list(projects.keys()),
            "guidance": "Use add_project(project_path, alias='...') to register a new project folder.",
        }

    set_active_project_name(matched_alias)
    info = projects[matched_alias]
    return {
        "success": True,
        "message": f"Active TypeScript project switched to '{matched_alias}' ({info.get('path')}).",
        "activeProject": matched_alias,
        "path": info.get("path"),
    }


@mcp.tool()
def add_project(
    project_path: str,
    alias: Optional[str] = None,
    auto_watch: bool = True,
    description: Optional[str] = None,
    wait_for_initial_compile: bool = True,
    timeout_seconds: float = 30.0,
) -> Dict[str, Any]:
    """
    Register and persist a new TypeScript project to ~/.mcp-win-stdio/tsc_projects.json.
    Optionally starts background compiler watchers immediately and waits for initial compilation.

    Args:
        project_path: Local filesystem directory path to the TypeScript project or tsconfig.json.
        alias: Friendly alias name for switching (e.g. 'web', 'api', 'admin'). Defaults to directory name.
        auto_watch: If True, immediately verifies tsc and starts background watching (default True).
        description: Friendly description or notes for this project.
        wait_for_initial_compile: If True, waits up to timeout_seconds for initial compilation (default True).
        timeout_seconds: Maximum seconds to wait for initial compile (default 30.0).
    """
    if not os.path.exists(project_path):
        return {"success": False, "error": f"Path not found: {project_path}"}

    if os.path.isfile(project_path):
        project_path = os.path.dirname(project_path)

    abs_project = os.path.abspath(project_path)

    if is_home_or_root_dir(abs_project):
        return {
            "success": False,
            "error": f"Refusing to register system, user home, or AppData directory: '{abs_project}'. Please specify a specific project directory.",
            "guidance": "Provide the path to your project folder (e.g. 'Z:/projects/my-app').",
        }

    key = alias.strip() if alias else Path(abs_project).name or "project"

    saved = _load_tsc_projects()
    projects = saved.get("projects", {})

    project_entry = {
        "path": normalize_path(abs_project),
        "alias": key,
        "auto_watch": auto_watch,
        "description": description.strip() if description else None,
        "registered_at": datetime.now(timezone.utc).isoformat(),
    }
    projects[key] = project_entry
    saved["projects"] = projects

    if not saved.get("active_project"):
        saved["active_project"] = key
        set_active_project_name(key)

    _save_tsc_projects(saved)

    tsc_check = check_tsc_available(abs_project)
    configs: List[str] = []
    compilation_completed = True
    elapsed_s = 0.0
    total_errors = 0

    if auto_watch:
        if not tsc_check.get("available"):
            return {
                "success": True,
                "registered": True,
                "alias": key,
                "path": normalize_path(abs_project),
                "watcher_started": False,
                "warning": tsc_check.get("error"),
                "guidance": tsc_check.get("guidance"),
                "message": f"Project '{key}' registered in config, but watcher was not started: {tsc_check.get('error')}",
            }

        configs = start_watching_project(abs_project, cmd_base=tsc_check.get("command"))
        if wait_for_initial_compile and configs:
            start_t = time.time()
            compilation_completed = wait_for_projects_compilation(configs, timeout=timeout_seconds)
            elapsed_s = round(time.time() - start_t, 2)

        with CACHE_LOCK:
            for cfg in configs:
                norm_cfg = normalize_path(cfg)
                if norm_cfg in WATCHED_PROJECTS:
                    total_errors += len(WATCHED_PROJECTS[norm_cfg].get("errors", []))

    return {
        "success": True,
        "alias": key,
        "path": normalize_path(abs_project),
        "isActive": get_active_project_name() == key,
        "auto_watch": auto_watch,
        "found_tsconfigs": configs,
        "compiler_type": tsc_check.get("type"),
        "compiler_command": " ".join(tsc_check.get("command", [])) if tsc_check.get("command") else None,
        "compilation_completed": compilation_completed,
        "elapsed_seconds": elapsed_s,
        "total_errors": total_errors,
        "message": f"Project '{key}' registered successfully ({len(configs)} configuration(s) found, {total_errors} errors).",
    }


@mcp.tool()
def remove_project(
    project: str,
    stop_watcher: bool = True,
) -> Dict[str, Any]:
    """
    Remove a saved TypeScript project configuration from ~/.mcp-win-stdio/tsc_projects.json.

    Args:
        project: Alias or directory path of the project to remove.
        stop_watcher: If True, terminates active background compiler processes for this project (default True).
    """
    clean_target = project.strip()
    saved = _load_tsc_projects()
    projects = saved.get("projects", {})

    target_alias = None
    if clean_target in projects:
        target_alias = clean_target
    else:
        norm_target = normalize_path(clean_target).lower()
        for k, pinfo in projects.items():
            if k.lower() == clean_target.lower() or normalize_path(pinfo.get("path", "")).lower() == norm_target:
                target_alias = k
                break

    if not target_alias:
        return {
            "success": False,
            "error": f"Project '{project}' not found in registered projects.",
            "available_projects": list(projects.keys()),
        }

    pinfo = projects.pop(target_alias)
    stopped_configs = []
    if stop_watcher and pinfo.get("path"):
        stopped_configs = stop_watching_project(pinfo["path"])

    saved["projects"] = projects
    active = saved.get("active_project")
    new_active = active
    if active == target_alias:
        new_active = next(iter(projects.keys())) if projects else None
        saved["active_project"] = new_active
        set_active_project_name(new_active)

    _save_tsc_projects(saved)

    return {
        "success": True,
        "message": f"Project '{target_alias}' removed successfully.",
        "removedProject": target_alias,
        "path": pinfo.get("path"),
        "stopped_configs": stopped_configs,
        "newActiveProject": new_active,
    }


# ==============================================================================
# 2. Diagnostic Query & Fix Tools
# ==============================================================================


@mcp.tool()
def get_tsc_errors(
    project_path: Optional[str] = None,
    tsconfig_path: Optional[str] = None,
    error_code: Optional[str] = None,
    limit: int = 30,
    offset: int = 0,
    max_message_chars: int = 300,
    wait_if_compiling: bool = True,
    wait_timeout: float = 45.0,
) -> Dict[str, Any]:
    """
    Get active TypeScript compiler errors across watched projects (0ms latency from memory cache).
    Features automatic context window protection, pagination, error code filtering, token-safe message truncation,
    and automatic synchronization if an initial compilation pass is in progress.

    Args:
        project_path: Optional filter by project directory substring.
        tsconfig_path: Optional filter by specific tsconfig.json file path.
        error_code: Optional filter by TS error code (e.g. 'TS2304', 'TS2322', 'TS2339').
        limit: Maximum number of detailed error objects to return per batch (default 30, max 100).
        offset: Starting index offset for pagination (default 0).
        max_message_chars: Maximum character length for individual error messages (default 300).
        wait_if_compiling: If True, waits up to wait_timeout seconds if projects are currently compiling their initial pass (default True).
        wait_timeout: Maximum seconds to wait if a project is actively compiling (default 15.0).
    """
    # Resolve effective project target (alias, active project, or path filter)
    active_alias = get_active_project_name()
    active_path = None
    if active_alias:
        pinfo = resolve_project_info(active_alias)
        if pinfo and pinfo.get("path"):
            active_path = pinfo.get("path")

    effective_project_path = project_path
    if not effective_project_path and not tsconfig_path:
        if active_path:
            effective_project_path = active_path
    elif effective_project_path and effective_project_path.strip().lower() in ("all", "*"):
        effective_project_path = None
    elif effective_project_path:
        pinfo = resolve_project_info(effective_project_path)
        if pinfo and pinfo.get("path"):
            effective_project_path = pinfo.get("path")

    # 1. If wait_if_compiling is enabled, check if matching projects are compiling and wait on their ready events
    if wait_if_compiling:
        events_to_wait = []
        with CACHE_LOCK:
            for cfg_path, data in WATCHED_PROJECTS.items():
                if tsconfig_path:
                    norm_cfg_filter = tsconfig_path.replace("\\", "/").lower()
                    norm_cfg_abs = normalize_path(tsconfig_path).lower()
                    if cfg_path.lower() != norm_cfg_abs and norm_cfg_filter not in cfg_path.lower():
                        continue
                if effective_project_path:
                    p_filter = effective_project_path.replace("\\", "/").rstrip("/").lower()
                    p_abs = normalize_path(effective_project_path).lower()
                    proj_dir = str(data["project_dir"]).replace("\\", "/").rstrip("/").lower()
                    if (
                        p_filter not in proj_dir
                        and p_abs != proj_dir
                        and not proj_dir.startswith(p_abs + "/")
                        and not p_abs.startswith(proj_dir + "/")
                    ):
                        continue
                if data.get("status") == "compiling":
                    ev = data.get("ready_event")
                    if ev and not ev.is_set():
                        events_to_wait.append(ev)

        start_w = time.time()
        for ev in events_to_wait:
            rem = max(0.1, wait_timeout - (time.time() - start_w))
            if (time.time() - start_w) >= wait_timeout or not ev.wait(timeout=rem):
                break

    with CACHE_LOCK:
        if not WATCHED_PROJECTS:
            return {
                "success": True,
                "total_errors": 0,
                "returned_errors": 0,
                "offset": offset,
                "limit": limit,
                "active_project": active_alias,
                "projects": [],
                "errors": [],
                "warning": "No TypeScript projects are currently being watched. Call 'add_project(project_path)' or 'watch_project(project_path)' with your project directory.",
            }

        all_errors = []
        projects_summary = []
        compiling_count = 0
        safe_limit = min(max(1, limit), 100)
        safe_offset = max(0, offset)

        for cfg_path, data in WATCHED_PROJECTS.items():
            if tsconfig_path:
                norm_cfg_filter = tsconfig_path.replace("\\", "/").lower()
                norm_cfg_abs = normalize_path(tsconfig_path).lower()
                if cfg_path.lower() != norm_cfg_abs and norm_cfg_filter not in cfg_path.lower():
                    continue

            if effective_project_path:
                p_filter = effective_project_path.replace("\\", "/").rstrip("/").lower()
                p_abs = normalize_path(effective_project_path).lower()
                proj_dir = str(data["project_dir"]).replace("\\", "/").rstrip("/").lower()
                if (
                    p_filter not in proj_dir
                    and p_abs != proj_dir
                    and not proj_dir.startswith(p_abs + "/")
                    and not p_abs.startswith(proj_dir + "/")
                ):
                    continue

            errs = data.get("errors", [])
            status = data.get("status", "unknown")
            if status == "compiling":
                compiling_count += 1

            for e in errs:
                if error_code and e.get("code", "").upper() != error_code.strip().upper():
                    continue
                all_errors.append(e)

            projects_summary.append(
                {
                    "tsconfig": data["relative_config"],
                    "project_dir": data["project_dir"],
                    "status": status,
                    "error_count": len(errs),
                    "compile_duration_s": data.get("compile_duration_s"),
                    "last_updated": data["last_updated"],
                }
            )

        # Calculate high-level breakdown
        code_counts: Dict[str, int] = {}
        file_counts: Dict[str, int] = {}
        for e in all_errors:
            c = e.get("code", "UNKNOWN")
            f = e.get("relative_path") or e.get("file", "UNKNOWN")
            code_counts[c] = code_counts.get(c, 0) + 1
            file_counts[f] = file_counts.get(f, 0) + 1

        total_errs = len(all_errors)
        display_errors = all_errors[safe_offset : safe_offset + safe_limit]
        has_more = total_errs > (safe_offset + len(display_errors))

        result: Dict[str, Any] = {
            "success": True,
            "total_errors": total_errs,
            "returned_errors": len(display_errors),
            "offset": safe_offset,
            "limit": safe_limit,
            "active_project": active_alias,
            "has_more": has_more,
            "truncated": has_more,
            "error_codes_breakdown": dict(sorted(code_counts.items(), key=lambda x: x[1], reverse=True)[:10]),
            "top_affected_files": dict(sorted(file_counts.items(), key=lambda x: x[1], reverse=True)[:8]),
            "projects": projects_summary,
            "errors": [_format_tsc_error(e, max_msg_chars=max_message_chars) for e in display_errors],
        }

        if has_more:
            next_offset = safe_offset + len(display_errors)
            result["notice"] = (
                f"... [TRUNCATED: Showing errors {safe_offset + 1}-{next_offset} of {total_errs} to protect context window. "
                f"Use offset={next_offset} to view the next window, or filter by file with 'get_file_errors'] ..."
            )

        if compiling_count > 0:
            result["is_initial_compilation_pending"] = True
            result["status_notice"] = (
                f"{compiling_count} project(s) still compiling initial pass. Diagnostics will update once compilation completes."
            )

        return result


@mcp.tool()
def suggest_error_fixes(error_code: str, message: Optional[str] = None) -> Dict[str, Any]:
    """
    [Advanced Tool] Instant actionable fix recommendations and code patterns for common TypeScript compiler errors.

    Args:
        error_code: The TypeScript error code (e.g. 'TS2304', 'TS2322', 'TS2339', 'TS7016').
        message: Optional compiler error message for deeper context analysis.
    """
    code = error_code.strip().upper()
    if not code.startswith("TS"):
        code = f"TS{code}"

    knowledge_base = {
        "TS2304": {
            "title": "Cannot find name 'X'",
            "category": "Missing Declaration / Global",
            "common_causes": [
                "Missing import statement for a module or type.",
                "Using browser/node globals (e.g. 'process', 'window', 'document') without appropriate types installed (@types/node).",
                "Typo in variable or class name.",
            ],
            "resolutions": [
                "Add import statement: import { X } from './module';",
                "If using Node globals: run 'npm install --save-dev @types/node' and add 'node' to compilerOptions.types in tsconfig.json.",
                "If ambient library global: declare global variable: declare const X: any;",
            ],
        },
        "TS2322": {
            "title": "Type 'A' is not assignable to type 'B'",
            "category": "Type Mismatch",
            "common_causes": [
                "Passing a null or undefined value to a strictly typed property (strictNullChecks).",
                "Object is missing required fields defined in an interface/type.",
                "Incompatible primitive types (e.g. string passed where number is expected).",
            ],
            "resolutions": [
                "Check for null/undefined: provide default fallback (val ?? defaultValue) or use optional type (B | null).",
                "Ensure all mandatory fields of interface 'B' are populated.",
                "Use explicit type narrowing (typeof, instanceof, in operator) before assignment.",
            ],
        },
        "TS2339": {
            "title": "Property 'X' does not exist on type 'Y'",
            "category": "Property Access Error",
            "common_causes": [
                "Accessing property on union type where not all union members have property 'X'.",
                "Accessing property on 'unknown' or 'never' type.",
                "Missing property definition on interface or class.",
            ],
            "resolutions": [
                "Use optional chaining: object?.X",
                "Narrow union type using type guards: if ('X' in obj) { obj.X }",
                "If 'unknown' type: cast or validate before access: (obj as Record<string, any>).X",
                "Extend interface definition with optional or required field: X?: string;",
            ],
        },
        "TS2554": {
            "title": "Expected N arguments, but got M",
            "category": "Function Signature Mismatch",
            "common_causes": [
                "Calling function with too few or too many arguments.",
                "Function definition changed without updating callers.",
            ],
            "resolutions": [
                "Provide all mandatory arguments, or make unused arguments optional in function declaration: fn(a: string, b?: number).",
                "Use object destructuring for parameter lists: fn({ a, b = defaultVal }: Options).",
            ],
        },
        "TS7016": {
            "title": "Could not find a declaration file for module 'X'",
            "category": "Missing Type Definitions",
            "common_causes": ["Third-party npm package lacks bundled TypeScript declaration (.d.ts) files."],
            "resolutions": [
                "Install DefinitelyTyped types: npm install --save-dev @types/X",
                "If no @types exists: create a ambient declaration file (e.g. 'src/declarations.d.ts') with: declare module 'X';",
            ],
        },
        "TS18048": {
            "title": "'X' is possibly 'undefined'",
            "category": "Strict Null Checks",
            "common_causes": [
                "Accessing a property on an object that could be undefined (e.g. find() result, dictionary lookup)."
            ],
            "resolutions": [
                "Use optional chaining: obj?.prop",
                "Use nullish coalescing default: const val = obj?.prop ?? fallback;",
                "Use early guard return: if (!obj) return;",
            ],
        },
    }

    advice = knowledge_base.get(code)
    if advice:
        return {
            "success": True,
            "error_code": code,
            "matched_error": advice["title"],
            "category": advice["category"],
            "common_causes": advice["common_causes"],
            "recommended_resolutions": advice["resolutions"],
            "provided_message": message,
        }

    return {
        "success": True,
        "error_code": code,
        "category": "General TypeScript Error",
        "guidance": "Check TypeScript documentation for error code "
        + code
        + ". Ensure types match interface declarations and strict null checks are satisfied.",
        "provided_message": message,
    }


@mcp.tool()
def get_error_category_breakdown(
    project: Optional[str] = None,
) -> Dict[str, Any]:
    """
    [Advanced Tool] Get an architectural aggregate breakdown of active errors grouped by semantic category
    (Missing Imports, Type Mismatches, Property Errors, Nullability, Syntax) to plan refactors.

    Args:
        project: Optional project alias or path to filter errors by. Defaults to active project or all.
    """
    active_alias = get_active_project_name()
    target_path = None
    if project:
        pinfo = resolve_project_info(project)
        target_path = pinfo.get("path") if pinfo else normalize_path(project).lower()

    with CACHE_LOCK:
        if not WATCHED_PROJECTS:
            return {
                "success": True,
                "total_errors": 0,
                "categories": {},
                "active_project": active_alias,
                "message": "No active projects watched.",
            }

        categories: Dict[str, List[Dict[str, Any]]] = {
            "missing_imports_or_types": [],
            "type_mismatches": [],
            "property_access_errors": [],
            "nullability_and_undefined": [],
            "function_signature_mismatches": [],
            "other": [],
        }

        total = 0
        for cfg_path, data in WATCHED_PROJECTS.items():
            if target_path:
                norm_target = normalize_path(target_path).lower()
                p_dir = data.get("project_dir", "").lower()
                if (
                    norm_target not in p_dir
                    and norm_target != p_dir
                    and not p_dir.startswith(norm_target + "/")
                    and not norm_target.startswith(p_dir + "/")
                ):
                    continue

            for e in data.get("errors", []):
                total += 1
                c = e.get("code", "")
                item = {
                    "code": c,
                    "file": e.get("relative_path") or e.get("file"),
                    "line": e.get("line"),
                    "message": e.get("message"),
                }

                if c in ("TS2304", "TS7016", "TS2307", "TS2686"):
                    categories["missing_imports_or_types"].append(item)
                elif c in ("TS2322", "TS2345", "TS2769"):
                    categories["type_mismatches"].append(item)
                elif c in ("TS2339", "TS2551"):
                    categories["property_access_errors"].append(item)
                elif c in ("TS2531", "TS2532", "TS18048"):
                    categories["nullability_and_undefined"].append(item)
                elif c in ("TS2554", "TS2555"):
                    categories["function_signature_mismatches"].append(item)
                else:
                    categories["other"].append(item)

        # Cap lists in categories to avoid bloating agent context window
        capped_cats = {}
        for cat_name, items in categories.items():
            capped_cats[cat_name] = {
                "count": len(items),
                "sample_errors": [_format_tsc_error(it, max_msg_chars=200) for it in items[:6]],
            }

        return {
            "success": True,
            "total_errors": total,
            "active_project": active_alias,
            "category_summary": {k: v["count"] for k, v in capped_cats.items()},
            "details": capped_cats,
        }


@mcp.tool()
def get_file_errors(
    file_path: str,
    project: Optional[str] = None,
    limit: int = 30,
    offset: int = 0,
    max_message_chars: int = 300,
) -> Dict[str, Any]:
    """
    Get TypeScript compiler errors for a specific file (.ts, .tsx, .js, .jsx) with context window protection.

    Args:
        file_path: Relative or absolute path to the TypeScript/JavaScript file.
        project: Optional project alias or path filter. Defaults to active project context if set.
        limit: Max errors to return in this batch (default 30, max 100).
        offset: Starting offset for pagination (default 0).
        max_message_chars: Maximum character length for individual error messages (default 300).
    """
    active_alias = get_active_project_name()
    target_path = None
    if project:
        pinfo = resolve_project_info(project)
        target_path = pinfo.get("path") if pinfo else normalize_path(project).lower()

    with CACHE_LOCK:
        if not WATCHED_PROJECTS:
            return {
                "file": file_path,
                "total_errors": 0,
                "returned_errors": 0,
                "offset": offset,
                "limit": limit,
                "active_project": active_alias,
                "has_errors": False,
                "errors": [],
                "warning": "No TypeScript projects are currently being watched. Call 'add_project(project_path)' or 'watch_project(project_path)' with your project directory first.",
            }

        norm_file = normalize_path(file_path).lower()
        norm_raw = file_path.replace("\\", "/").lower()
        file_errors = []

        for cfg_path, data in WATCHED_PROJECTS.items():
            if target_path:
                norm_target = normalize_path(target_path).lower()
                p_dir = data.get("project_dir", "").lower()
                if (
                    norm_target not in p_dir
                    and norm_target != p_dir
                    and not p_dir.startswith(norm_target + "/")
                    and not norm_target.startswith(p_dir + "/")
                ):
                    continue

            for err in data.get("errors", []):
                err_file = err.get("file", "").lower()
                err_rel = err.get("relative_path", "").lower()
                if (
                    err_file == norm_file
                    or err_rel == norm_raw
                    or err_file.endswith("/" + norm_raw.lstrip("/"))
                    or norm_raw in err_file
                    or norm_raw == err_file
                ):
                    file_errors.append(err)

    safe_limit = min(max(1, limit), 100)
    safe_offset = max(0, offset)
    total_file_errs = len(file_errors)
    display_errs = file_errors[safe_offset : safe_offset + safe_limit]
    has_more = total_file_errs > (safe_offset + len(display_errs))

    res: Dict[str, Any] = {
        "file": file_path,
        "total_errors": total_file_errs,
        "returned_errors": len(display_errs),
        "offset": safe_offset,
        "limit": safe_limit,
        "active_project": active_alias,
        "has_errors": total_file_errs > 0,
        "has_more": has_more,
        "truncated": has_more,
        "errors": [_format_tsc_error(e, max_msg_chars=max_message_chars) for e in display_errs],
    }

    if has_more:
        next_offset = safe_offset + len(display_errs)
        res["notice"] = (
            f"... [TRUNCATED: Showing errors {safe_offset + 1}-{next_offset} of {total_file_errs}. "
            f"Use offset={next_offset} to view the next batch] ..."
        )

    return res


@mcp.tool()
def get_error_summary(
    project: Optional[str] = None,
    wait_if_compiling: bool = True,
    wait_timeout: float = 45.0,
) -> Dict[str, Any]:
    """
    Get high-level summary of TypeScript errors across projects without full diagnostic lists.
    Synchronizes with background compiler passes to avoid returning inaccurate 0-error states while compiling.

    Args:
        project: Optional project alias or path to filter summary. Defaults to all or active project.
        wait_if_compiling: If True, waits up to wait_timeout seconds if projects are currently compiling their initial pass (default True).
        wait_timeout: Maximum seconds to wait if a project is actively compiling (default 15.0).
    """
    active_alias = get_active_project_name()
    target_path = None
    if project:
        pinfo = resolve_project_info(project)
        target_path = pinfo.get("path") if pinfo else normalize_path(project).lower()

    if wait_if_compiling:
        events_to_wait = []
        with CACHE_LOCK:
            for data in WATCHED_PROJECTS.values():
                if target_path:
                    norm_target = normalize_path(target_path).lower()
                    p_dir = data.get("project_dir", "").lower()
                    if (
                        norm_target not in p_dir
                        and norm_target != p_dir
                        and not p_dir.startswith(norm_target + "/")
                        and not norm_target.startswith(p_dir + "/")
                    ):
                        continue
                if data.get("status") == "compiling":
                    ev = data.get("ready_event")
                    if ev and not ev.is_set():
                        events_to_wait.append(ev)

        start_w = time.time()
        for ev in events_to_wait:
            rem = max(0.1, wait_timeout - (time.time() - start_w))
            if (time.time() - start_w) >= wait_timeout or not ev.wait(timeout=rem):
                break

    with CACHE_LOCK:
        if not WATCHED_PROJECTS:
            return {
                "total_errors": 0,
                "projects_count": 0,
                "projects": {},
                "active_project": active_alias,
                "warning": "No TypeScript projects are currently being watched. Call 'add_project(project_path)' or 'watch_project(project_path)' with your project directory first.",
            }

        summary = {}
        total = 0
        error_by_code: Dict[str, int] = {}
        compiling_count = 0

        for cfg_path, data in WATCHED_PROJECTS.items():
            if target_path:
                norm_target = normalize_path(target_path).lower()
                p_dir = data.get("project_dir", "").lower()
                if (
                    norm_target not in p_dir
                    and norm_target != p_dir
                    and not p_dir.startswith(norm_target + "/")
                    and not norm_target.startswith(p_dir + "/")
                ):
                    continue

            errs = data.get("errors", [])
            count = len(errs)
            total += count
            status = data.get("status", "unknown")
            if status == "compiling":
                compiling_count += 1
            summary[data["relative_config"]] = {
                "project_dir": data["project_dir"],
                "status": status,
                "errors": count,
                "compile_duration_s": data.get("compile_duration_s"),
            }
            for e in errs:
                code = e.get("code", "UNKNOWN")
                error_by_code[code] = error_by_code.get(code, 0) + 1

        result: Dict[str, Any] = {
            "total_errors": total,
            "projects_count": len(summary),
            "active_project": active_alias,
            "projects": summary,
            "most_common_error_codes": sorted(error_by_code.items(), key=lambda x: x[1], reverse=True)[:5],
        }
        if compiling_count > 0:
            result["is_initial_compilation_pending"] = True
            result["notice"] = f"{compiling_count} project(s) still compiling initial pass."

        return result


# ==============================================================================
# 3. Watcher Management & Backward Compatibility Tools
# ==============================================================================


@mcp.tool()
def list_watched_projects() -> Dict[str, Any]:
    """
    List all active TypeScript projects and tsconfig.json files currently being monitored.
    """
    active_alias = get_active_project_name()
    with CACHE_LOCK:
        projects = []
        for cfg_path, data in WATCHED_PROJECTS.items():
            projects.append(
                {
                    "tsconfig_path": cfg_path,
                    "relative_config": data["relative_config"],
                    "project_dir": data["project_dir"],
                    "status": data["status"],
                    "error_count": len(data.get("errors", [])),
                    "compile_duration_s": data.get("compile_duration_s"),
                    "last_updated": data["last_updated"],
                }
            )

        if not projects:
            return {
                "active_project": active_alias,
                "watched_projects_count": 0,
                "projects": [],
                "status": "standby",
                "message": (
                    "Watcher is currently in standby mode (no projects being monitored). "
                    "Call add_project(project_path, alias='...') or watch_project(project_path) to start monitoring."
                ),
            }

        return {
            "active_project": active_alias,
            "watched_projects_count": len(projects),
            "projects": projects,
        }


@mcp.tool()
def watch_project(
    project_path: str,
    wait_for_initial_compile: bool = True,
    timeout_seconds: float = 30.0,
) -> Dict[str, Any]:
    """
    Dynamically add and watch a new TypeScript project or directory without restarting the MCP server.
    First verifies TypeScript compiler availability, scans for tsconfig.json files, registers project
    to ~/.mcp-win-stdio/tsc_projects.json, and waits for the initial compilation pass.

    Args:
        project_path: Path to project directory or tsconfig.json.
        wait_for_initial_compile: If True, waits up to timeout_seconds for initial compilation to complete before returning (default True).
        timeout_seconds: Maximum seconds to wait for initial compilation (default 30.0).
    """
    return add_project(
        project_path=project_path,
        auto_watch=True,
        wait_for_initial_compile=wait_for_initial_compile,
        timeout_seconds=timeout_seconds,
    )


@mcp.tool()
def restart_tsc_watcher(
    wait_for_initial_compile: bool = True,
    timeout_seconds: float = 30.0,
) -> Dict[str, Any]:
    """
    Restart all active background TypeScript watchers and recompile all projects.
    Preserves all currently watched projects and registered projects in ~/.mcp-win-stdio/tsc_projects.json,
    waiting for compilation passes to finish (by default) to guarantee accurate diagnostic results.

    Args:
        wait_for_initial_compile: If True, waits up to timeout_seconds for all projects to complete compilation before returning (default True).
        timeout_seconds: Maximum seconds to wait for initial compilation across all projects (default 30.0).
    """
    # 1. Collect all currently watched project directories before clearing cache
    watched_dirs = set()
    with CACHE_LOCK:
        for data in WATCHED_PROJECTS.values():
            p = data.get("project_dir")
            if p and os.path.isdir(p):
                watched_dirs.add(p)

    # Also load all registered auto_watch projects from tsc_projects.json
    saved = _load_tsc_projects()
    for alias, pinfo in saved.get("projects", {}).items():
        if pinfo.get("auto_watch", True) and pinfo.get("path"):
            p = pinfo["path"]
            if os.path.isdir(p) and not is_home_or_root_dir(p):
                watched_dirs.add(p)

    _cleanup_watchers()
    with CACHE_LOCK:
        WATCHED_PROJECTS.clear()

    # If no projects were actively watched, check default watch dir fallback
    if not watched_dirs:
        default_root = get_default_watch_dir()
        if default_root and os.path.isdir(default_root):
            watched_dirs.add(default_root)

    if not watched_dirs:
        return {
            "success": True,
            "restarted_configs": [],
            "message": "Flushed watcher cache. Watcher is in standby mode. Call add_project(project_path) or watch_project(project_path) to start monitoring a project.",
        }

    # 2. Re-start watching across all project roots
    all_configs = []
    for d in watched_dirs:
        cfgs = start_watching_project(d)
        all_configs.extend(cfgs)

    if not all_configs:
        return {
            "success": True,
            "restarted_configs": [],
            "message": f"No tsconfig.json configurations found across watched directories: {list(watched_dirs)}",
        }

    # 3. Wait for all background watchers to complete their initial compilation pass
    start_t = time.time()
    compilation_completed = True
    if wait_for_initial_compile:
        compilation_completed = wait_for_projects_compilation(all_configs, timeout=timeout_seconds)

    elapsed_s = round(time.time() - start_t, 2)

    # 4. Gather consolidated summary
    project_summaries = []
    total_errors = 0
    with CACHE_LOCK:
        for cfg in all_configs:
            norm_cfg = normalize_path(cfg)
            if norm_cfg in WATCHED_PROJECTS:
                p_data = WATCHED_PROJECTS[norm_cfg]
                err_cnt = len(p_data.get("errors", []))
                total_errors += err_cnt
                project_summaries.append(
                    {
                        "tsconfig": p_data.get("tsconfig_path", cfg),
                        "relative_config": p_data.get("relative_config"),
                        "project_dir": p_data.get("project_dir"),
                        "status": p_data.get("status"),
                        "error_count": err_cnt,
                        "compile_duration_s": p_data.get("compile_duration_s"),
                    }
                )

    if compilation_completed:
        msg = f"Successfully restarted and recompiled {len(all_configs)} project configuration(s) in {elapsed_s}s ({total_errors} errors found)."
    else:
        msg = f"Restarted watchers for {len(all_configs)} configuration(s). Initial compilation is taking longer than {timeout_seconds}s and continuing in background."

    return {
        "success": True,
        "compilation_completed": compilation_completed,
        "elapsed_seconds": elapsed_s,
        "restarted_configs": all_configs,
        "total_errors": total_errors,
        "projects": project_summaries,
        "message": msg,
    }


if __name__ == "__main__":
    mcp.run()
