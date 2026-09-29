#!/usr/bin/env python3
"""
TypeScript Diagnostic Watcher MCP Server (Python Edition).
Runs background tsc compiler watchers for target projects, maintaining an in-memory
diagnostic cache for instantaneous (0ms latency) TypeScript error inspection.
"""

import atexit
from datetime import datetime, timezone
import json
import ntpath
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import threading
import time
from typing import Any, Dict, List, Optional, Union

try:
    from mcp.server.mcpserver import MCPServer as FastMCP
except (ImportError, ModuleNotFoundError):
    from mcp.server.fastmcp import FastMCP

mcp = FastMCP("tsc-mcp")

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
        for env_var in ("APPDATA", "LOCALAPPDATA", "TEMP", "TMP", "WINDIR", "SYSTEMROOT", "PROGRAMFILES", "PROGRAMFILES(X86)"):
            val = os.environ.get(env_var)
            if val:
                val_resolved = str(Path(val).resolve()).lower()
                if resolved_str == val_resolved or resolved_str.startswith(val_resolved + "\\") or resolved_str.startswith(val_resolved + "/"):
                    return True

        # Check path parts directly for AppData or Windows system directories
        parts_lower = [part.lower() for part in resolved.parts]
        if any(part in ("appdata", "application data", "windows", "system32") for part in parts_lower):
            return True

    except Exception:
        pass

    return False


def get_default_watch_dir() -> Optional[str]:
    """
    Get project directory from user environment variable (TSC_WATCH_DIR or PROJECT_ROOT) or stored config.
    Returns None if not configured or if configured to a system/home/AppData directory.
    NOTE: Does NOT default to cwd or admin home to avoid unintended scans.
    """
    env_dir = os.environ.get("TSC_WATCH_DIR") or os.environ.get("PROJECT_ROOT")
    if env_dir:
        abs_env = os.path.abspath(env_dir)
        if os.path.isdir(abs_env) and not is_home_or_root_dir(abs_env):
            return abs_env

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
    return os.path.abspath(p).replace("\\", "/")


