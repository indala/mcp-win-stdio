#!/usr/bin/env python3
"""
TypeScript Diagnostic Watcher MCP Server (Python Edition).
Runs background tsc compiler watchers for target projects, maintaining an in-memory
diagnostic cache for instantaneous (0ms latency) TypeScript error inspection.
"""

import atexit
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import threading
import time
from typing import Any, Dict, List, Optional

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("tsc-mcp")

# Global in-memory cache and watcher state
# tsconfig_path -> { "process": Popen, "thread": Thread, "project_dir": str, "errors": list, "pending_errors": list, "status": str, "last_updated": str }
WATCHED_PROJECTS: Dict[str, Dict[str, Any]] = {}
CACHE_LOCK = threading.Lock()

# Regex to parse standard tsc compiler output line
# Example: src/components/App.tsx(42,15): error TS2322: Type 'string' is not assignable to type 'number'.
ERROR_REGEX = re.compile(r"^([^(]+)\((\d+),(\d+)\):\s*(error|warning)\s*(TS\d+):\s*(.+)$")


def get_default_watch_dir() -> str:
    """Get project directory from env, config file, or current working directory."""
    env_dir = os.environ.get("TSC_WATCH_DIR") or os.environ.get("PROJECT_ROOT")
    if env_dir and os.path.isdir(env_dir):
        return os.path.abspath(env_dir)

    # Check ~/.mcp-win-stdio/config.json
    try:
        from mcp_win_stdio.core.config import load_config
        cfg = load_config()
        stored_dir = cfg.get("tsc_watch_dir")
        if stored_dir and os.path.isdir(stored_dir):
            return os.path.abspath(stored_dir)
    except Exception:
        pass

    return os.path.abspath(os.getcwd())


def normalize_path(p: str) -> str:
    return os.path.abspath(p).replace("\\", "/")


def find_tsconfigs(base_dir: str, max_depth: int = 4) -> List[str]:
    """Find all tsconfig.json files skipping heavy build/vendor folders."""
    ignore_dirs = {
        "node_modules", ".git", ".next", ".nuxt", "dist", "build",
        "out", ".output", "target", "bin", "obj", "__pycache__", ".cache",
        "coverage", ".turbo"
    }
    configs = []
    base_p = Path(base_dir)
    if not base_p.exists():
        return configs

    for root, dirs, files in os.walk(base_dir):
        # Prune ignored directories in-place
        dirs[:] = [d for d in dirs if d.lower() not in ignore_dirs]
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
        "relative_path": normalize_path(rel_path),
        "line": int(line_num),
        "column": int(col_num),
        "severity": severity.lower(),
        "code": code,
        "message": message.strip(),
    }


def _watcher_loop(tsconfig_path: str, root_dir: str) -> None:
    """Worker thread running tsc --noEmit --watch in background."""
    project_dir = os.path.dirname(tsconfig_path)
    cmd_base = resolve_tsc_command(project_dir)

    if not cmd_base:
        with CACHE_LOCK:
            if tsconfig_path in WATCHED_PROJECTS:
                WATCHED_PROJECTS[tsconfig_path]["status"] = "error: tsc binary not found (install typescript)"
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
                WATCHED_PROJECTS[tsconfig_path]["status"] = "watching"

        pending_errors: List[Dict[str, Any]] = []

        for raw_line in proc.stdout:
            line = raw_line.rstrip()
            if not line:
                continue

            # Check completion markers
            if "Found 0 errors." in line or "Found " in line and "Watching for file changes." in line:
                with CACHE_LOCK:
                    if tsconfig_path in WATCHED_PROJECTS:
                        WATCHED_PROJECTS[tsconfig_path]["errors"] = list(pending_errors)
                        WATCHED_PROJECTS[tsconfig_path]["last_updated"] = datetime.now(timezone.utc).isoformat()
                pending_errors = []
            elif "Starting compilation in watch mode..." in line or "File change detected." in line:
                pending_errors = []
            else:
                err = parse_tsc_line(line, project_dir, root_dir)
                if err:
                    pending_errors.append(err)

    except Exception as e:
        with CACHE_LOCK:
            if tsconfig_path in WATCHED_PROJECTS:
                WATCHED_PROJECTS[tsconfig_path]["status"] = f"error: {str(e)}"


def start_watching_project(target_dir: str) -> List[str]:
    """Scan and start background watchers for all tsconfig.json in target_dir."""
    abs_root = os.path.abspath(target_dir)
    configs = find_tsconfigs(abs_root)

    for cfg in configs:
        norm_cfg = normalize_path(cfg)
        with CACHE_LOCK:
            if norm_cfg in WATCHED_PROJECTS and WATCHED_PROJECTS[norm_cfg].get("process"):
                # Already watching
                continue

            WATCHED_PROJECTS[norm_cfg] = {
                "project_dir": normalize_path(os.path.dirname(cfg)),
                "tsconfig_path": norm_cfg,
                "relative_config": normalize_path(os.path.relpath(cfg, abs_root)),
                "errors": [],
                "status": "initializing",
                "last_updated": datetime.now(timezone.utc).isoformat(),
                "process": None,
            }

        t = threading.Thread(target=_watcher_loop, args=(norm_cfg, abs_root), daemon=True)
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