def find_tsconfigs(base_dir: str, max_depth: int = 4) -> List[str]:
    """Find all tsconfig.json files skipping heavy build/vendor folders."""
    ignore_dirs = {
        "node_modules", ".git", ".next", ".nuxt", "dist", "build",
        "out", ".output", "target", "bin", "obj", "__pycache__", ".cache",
        "coverage", ".turbo", "appdata", ".vscode", ".gemini", ".cursor",
        ".cargo", ".rustup", "venv", ".venv", "env", ".env", "site-packages",
        "local settings", "application data"
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
        "relative_path": normalize_path(rel_path),
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
            if "Found 0 errors." in line or ("Found " in line and "Watching for file changes." in line):
                with CACHE_LOCK:
                    if tsconfig_path in WATCHED_PROJECTS:
                        WATCHED_PROJECTS[tsconfig_path]["errors"] = list(pending_errors)
                        WATCHED_PROJECTS[tsconfig_path]["status"] = "watching"
                        WATCHED_PROJECTS[tsconfig_path]["last_updated"] = datetime.now(timezone.utc).isoformat()
                pending_errors = []
            elif "Starting compilation in watch mode..." in line or "File change detected." in line:
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
                "cmd_base": cmd_base,
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

# Startup initialization:
# ONLY start watching if user explicitly configured TSC_WATCH_DIR, PROJECT_ROOT, or stored config.
# If not configured, the watcher starts in standby mode (waiting for user/Claude to call watch_project).
# This avoids any scanning of C:\Users\admin or AppData when spawned by Claude.
_initial_root = get_default_watch_dir()
if _initial_root and os.path.isdir(_initial_root) and not is_home_or_root_dir(_initial_root):
    _tsc_status = check_tsc_available(_initial_root)
    if _tsc_status["available"]:
        start_watching_project(_initial_root, cmd_base=_tsc_status["command"])



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


# ==========================================
# MCP TOOLS
# ==========================================

@mcp.tool()
def get_tsc_errors(
    project_path: Optional[str] = None,
    tsconfig_path: Optional[str] = None,
    error_code: Optional[str] = None,
    limit: int = 30,
    offset: int = 0,
    max_message_chars: int = 300,
) -> Dict[str, Any]:
    """
    Get active TypeScript compiler errors across watched projects (0ms latency from memory cache).
    Features automatic context window protection, pagination, error code filtering, and token-safe message truncation.
    
    Args:
        project_path: Optional filter by project directory substring.
        tsconfig_path: Optional filter by specific tsconfig.json file path.
        error_code: Optional filter by TS error code (e.g. 'TS2304', 'TS2322', 'TS2339').
        limit: Maximum number of detailed error objects to return per batch (default 30, max 100).
        offset: Starting index offset for pagination (default 0).
        max_message_chars: Maximum character length for individual error messages (default 300).
    """
    with CACHE_LOCK:
        if not WATCHED_PROJECTS:
            return {
                "success": True,
                "total_errors": 0,
                "returned_errors": 0,
                "offset": offset,
                "limit": limit,
                "projects": [],
                "errors": [],
                "warning": "No TypeScript projects are currently being watched. Call 'watch_project(project_path)' with your project directory first, or configure TSC_WATCH_DIR.",
            }

        all_errors = []
        projects_summary = []
        initializing_count = 0
        safe_limit = min(max(1, limit), 100)
        safe_offset = max(0, offset)

        for cfg_path, data in WATCHED_PROJECTS.items():
            if tsconfig_path and normalize_path(tsconfig_path) != cfg_path:
                continue
            if project_path and normalize_path(project_path) not in data["project_dir"]:
                continue

            errs = data.get("errors", [])
            status = data.get("status", "unknown")
            if status == "initializing":
                initializing_count += 1

            for e in errs:
                if error_code and e.get("code", "").upper() != error_code.strip().upper():
                    continue
                all_errors.append(e)

            projects_summary.append({
                "tsconfig": data["relative_config"],
                "project_dir": data["project_dir"],
                "status": status,
                "error_count": len(errs),
                "last_updated": data["last_updated"],
            })

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

        if initializing_count > 0:
            result["status_notice"] = f"{initializing_count} project(s) still compiling initial pass. Errors will update in 1-2 seconds."

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
                "Typo in variable or class name."
            ],
            "resolutions": [
                "Add import statement: import { X } from './module';",
                "If using Node globals: run 'npm install --save-dev @types/node' and add 'node' to compilerOptions.types in tsconfig.json.",
                "If ambient library global: declare global variable: declare const X: any;"
            ]
        },
        "TS2322": {
            "title": "Type 'A' is not assignable to type 'B'",
            "category": "Type Mismatch",
            "common_causes": [
                "Passing a null or undefined value to a strictly typed property (strictNullChecks).",
                "Object is missing required fields defined in an interface/type.",
                "Incompatible primitive types (e.g. string passed where number is expected)."
            ],
            "resolutions": [
                "Check for null/undefined: provide default fallback (val ?? defaultValue) or use optional type (B | null).",
                "Ensure all mandatory fields of interface 'B' are populated.",
                "Use explicit type narrowing (typeof, instanceof, in operator) before assignment."
            ]
        },
        "TS2339": {
            "title": "Property 'X' does not exist on type 'Y'",
            "category": "Property Access Error",
            "common_causes": [
                "Accessing property on union type where not all union members have property 'X'.",
                "Accessing property on 'unknown' or 'never' type.",
                "Missing property definition on interface or class."
            ],
            "resolutions": [
                "Use optional chaining: object?.X",
                "Narrow union type using type guards: if ('X' in obj) { obj.X }",
                "If 'unknown' type: cast or validate before access: (obj as Record<string, any>).X",
                "Extend interface definition with optional or required field: X?: string;"
            ]
        },
        "TS2554": {
            "title": "Expected N arguments, but got M",
            "category": "Function Signature Mismatch",
            "common_causes": [
                "Calling function with too few or too many arguments.",
                "Function definition changed without updating callers."
            ],
            "resolutions": [
                "Provide all mandatory arguments, or make unused arguments optional in function declaration: fn(a: string, b?: number).",
                "Use object destructuring for parameter lists: fn({ a, b = defaultVal }: Options)."
            ]
        },
        "TS7016": {
            "title": "Could not find a declaration file for module 'X'",
            "category": "Missing Type Definitions",
            "common_causes": [
                "Third-party npm package lacks bundled TypeScript declaration (.d.ts) files."
            ],
            "resolutions": [
                "Install DefinitelyTyped types: npm install --save-dev @types/X",
                "If no @types exists: create a ambient declaration file (e.g. 'src/declarations.d.ts') with: declare module 'X';"
            ]
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
                "Use early guard return: if (!obj) return;"
            ]
        }
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
            "provided_message": message
        }

    return {
        "success": True,
        "error_code": code,
        "category": "General TypeScript Error",
        "guidance": "Check TypeScript documentation for error code " + code + ". Ensure types match interface declarations and strict null checks are satisfied.",
        "provided_message": message
    }


@mcp.tool()
def get_error_category_breakdown() -> Dict[str, Any]:
    """
    [Advanced Tool] Get an architectural aggregate breakdown of active errors grouped by semantic category
    (Missing Imports, Type Mismatches, Property Errors, Nullability, Syntax) to plan refactors.
    """
    with CACHE_LOCK:
        if not WATCHED_PROJECTS:
            return {"success": True, "total_errors": 0, "categories": {}, "message": "No active projects watched."}

        categories: Dict[str, List[Dict[str, Any]]] = {
            "missing_imports_or_types": [],
            "type_mismatches": [],
            "property_access_errors": [],
            "nullability_and_undefined": [],
            "function_signature_mismatches": [],
            "other": []
        }

        total = 0
        for data in WATCHED_PROJECTS.values():
            for e in data.get("errors", []):
                total += 1
                c = e.get("code", "")
                item = {
                    "code": c,
                    "file": e.get("relative_path") or e.get("file"),
                    "line": e.get("line"),
                    "message": e.get("message")
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
                "sample_errors": [_format_tsc_error(it, max_msg_chars=200) for it in items[:6]]
            }

        return {
            "success": True,
            "total_errors": total,
            "category_summary": {k: v["count"] for k, v in capped_cats.items()},
            "details": capped_cats
        }


@mcp.tool()
def get_file_errors(
    file_path: str,
    limit: int = 30,
    offset: int = 0,
    max_message_chars: int = 300,
) -> Dict[str, Any]:
    """
    Get TypeScript compiler errors for a specific file (.ts, .tsx, .js, .jsx) with context window protection.
    
    Args:
        file_path: Relative or absolute path to the TypeScript/JavaScript file.
        limit: Max errors to return in this batch (default 30, max 100).
        offset: Starting offset for pagination (default 0).
        max_message_chars: Maximum character length for individual error messages (default 300).
    """
    with CACHE_LOCK:
        if not WATCHED_PROJECTS:
            return {
                "file": file_path,
                "total_errors": 0,
                "returned_errors": 0,
                "offset": offset,
                "limit": limit,
                "has_errors": False,
                "errors": [],
                "warning": "No TypeScript projects are currently being watched. Call 'watch_project(project_path)' with your project directory first.",
            }

        norm_file = normalize_path(file_path)
        file_errors = []

        for cfg_path, data in WATCHED_PROJECTS.items():
            for err in data.get("errors", []):
                if err["file"] == norm_file or err["relative_path"] == norm_file or file_path.replace("\\", "/") in err["file"]:
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
def get_error_summary() -> Dict[str, Any]:
    """
    Get high-level summary of TypeScript errors across all projects without full diagnostic lists.
    """
    with CACHE_LOCK:
        if not WATCHED_PROJECTS:
            return {
                "total_errors": 0,
                "projects_count": 0,
                "projects": {},
                "warning": "No TypeScript projects are currently being watched. Call 'watch_project(project_path)' with your project directory first.",
            }

        summary = {}
        total = 0
        error_by_code: Dict[str, int] = {}
        initializing_count = 0

        for cfg_path, data in WATCHED_PROJECTS.items():
            errs = data.get("errors", [])
            count = len(errs)
            total += count
            status = data.get("status", "unknown")
            if status == "initializing":
                initializing_count += 1
            summary[data["relative_config"]] = {
                "project_dir": data["project_dir"],
                "status": status,
                "errors": count,
            }
            for e in errs:
                code = e.get("code", "UNKNOWN")
                error_by_code[code] = error_by_code.get(code, 0) + 1

        result: Dict[str, Any] = {
            "total_errors": total,
            "projects_count": len(WATCHED_PROJECTS),
            "projects": summary,
            "most_common_error_codes": sorted(error_by_code.items(), key=lambda x: x[1], reverse=True)[:5],
        }
        if initializing_count > 0:
            result["notice"] = f"{initializing_count} project(s) still compiling initial pass."

        return result


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

        if not projects:
            return {
                "watched_projects_count": 0,
                "projects": [],
                "status": "standby",
                "message": (
                    "Watcher is currently in standby mode (no projects being monitored). "
                    "Define TSC_WATCH_DIR in your MCP environment or call watch_project(project_path) to start monitoring."
                ),
            }

        return {
            "watched_projects_count": len(projects),
            "projects": projects,
        }