# Initialize on import
_initial_root = get_default_watch_dir()
if os.path.isdir(_initial_root):
    start_watching_project(_initial_root)


# ==========================================
# MCP TOOLS
# ==========================================

@mcp.tool()
def get_tsc_errors(project_path: Optional[str] = None, tsconfig_path: Optional[str] = None) -> Dict[str, Any]:
    """
    Get all active TypeScript compiler errors across watched projects (0ms latency from memory).
    Can filter by specific project directory or tsconfig.json path.
    """
    with CACHE_LOCK:
        all_errors = []
        projects_summary = []

        for cfg_path, data in WATCHED_PROJECTS.items():
            if tsconfig_path and normalize_path(tsconfig_path) != cfg_path:
                continue
            if project_path and normalize_path(project_path) not in data["project_dir"]:
                continue

            errs = data.get("errors", [])
            all_errors.extend(errs)
            projects_summary.append({
                "tsconfig": data["relative_config"],
                "status": data["status"],
                "error_count": len(errs),
                "last_updated": data["last_updated"],
            })

        return {
            "total_errors": len(all_errors),
            "projects": projects_summary,
            "errors": all_errors,
        }


@mcp.tool()
def get_file_errors(file_path: str) -> Dict[str, Any]:
    """
    Get TypeScript compiler errors for a specific file (.ts, .tsx, .js, .jsx).
    """
    norm_file = normalize_path(file_path)
    file_errors = []

    with CACHE_LOCK:
        for cfg_path, data in WATCHED_PROJECTS.items():
            for err in data.get("errors", []):
                if err["file"] == norm_file or err["relative_path"] == norm_file or file_path.replace("\\", "/") in err["file"]:
                    file_errors.append(err)

    return {
        "file": file_path,
        "error_count": len(file_errors),
        "has_errors": len(file_errors) > 0,
        "errors": file_errors,
    }


@mcp.tool()
def get_error_summary() -> Dict[str, Any]:
    """
    Get high-level summary of TypeScript errors across all projects without full diagnostic lists.
    """
    with CACHE_LOCK:
        summary = {}
        total = 0
        error_by_code: Dict[str, int] = {}

        for cfg_path, data in WATCHED_PROJECTS.items():
            errs = data.get("errors", [])
            count = len(errs)
            total += count
            summary[data["relative_config"]] = {
                "status": data["status"],
                "errors": count,
            }
            for e in errs:
                code = e.get("code", "UNKNOWN")
                error_by_code[code] = error_by_code.get(code, 0) + 1

        return {
            "total_errors": total,
            "projects_count": len(WATCHED_PROJECTS),
            "projects": summary,
            "most_common_error_codes": sorted(error_by_code.items(), key=lambda x: x[1], reverse=True)[:5],
        }


@mcp.tool()
def list_watched_projects() -> Dict[str, Any]:
    """
    List all active TypeScript projects and tsconfig.json files currently being monitored.
    """
    with CACHE_LOCK:
        projects = []
        for cfg_path, data in WATCHED_PROJECTS.items():
            projects.append({
                "tsconfig_path": cfg_path,
                "relative_config": data["relative_config"],
                "project_dir": data["project_dir"],
                "status": data["status"],
                "error_count": len(data.get("errors", [])),
                "last_updated": data["last_updated"],
            })

        return {
            "watched_projects_count": len(projects),
            "projects": projects,
        }


@mcp.tool()
def watch_project(project_path: str) -> Dict[str, Any]:
    """
    Dynamically add and watch a new TypeScript project or directory without restarting the MCP server.
    """
    if not os.path.exists(project_path):
        return {"success": False, "error": f"Path not found: {project_path}"}

    configs = start_watching_project(project_path)
    return {
        "success": True,
        "project_path": normalize_path(project_path),
        "found_tsconfigs": configs,
        "message": f"Started background TypeScript watchers for {len(configs)} configuration(s).",
    }


@mcp.tool()
def restart_tsc_watcher() -> Dict[str, Any]:
    """
    Restart all active background TypeScript watchers and refresh diagnostics.
    """
    _cleanup_watchers()
    with CACHE_LOCK:
        WATCHED_PROJECTS.clear()

    default_root = get_default_watch_dir()
    configs = start_watching_project(default_root)
    return {
        "success": True,
        "restarted_configs": configs,
        "message": f"Restarted watchers for {len(configs)} project(s).",
    }