@mcp.tool()
def watch_project(project_path: str) -> Dict[str, Any]:
    """
    Dynamically add and watch a new TypeScript project or directory without restarting the MCP server.
    First verifies TypeScript compiler availability and rejects system/AppData directories.
    """
    if not os.path.exists(project_path):
        return {"success": False, "error": f"Path not found: {project_path}"}

    # If user or LLM passed a file path, resolve to its containing directory
    if os.path.isfile(project_path):
        project_path = os.path.dirname(project_path)

    abs_project = os.path.abspath(project_path)

    # 1. Safety check: prevent crawling user home, root drive, or AppData
    if is_home_or_root_dir(abs_project):
        return {
            "success": False,
            "error": f"Refusing to watch system, user home, or AppData directory: '{abs_project}'. Please specify a specific project directory.",
            "guidance": "Provide the path to your project folder (e.g. 'C:/Users/admin/projects/my-app').",
        }

    # 2. Check for tsc FIRST before scanning files
    tsc_check = check_tsc_available(abs_project)
    if not tsc_check["available"]:
        return {
            "success": False,
            "error": tsc_check["error"],
            "guidance": tsc_check["guidance"],
            "project_path": normalize_path(abs_project),
        }

    # 3. Scan for tsconfig.json and start watchers
    configs = start_watching_project(abs_project, cmd_base=tsc_check["command"])
    if not configs:
        return {
            "success": False,
            "project_path": normalize_path(abs_project),
            "found_tsconfigs": [],
            "error": f"No tsconfig.json found in '{abs_project}' (searched up to 4 directories deep). Make sure this directory contains a TypeScript project.",
        }

    return {
        "success": True,
        "project_path": normalize_path(abs_project),
        "found_tsconfigs": configs,
        "compiler_type": tsc_check.get("type"),
        "compiler_command": " ".join(tsc_check.get("command", [])),
        "message": f"Verified 'tsc' ({tsc_check.get('type')}) and started background watchers for {len(configs)} configuration(s).",
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
    if not default_root:
        return {
            "success": True,
            "restarted_configs": [],
            "message": "Flushed watcher cache. Watcher is in standby mode. Set TSC_WATCH_DIR or call watch_project(project_path) to start monitoring a project.",
        }

    configs = start_watching_project(default_root)
    return {
        "success": True,
        "restarted_configs": configs,
        "message": f"Restarted watchers for {len(configs)} project(s).",
    }


if __name__ == "__main__":
    mcp.run()

