"""
Workspace Explorer MCP Server
High-performance, token-safe directory exploration, smart .gitignore resolution,
collapsible heavy-folder summaries, RapidFuzz fuzzy search, code outline extraction,
in-file grep, windowed reading, and disk export.
"""

import ast
from datetime import datetime, timedelta, timezone
import fnmatch
import hashlib
import json
import mimetypes
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
from typing import Any, Dict, List, Literal, Optional, Set, Tuple, Union

try:
    from mcp.server.mcpserver import MCPServer as FastMCP
except (ImportError, ModuleNotFoundError):
    from mcp.server.fastmcp import FastMCP
import pathspec
from rapidfuzz import fuzz, process

# Initialize FastMCP Server
mcp = FastMCP("workspace-explorer")

# Directories known to be heavy or contain build caches
HEAVY_BUILD_DIRS = {
    "node_modules",
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
    ".venv",
    "venv",
    "env",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".cache",
    "coverage",
    ".turbo",
    ".parcel-cache",
}

GIT_DIRS = {
    ".git",
    ".hg",
    ".svn",
}

BINARY_EXTENSIONS = {
    ".exe", ".dll", ".so", ".dylib", ".bin", ".iso", ".img",
    ".zip", ".tar", ".gz", ".7z", ".rar", ".bz2", ".xz",
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".bmp", ".tiff",
    ".mp3", ".wav", ".flac", ".ogg", ".aac",
    ".mp4", ".mkv", ".avi", ".mov", ".wmv", ".webm",
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".pyc", ".pyo", ".pyd", ".class", ".jar", ".war",
    ".ttf", ".otf", ".woff", ".woff2", ".eot"
}


# ==========================================
# HELPER UTILITIES
# ==========================================

def _format_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.2f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"


def _is_hidden(path: Path) -> bool:
    try:
        if path.name.startswith("."):
            return True
        if os.name == "nt":
            attrs = path.stat().st_file_attributes
            return bool(attrs & stat.FILE_ATTRIBUTE_HIDDEN)
    except Exception:
        pass
    return False


def _is_binary_file(path: Path) -> bool:
    if path.suffix.lower() in BINARY_EXTENSIONS:
        return True
    try:
        with open(path, "rb") as f:
            chunk = f.read(1024)
            if b"\x00" in chunk:
                return True
    except Exception:
        pass
    return False


def _read_file_text_with_fallback(path: Path) -> Tuple[str, str]:
    encodings = ["utf-8", "utf-8-sig", "latin-1", "cp1252", "utf-16"]
    for enc in encodings:
        try:
            with open(path, "r", encoding=enc) as f:
                return f.read(), enc
        except (UnicodeDecodeError, UnicodeError):
            continue
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read(), "utf-8 (lossy)"


def _parse_relative_time(time_str: str) -> Optional[datetime]:
    time_str = time_str.strip().lower()
    now = datetime.now(timezone.utc)
    match = re.match(r"^(\d+)\s*([smhdw])$", time_str)
    if match:
        val = int(match.group(1))
        unit = match.group(2)
        if unit == "s":
            return now - timedelta(seconds=val)
        elif unit == "m":
            return now - timedelta(minutes=val)
        elif unit == "h":
            return now - timedelta(hours=val)
        elif unit == "d":
            return now - timedelta(days=val)
        elif unit == "w":
            return now - timedelta(weeks=val)
    try:
        dt = datetime.fromisoformat(time_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def _get_collapsed_summary(dir_path: Path, max_depth: int = 2) -> Tuple[int, int]:
    """Quickly estimate item count and total size for a collapsed directory without deep traversal."""
    total_count = 0
    total_bytes = 0
    root_depth = len(dir_path.parts)
    try:
        for root, dirs, files in os.walk(dir_path):
            curr_depth = len(Path(root).parts) - root_depth
            if curr_depth >= max_depth:
                dirs[:] = []
            total_count += len(files) + len(dirs)
            for f in files:
                try:
                    total_bytes += (Path(root) / f).stat().st_size
                except Exception:
                    pass
    except Exception:
        pass
    return total_count, total_bytes


def _load_gitignore_spec(root: Path) -> Optional[pathspec.PathSpec]:
    """Find and load .gitignore / .mcpignore rules from root or parent directory."""
    patterns = []
    # Check .gitignore
    gi = root / ".gitignore"
    if gi.is_file():
        try:
            with open(gi, "r", encoding="utf-8", errors="replace") as f:
                patterns.extend(f.readlines())
        except Exception:
            pass
    # Check .mcpignore if user created one
    mi = root / ".mcpignore"
    if mi.is_file():
        try:
            with open(mi, "r", encoding="utf-8", errors="replace") as f:
                patterns.extend(f.readlines())
        except Exception:
            pass

    if not patterns:
        return None
    try:
        return pathspec.PathSpec.from_lines("gitwildmatch", patterns)
    except Exception:
        return None


def _matches_gitignore(gi_spec: Optional[pathspec.PathSpec], rel_posix: str, is_dir: bool = False) -> bool:
    """Accurately match relative path against gitignore spec, supporting trailing slashes on directory patterns."""
    if not gi_spec:
        return False
    try:
        if gi_spec.match_file(rel_posix):
            return True
        if is_dir and gi_spec.match_file(rel_posix.rstrip("/") + "/"):
            return True
    except Exception:
        pass
    return False



# ==========================================
# 1. DIRECTORY LISTING & NAVIGATION
# ==========================================

@mcp.tool()
def list_dir(
    path: str,
    include_hidden: bool = False,
    filter_pattern: Optional[str] = None,
    sort_by: Literal["name", "size", "modified", "extension", "type"] = "name",
    sort_desc: bool = False,
    offset: int = 0,
    limit: int = 100,
) -> Dict[str, Any]:
    """
    List contents of a directory with rich file and folder metadata (PowerShell Get-ChildItem style).
    If a folder is directly requested, it is ALWAYS explored even if it is in an ignore list.
    
    Args:
        path: Path to the directory.
        include_hidden: Include hidden files and folders (default False).
        filter_pattern: Optional glob pattern to filter entries (e.g. "*.py", "data_*").
        sort_by: Field to sort by: 'name', 'size', 'modified', 'extension', 'type'.
        sort_desc: Sort in descending order.
        offset: Skip first N items (pagination).
        limit: Maximum number of items to return (default 100, max 500).
    """
    p = Path(path).resolve()
    if not p.exists():
        return {"error": f"Path not found: {p}"}
    if not p.is_dir():
        return {"error": f"Path is not a directory: {p}"}

    limit = min(max(1, limit), 500)
    items = []

    try:
        with os.scandir(p) as entries:
            for entry in entries:
                entry_path = Path(entry.path)
                if not include_hidden and _is_hidden(entry_path):
                    continue
                if filter_pattern and not fnmatch.fnmatch(entry.name, filter_pattern):
                    continue

                try:
                    st = entry.stat()
                    is_dir = entry.is_dir(follow_symlinks=False)
                    size = 0 if is_dir else st.st_size
                    mtime = datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).isoformat()
                    
                    child_count = None
                    is_heavy = False
                    if is_dir:
                        is_heavy = entry.name in HEAVY_BUILD_DIRS or entry.name in GIT_DIRS
                        try:
                            child_count = len(os.listdir(entry.path))
                        except Exception:
                            child_count = None

                    items.append({
                        "name": entry.name,
                        "path": str(entry_path),
                        "is_dir": is_dir,
                        "type": "directory" if is_dir else "file",
                        "extension": entry_path.suffix.lower() if not is_dir else "",
                        "size_bytes": size,
                        "size_formatted": _format_size(size) if not is_dir else (
                            f"{child_count} items (heavy build/cache)" if is_heavy else f"{child_count} items"
                        ) if child_count is not None else "dir",
                        "child_count": child_count,
                        "is_heavy_dir": is_heavy,
                        "modified_at": mtime,
                        "is_symlink": entry.is_symlink(),
                    })
                except Exception:
                    continue

        total_count = len(items)

        # Sorting
        if sort_by == "name":
            items.sort(key=lambda x: x["name"].lower(), reverse=sort_desc)
        elif sort_by == "size":
            items.sort(key=lambda x: x["size_bytes"], reverse=sort_desc)
        elif sort_by == "modified":
            items.sort(key=lambda x: x["modified_at"], reverse=sort_desc)
        elif sort_by == "extension":
            items.sort(key=lambda x: (not x["is_dir"], x["extension"], x["name"].lower()), reverse=sort_desc)
        elif sort_by == "type":
            items.sort(key=lambda x: (x["is_dir"], x["name"].lower()), reverse=sort_desc)

        paginated_items = items[offset : offset + limit]

        return {
            "directory": str(p),
            "total_items": total_count,
            "offset": offset,
            "limit": limit,
            "has_more": (offset + limit) < total_count,
            "items": paginated_items,
        }
    except Exception as e:
        return {"error": f"Failed to list directory: {str(e)}"}


# ==========================================
# 2. DIRECTORY TREE (SMART COLLAPSING & NOISE SAFE)
# ==========================================

@mcp.tool()
def get_directory_tree(
    path: str,
    max_depth: int = 2,
    include_files: bool = True,
    only_dirs: bool = False,
    ignore_mode: Literal["smart", "git_only", "none"] = "smart",
    respect_gitignore: bool = True,
    collapse_heavy_dirs: bool = True,
    max_nodes: int = 250,
    tree_style: Literal["ascii", "unicode"] = "ascii",
    format: Literal["tree", "json"] = "tree",
) -> Union[str, Dict[str, Any]]:
    """
    Render a clean, token-safe directory hierarchy with smart collapsing and .gitignore awareness.
    Instead of blowing context on node_modules or .git, it collapses them into informative summary nodes.
    
    Args:
        path: Root directory path.
        max_depth: Maximum recursion depth (1 to 5, default 2).
        include_files: Whether to include files in the output (default True).
        only_dirs: If True, only lists subdirectories.
        ignore_mode: 'smart' (collapses build/cache dirs and honors gitignore), 'git_only' (only collapses .git), or 'none' (raw).
        respect_gitignore: Honor .gitignore/.mcpignore rules found in the root (default True).
        collapse_heavy_dirs: Collapse heavy directories into summary nodes instead of expanding their children (default True).
        max_nodes: Hard safety circuit-breaker cap on total displayed items (default 250).
        tree_style: 'ascii' (|--, \\--) or 'unicode' (├──, └──).
        format: Output format: 'tree' (formatted indented text) or 'json'.
    """
    root = Path(path).resolve()
    if not root.exists():
        return f"Error: Path not found: {root}"
    if not root.is_dir():
        return f"Error: Path is not a directory: {root}"

    max_depth = min(max(1, max_depth), 5)
    gi_spec = _load_gitignore_spec(root) if respect_gitignore and ignore_mode == "smart" else None

    # Connectors
    if tree_style == "unicode":
        c_branch, c_last, c_pipe = "├── ", "└── ", "│   "
    else:
        c_branch, c_last, c_pipe = "|-- ", "\\-- ", "|   "

    nodes_count = [0]
    circuit_broken = [False]

    if format == "tree":
        lines = [f"{root.name}/ ({str(root)})"]
        stats = {"dirs": 0, "files": 0, "collapsed": 0}

        def _walk_tree(current: Path, prefix: str, depth: int):
            if depth > max_depth or circuit_broken[0]:
                return
            try:
                entries = sorted(os.scandir(current), key=lambda e: (not e.is_dir(), e.name.lower()))
            except Exception:
                return

            filtered_entries = []
            for e in entries:
                e_path = Path(e.path)
                rel_posix = str(e_path.relative_to(root)).replace("\\", "/")

                # Hidden check
                if _is_hidden(e_path) and e.name not in GIT_DIRS:
                    continue

                # Gitignore check
                if _matches_gitignore(gi_spec, rel_posix, is_dir=e.is_dir()):
                    if not (e.is_dir() and collapse_heavy_dirs):
                        continue

                if only_dirs and not e.is_dir():
                    continue
                if not include_files and not e.is_dir():
                    continue
                filtered_entries.append(e)

            count = len(filtered_entries)
            for i, entry in enumerate(filtered_entries):
                if nodes_count[0] >= max_nodes:
                    circuit_broken[0] = True
                    lines.append(f"{prefix}... [Circuit breaker: Reached {max_nodes} items safety cap. Narrow down with subfolder or lower max_depth]")
                    return

                is_last = (i == count - 1)
                connector = c_last if is_last else c_branch
                sub_prefix = "    " if is_last else c_pipe
                e_path = Path(entry.path)

                if entry.is_dir():
                    stats["dirs"] += 1
                    nodes_count[0] += 1
                    name = entry.name

                    # Should we collapse this directory?
                    should_collapse = False
                    if collapse_heavy_dirs:
                        if ignore_mode in ("smart", "git_only") and name in GIT_DIRS:
                            should_collapse = True
                        elif ignore_mode == "smart" and name in HEAVY_BUILD_DIRS:
                            should_collapse = True
                        elif _matches_gitignore(gi_spec, rel_posix, is_dir=True):
                            should_collapse = True

                    if should_collapse:
                        stats["collapsed"] += 1
                        c_items, c_bytes = _get_collapsed_summary(e_path)
                        lines.append(
                            f"{prefix}{connector}{name}/ [COLLAPSED: ~{c_items} items, {_format_size(c_bytes)} -> target directly to explore]"
                        )
                    else:
                        lines.append(f"{prefix}{connector}{name}/")
                        _walk_tree(e_path, prefix + sub_prefix, depth + 1)
                else:
                    stats["files"] += 1
                    nodes_count[0] += 1
                    sz = ""
                    try:
                        sz = f" ({_format_size(entry.stat().st_size)})"
                    except Exception:
                        pass
                    lines.append(f"{prefix}{connector}{entry.name}{sz}")

        _walk_tree(root, "", 1)
        summary = (
            f"\n\nTotal: {stats['dirs']} directories, {stats['files']} files "
            f"({stats['collapsed']} collapsed heavy folders, Max depth: {max_depth})"
        )
        return "\n".join(lines) + summary

    else:
        # JSON format
        def _walk_json(current: Path, depth: int) -> Dict[str, Any]:
            node = {"name": current.name, "path": str(current), "type": "directory", "children": []}
            if depth > max_depth or circuit_broken[0]:
                return node

            try:
                entries = sorted(os.scandir(current), key=lambda e: (not e.is_dir(), e.name.lower()))
                for entry in entries:
                    if nodes_count[0] >= max_nodes:
                        circuit_broken[0] = True
                        node["children"].append({"name": "[TRUNCATED]", "message": f"Safety limit of {max_nodes} reached."})
                        return node

                    e_path = Path(entry.path)
                    rel_posix = str(e_path.relative_to(root)).replace("\\", "/")

                    if _is_hidden(e_path) and entry.name not in GIT_DIRS:
                        continue
                    if _matches_gitignore(gi_spec, rel_posix, is_dir=entry.is_dir()):
                        if not (entry.is_dir() and collapse_heavy_dirs):
                            continue

                    if entry.is_dir():
                        nodes_count[0] += 1
                        is_heavy = (ignore_mode == "smart" and entry.name in HEAVY_BUILD_DIRS) or (entry.name in GIT_DIRS)
                        is_gi_ignored = _matches_gitignore(gi_spec, rel_posix, is_dir=True)
                        if collapse_heavy_dirs and (is_heavy or is_gi_ignored):
                            c_items, c_bytes = _get_collapsed_summary(e_path)
                            node["children"].append({
                                "name": entry.name,
                                "path": str(e_path),
                                "type": "directory",
                                "collapsed": True,
                                "estimated_items": c_items,
                                "estimated_size": _format_size(c_bytes),
                            })
                        else:
                            node["children"].append(_walk_json(e_path, depth + 1))
                    elif include_files and not only_dirs:
                        nodes_count[0] += 1
                        st = entry.stat()
                        node["children"].append({
                            "name": entry.name,
                            "path": str(e_path),
                            "type": "file",
                            "size_bytes": st.st_size,
                            "size_formatted": _format_size(st.st_size),
                        })
            except Exception:
                pass
            return node

        return _walk_json(root, 1)


# ==========================================
# 3. ADVANCED FILE SEARCH (FIND)
# ==========================================

@mcp.tool()
def find_files(
    search_path: str,
    pattern: Optional[str] = None,
    extensions: Optional[List[str]] = None,
    item_type: Literal["file", "directory", "any"] = "file",
    min_size_bytes: Optional[int] = None,
    max_size_bytes: Optional[int] = None,
    modified_after: Optional[str] = None,
    modified_before: Optional[str] = None,
    ignore_mode: Literal["smart", "git_only", "none"] = "smart",
    respect_gitignore: bool = True,
    max_depth: Optional[int] = None,
    max_results: int = 50,
) -> Dict[str, Any]:
    """
    Advanced file search across directories with filters for name patterns, extensions, sizes, and timestamps.
    Honors .gitignore and build caches dynamically without rigid lockouts.
    
    Args:
        search_path: Root folder to search within.
        pattern: Glob pattern for matching names (e.g. "*config*", "data_*.csv", "test*").
        extensions: List of file extensions to include (without leading dot, e.g. ["py", "json"]).
        item_type: 'file', 'directory', or 'any' (default 'file').
        min_size_bytes: Minimum file size in bytes.
        max_size_bytes: Maximum file size in bytes.
        modified_after: ISO date or relative duration like '24h', '7d', '30m'.
        modified_before: ISO date or relative duration.
        ignore_mode: 'smart' (skips build/cache dirs), 'git_only' (skips .git), or 'none'.
        respect_gitignore: Honor .gitignore rules if present.
        max_depth: Optional maximum search depth.
        max_results: Limit results count (default 50, max 300).
    """
    root = Path(search_path).resolve()
    if not root.exists():
        return {"error": f"Path not found: {root}"}
    if not root.is_dir():
        return {"error": f"Path is not a directory: {root}"}

    max_results = min(max(1, max_results), 300)
    gi_spec = _load_gitignore_spec(root) if respect_gitignore and ignore_mode == "smart" else None

    ext_set = {f".{ext.lower().lstrip('.')}" for ext in extensions} if extensions else None
    dt_after = _parse_relative_time(modified_after) if modified_after else None
    dt_before = _parse_relative_time(modified_before) if modified_before else None

    matches = []
    total_scanned = 0
    root_depth = len(root.parts)

    for dirpath, dirnames, filenames in os.walk(root):
        current_p = Path(dirpath)
        current_depth = len(current_p.parts) - root_depth

        if max_depth is not None and current_depth >= max_depth:
            dirnames[:] = []

        # Ignore pruning
        if ignore_mode == "smart":
            dirnames[:] = [
                d for d in dirnames
                if d not in HEAVY_BUILD_DIRS
                and d not in GIT_DIRS
                and not _is_hidden(current_p / d)
                and not _matches_gitignore(gi_spec, str((current_p / d).relative_to(root)).replace("\\", "/"), is_dir=True)
            ]
        elif ignore_mode == "git_only":
            dirnames[:] = [d for d in dirnames if d not in GIT_DIRS]

        # Directory matches
        if item_type in ("directory", "any"):
            for d in dirnames:
                total_scanned += 1
                d_path = current_p / d
                rel_posix = str(d_path.relative_to(root)).replace("\\", "/")
                if _matches_gitignore(gi_spec, rel_posix, is_dir=True):
                    continue
                if pattern and not fnmatch.fnmatch(d, pattern):
                    continue
                try:
                    st = d_path.stat()
                    mtime = datetime.fromtimestamp(st.st_mtime, tz=timezone.utc)
                    if dt_after and mtime < dt_after:
                        continue
                    if dt_before and mtime > dt_before:
                        continue
                    matches.append({
                        "name": d,
                        "path": str(d_path),
                        "relative_path": str(d_path.relative_to(root)),
                        "type": "directory",
                        "size_bytes": 0,
                        "size_formatted": "dir",
                        "modified_at": mtime.isoformat(),
                    })
                    if len(matches) >= max_results:
                        break
                except Exception:
                    pass
            if len(matches) >= max_results:
                break

        # File matches
        if item_type in ("file", "any"):
            for f in filenames:
                total_scanned += 1
                f_path = current_p / f
                rel_posix = str(f_path.relative_to(root)).replace("\\", "/")

                if _is_hidden(f_path):
                    continue
                if _matches_gitignore(gi_spec, rel_posix, is_dir=False):
                    continue
                if pattern and not fnmatch.fnmatch(f, pattern):
                    continue
                if ext_set and f_path.suffix.lower() not in ext_set:
                    continue

                try:
                    st = f_path.stat()
                    size = st.st_size
                    if min_size_bytes is not None and size < min_size_bytes:
                        continue
                    if max_size_bytes is not None and size > max_size_bytes:
                        continue

                    mtime = datetime.fromtimestamp(st.st_mtime, tz=timezone.utc)
                    if dt_after and mtime < dt_after:
                        continue
                    if dt_before and mtime > dt_before:
                        continue

                    matches.append({
                        "name": f,
                        "path": str(f_path),
                        "relative_path": str(f_path.relative_to(root)),
                        "type": "file",
                        "extension": f_path.suffix.lower(),
                        "size_bytes": size,
                        "size_formatted": _format_size(size),
                        "modified_at": mtime.isoformat(),
                    })
                    if len(matches) >= max_results:
                        break
                except Exception:
                    continue

            if len(matches) >= max_results:
                break

    return {
        "search_path": str(root),
        "total_scanned": total_scanned,
        "match_count": len(matches),
        "limit_reached": len(matches) >= max_results,
        "matches": matches,
    }


# ==========================================
# 4. LIGHTNING-FAST FUZZY FILE SEARCH
# ==========================================

@mcp.tool()
def fuzzy_find(
    query: str,
    search_path: str,
    extensions: Optional[List[str]] = None,
    score_cutoff: float = 50.0,
    limit: int = 25,
    ignore_mode: Literal["smart", "git_only", "none"] = "smart",
    respect_gitignore: bool = True,
) -> Dict[str, Any]:
    """
    Rapid, typo-tolerant fuzzy file search using RapidFuzz.
    Find files by approximate name or abbreviation (e.g., 'usrctrl' -> 'user_controller.py', 'authsrv' -> 'auth_service.ts').
    
    Args:
        query: Approximate or partial file name to find.
        search_path: Root folder to search.
        extensions: Optional extension filter (e.g. ['py', 'ts']).
        score_cutoff: Minimum similarity score from 0 to 100 (default 50.0).
        limit: Max number of top matches to return (default 25).
        ignore_mode: 'smart', 'git_only', or 'none'.
        respect_gitignore: Honor .gitignore if present.
    """
    root = Path(search_path).resolve()
    if not root.exists() or not root.is_dir():
        return {"error": f"Invalid directory: {root}"}

    gi_spec = _load_gitignore_spec(root) if respect_gitignore and ignore_mode == "smart" else None
    ext_set = {f".{ext.lower().lstrip('.')}" for ext in extensions} if extensions else None

    # Collect candidate file paths
    file_map = {}
    for dirpath, dirnames, filenames in os.walk(root):
        current_p = Path(dirpath)
        if ignore_mode == "smart":
            dirnames[:] = [
                d for d in dirnames
                if d not in HEAVY_BUILD_DIRS
                and d not in GIT_DIRS
                and not _is_hidden(current_p / d)
                and not _matches_gitignore(gi_spec, str((current_p / d).relative_to(root)).replace("\\", "/"), is_dir=True)
            ]
        elif ignore_mode == "git_only":
            dirnames[:] = [d for d in dirnames if d not in GIT_DIRS]

        for f in filenames:
            f_path = current_p / f
            if _is_hidden(f_path):
                continue
            rel_posix = str(f_path.relative_to(root)).replace("\\", "/")
            if _matches_gitignore(gi_spec, rel_posix, is_dir=False):
                continue
            if ext_set and f_path.suffix.lower() not in ext_set:
                continue

            # Key for fuzzy matching: relative path gives context (e.g. src/auth/service.py)
            file_map[rel_posix] = f_path

    if not file_map:
        return {"query": query, "matches_found": 0, "matches": []}

    # Perform RapidFuzz extraction
    candidates = list(file_map.keys())
    results = process.extract(
        query,
        candidates,
        scorer=fuzz.WRatio,
        score_cutoff=score_cutoff,
        limit=limit,
    )

    formatted_matches = []
    for match_rel_path, score, _ in results:
        full_p = file_map[match_rel_path]
        try:
            st = full_p.stat()
            formatted_matches.append({
                "name": full_p.name,
                "relative_path": match_rel_path,
                "path": str(full_p),
                "similarity_score": round(score, 1),
                "size_formatted": _format_size(st.st_size),
                "modified_at": datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).isoformat(),
            })
        except Exception:
            continue

    return {
        "query": query,
        "search_path": str(root),
        "total_files_indexed": len(file_map),
        "matches_found": len(formatted_matches),
        "matches": formatted_matches,
    }


# ==========================================
# 5. FAST GREP / CONTENT SEARCH
# ==========================================

@mcp.tool()
def grep_search(
    query: str,
    search_path: str,
    is_regex: bool = False,
    case_sensitive: bool = False,
    file_patterns: Optional[List[str]] = None,
    ignore_mode: Literal["smart", "git_only", "none"] = "smart",
    respect_gitignore: bool = True,
    context_lines: int = 1,
    max_file_size_mb: float = 5.0,
    max_matches: int = 50,
) -> Dict[str, Any]:
    """
    Search for text or regex patterns INSIDE files across a directory or within a single file.
    
    Args:
        query: Search term or regular expression pattern.
        search_path: Directory or file to search.
        is_regex: Treat query as a regex pattern (default False).
        case_sensitive: Perform case-sensitive search (default False).
        file_patterns: File globs to include, e.g. ["*.py", "*.ts", "*.json"].
        ignore_mode: 'smart', 'git_only', or 'none'.
        respect_gitignore: Honor .gitignore rules if present.
        context_lines: Number of surrounding lines to return for context (0 to 3, default 1).
        max_file_size_mb: Maximum file size to scan (default 5MB).
        max_matches: Maximum number of matching lines to return (default 50, max 200).
    """
    target = Path(search_path).resolve()
    if not target.exists():
        return {"error": f"Path not found: {target}"}

    context_lines = min(max(0, context_lines), 3)
    max_matches = min(max(1, max_matches), 200)
    max_bytes = int(max_file_size_mb * 1024 * 1024)

    flags = 0 if case_sensitive else re.IGNORECASE
    try:
        regex = re.compile(query if is_regex else re.escape(query), flags)
    except re.error as e:
        return {"error": f"Invalid regular expression: {str(e)}"}

    files_to_scan = []
    gi_spec = _load_gitignore_spec(target) if target.is_dir() and respect_gitignore and ignore_mode == "smart" else None

    if target.is_file():
        files_to_scan.append(target)
    else:
        for dirpath, dirnames, filenames in os.walk(target):
            current_p = Path(dirpath)
            if ignore_mode == "smart":
                dirnames[:] = [
                    d for d in dirnames
                    if d not in HEAVY_BUILD_DIRS
                    and d not in GIT_DIRS
                    and not _is_hidden(current_p / d)
                    and not _matches_gitignore(gi_spec, str((current_p / d).relative_to(target)).replace("\\", "/"), is_dir=True)
                ]
            elif ignore_mode == "git_only":
                dirnames[:] = [d for d in dirnames if d not in GIT_DIRS]

            for f in filenames:
                f_path = current_p / f
                if _is_hidden(f_path):
                    continue
                rel_posix = str(f_path.relative_to(target)).replace("\\", "/")
                if _matches_gitignore(gi_spec, rel_posix, is_dir=False):
                    continue
                if file_patterns and not any(fnmatch.fnmatch(f, pat) for pat in file_patterns):
                    continue
                if _is_binary_file(f_path):
                    continue
                try:
                    if f_path.stat().st_size <= max_bytes:
                        files_to_scan.append(f_path)
                except Exception:
                    pass

    matches = []
    files_with_matches = set()
    total_scanned_files = 0

    for f_path in files_to_scan:
        total_scanned_files += 1
        try:
            content, _ = _read_file_text_with_fallback(f_path)
            lines = content.splitlines()

            for idx, line in enumerate(lines):
                if regex.search(line):
                    files_with_matches.add(str(f_path))
                    line_no = idx + 1

                    start_ctx = max(0, idx - context_lines)
                    end_ctx = min(len(lines), idx + context_lines + 1)
                    ctx_snippet = []
                    for c_idx in range(start_ctx, end_ctx):
                        prefix = " > " if c_idx == idx else "   "
                        ctx_snippet.append(f"{c_idx + 1:4d}{prefix}{lines[c_idx]}")

                    matches.append({
                        "file": str(f_path),
                        "line_number": line_no,
                        "line_content": line.strip(),
                        "context": "\n".join(ctx_snippet),
                    })

                    if len(matches) >= max_matches:
                        break
            if len(matches) >= max_matches:
                break
        except Exception:
            continue

    return {
        "query": query,
        "is_regex": is_regex,
        "total_files_scanned": total_scanned_files,
        "matching_files_count": len(files_with_matches),
        "total_matches": len(matches),
        "limit_reached": len(matches) >= max_matches,
        "matches": matches,
    }


# ==========================================
# 6. CODE OUTLINE & STRUCTURE EXTRACTOR
# ==========================================

@mcp.tool()
def get_code_outline(
    file_path: str,
) -> Dict[str, Any]:
    """
    Extract high-level classes, functions, interfaces, methods, and exports from a code file
    without loading thousands of lines of implementation. Saves 90%+ context window tokens.
    Supports Python, JavaScript, TypeScript, and JSON files.
    
    Args:
        file_path: Path to the source file (.py, .js, .ts, .jsx, .tsx, .json).
    """
    p = Path(file_path).resolve()
    if not p.exists() or not p.is_file():
        return {"error": f"File not found: {p}"}

    ext = p.suffix.lower()
    symbols = []

    try:
        content, enc = _read_file_text_with_fallback(p)
        lines = content.splitlines()
        total_lines = len(lines)

        # 1. PYTHON AST PARSER
        if ext in (".py", ".pyw"):
            try:
                tree = ast.parse(content, filename=str(p))
                for node in tree.body:
                    if isinstance(node, ast.ClassDef):
                        bases = [getattr(b, "id", getattr(b, "attr", "Unknown")) for b in node.bases]
                        doc = ast.get_docstring(node)
                        first_doc = doc.splitlines()[0] if doc else None
                        methods = []
                        for sub in node.body:
                            if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                                m_doc = ast.get_docstring(sub)
                                args = [a.arg for a in sub.args.args]
                                methods.append({
                                    "name": sub.name,
                                    "type": "async_method" if isinstance(sub, ast.AsyncFunctionDef) else "method",
                                    "line": sub.lineno,
                                    "args": args,
                                    "docstring": m_doc.splitlines()[0] if m_doc else None,
                                })
                        symbols.append({
                            "name": node.name,
                            "type": "class",
                            "line": node.lineno,
                            "bases": bases,
                            "docstring": first_doc,
                            "methods": methods,
                        })
                    elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        doc = ast.get_docstring(node)
                        first_doc = doc.splitlines()[0] if doc else None
                        args = [a.arg for a in node.args.args]
                        symbols.append({
                            "name": node.name,
                            "type": "async_function" if isinstance(node, ast.AsyncFunctionDef) else "function",
                            "line": node.lineno,
                            "args": args,
                            "docstring": first_doc,
                        })
            except SyntaxError as se:
                return {"error": f"Python syntax error in file: {str(se)}"}

        # 2. JS / TS REGEX PARSER
        elif ext in (".js", ".ts", ".jsx", ".tsx", ".mjs"):
            pat = re.compile(
                r"^\s*(?:export\s+(?:default\s+)?)?(?:async\s+)?(class|function|interface|type|enum|const|let|var)\s+([A-Za-z0-9_$]+)",
                re.MULTILINE,
            )
            for idx, line in enumerate(lines):
                m = pat.match(line)
                if m:
                    kind, name = m.group(1), m.group(2)
                    symbols.append({
                        "name": name,
                        "type": kind,
                        "line": idx + 1,
                        "signature": line.strip()[:100],
                    })

        # 3. JSON SHAPE
        elif ext == ".json":
            try:
                data = json.loads(content)
                if isinstance(data, dict):
                    symbols = [
                        {"key": k, "type": type(v).__name__, "length": len(v) if isinstance(v, (list, dict)) else None}
                        for k, v in data.items()
                    ]
                elif isinstance(data, list):
                    symbols = [{"total_array_items": len(data), "sample_element_type": type(data[0]).__name__ if data else None}]
            except Exception as je:
                return {"error": f"Invalid JSON file: {str(je)}"}

        return {
            "file": str(p),
            "extension": ext,
            "total_lines": total_lines,
            "symbols_count": len(symbols),
            "symbols": symbols,
        }
    except Exception as e:
        return {"error": f"Failed to extract outline: {str(e)}"}


# ==========================================
# 7. TOKEN-SAFE FILE READING
# ==========================================

@mcp.tool()
def read_file(
    file_path: str,
    start_line: Optional[int] = None,
    end_line: Optional[int] = None,
    line_numbers: bool = True,
    max_lines: int = 500,
    encoding: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Read text from a file with precise line range windowing and token protection.
    Detects and protects against binary file dumps.
    
    Args:
        file_path: Path to the file.
        start_line: First line to read (1-indexed, inclusive). Default is 1.
        end_line: Last line to read (1-indexed, inclusive). Default is min(start + max_lines, total).
        line_numbers: Prepend line numbers to the output lines (default True).
        max_lines: Safety cap on number of lines returned (default 500, max 2000).
        encoding: Optional explicit character encoding. Auto-detects if None.
    """
    p = Path(file_path).resolve()
    if not p.exists():
        return {"error": f"File not found: {p}"}
    if not p.is_file():
        return {"error": f"Path is a directory, not a file: {p}"}

    if _is_binary_file(p):
        st = p.stat()
        mime, _ = mimetypes.guess_type(str(p))
        return {
            "is_binary": True,
            "path": str(p),
            "size_bytes": st.st_size,
            "size_formatted": _format_size(st.st_size),
            "mime_type": mime or "application/octet-stream",
            "message": "File appears to be binary. Content reading was skipped to protect context window.",
        }

    max_lines = min(max(1, max_lines), 2000)

    try:
        if encoding:
            with open(p, "r", encoding=encoding, errors="replace") as f:
                content = f.read()
            detected_enc = encoding
        else:
            content, detected_enc = _read_file_text_with_fallback(p)

        all_lines = content.splitlines()
        total_lines = len(all_lines)

        s_line = 1 if start_line is None else max(1, start_line)
        e_line = total_lines if end_line is None else min(total_lines, end_line)

        if (e_line - s_line + 1) > max_lines:
            e_line = s_line + max_lines - 1

        selected = all_lines[s_line - 1 : e_line]

        if line_numbers:
            width = len(str(e_line))
            output_lines = [f"{s_line + idx:{width}d} | {line}" for idx, line in enumerate(selected)]
        else:
            output_lines = selected

        return {
            "path": str(p),
            "total_lines": total_lines,
            "start_line": s_line,
            "end_line": e_line,
            "lines_returned": len(output_lines),
            "has_more": e_line < total_lines,
            "encoding": detected_enc,
            "content": "\n".join(output_lines),
        }
    except Exception as e:
        return {"error": f"Failed to read file: {str(e)}"}


@mcp.tool()
def read_head_tail(
    file_path: str,
    mode: Literal["head", "tail"] = "head",
    lines: int = 50,
    line_numbers: bool = True,
) -> Dict[str, Any]:
    """
    Quickly read the first N lines (head) or last N lines (tail) of a file.
    Ideal for inspection of large logs, data files, or configs.
    
    Args:
        file_path: Path to the file.
        mode: 'head' for top lines or 'tail' for bottom lines.
        lines: Number of lines to retrieve (default 50, max 500).
        line_numbers: Prepend line numbers (default True).
    """
    lines = min(max(1, lines), 500)
    p = Path(file_path).resolve()
    if not p.exists() or not p.is_file():
        return {"error": f"File not found or not a regular file: {p}"}

    try:
        content, _ = _read_file_text_with_fallback(p)
        all_lines = content.splitlines()
        total_lines = len(all_lines)

        if mode == "head":
            start_idx = 0
            end_idx = min(total_lines, lines)
        else:
            start_idx = max(0, total_lines - lines)
            end_idx = total_lines

        selected = all_lines[start_idx:end_idx]

        if line_numbers:
            width = len(str(end_idx))
            output_lines = [f"{start_idx + idx + 1:{width}d} | {line}" for idx, line in enumerate(selected)]
        else:
            output_lines = selected

        return {
            "path": str(p),
            "mode": mode,
            "total_lines": total_lines,
            "lines_returned": len(output_lines),
            "content": "\n".join(output_lines),
        }
    except Exception as e:
        return {"error": f"Failed to read file: {str(e)}"}


# ==========================================
# 8. FILE METADATA & DIAGNOSTICS
# ==========================================

@mcp.tool()
def get_file_info(
    path: str,
    include_hash: bool = False,
) -> Dict[str, Any]:
    """
    Get detailed diagnostic metadata about any file or directory.
    
    Args:
        path: File or directory path.
        include_hash: Compute SHA256 and MD5 hashes (files only, default False).
    """
    p = Path(path).resolve()
    if not p.exists():
        return {"error": f"Path not found: {p}"}

    try:
        st = p.stat()
        is_dir = p.is_dir()
        is_sym = p.is_symlink()
        is_bin = False if is_dir else _is_binary_file(p)

        line_count = None
        line_ending = None
        if not is_dir and not is_bin:
            try:
                content, _ = _read_file_text_with_fallback(p)
                line_count = len(content.splitlines())
                if "\r\n" in content:
                    line_ending = "CRLF (Windows)"
                elif "\n" in content:
                    line_ending = "LF (Unix)"
            except Exception:
                pass

        hashes = {}
        if include_hash and not is_dir and st.st_size <= 100 * 1024 * 1024:
            try:
                with open(p, "rb") as f:
                    data = f.read()
                    hashes["md5"] = hashlib.md5(data).hexdigest()
                    hashes["sha256"] = hashlib.sha256(data).hexdigest()
            except Exception:
                pass

        return {
            "path": str(p),
            "name": p.name,
            "type": "directory" if is_dir else "file",
            "is_dir": is_dir,
            "is_symlink": is_sym,
            "is_hidden": _is_hidden(p),
            "is_binary": is_bin,
            "extension": p.suffix.lower() if not is_dir else "",
            "size_bytes": st.st_size if not is_dir else None,
            "size_formatted": _format_size(st.st_size) if not is_dir else None,
            "created_at": datetime.fromtimestamp(st.st_ctime, tz=timezone.utc).isoformat(),
            "modified_at": datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).isoformat(),
            "line_count": line_count,
            "line_ending": line_ending,
            "hashes": hashes if include_hash else None,
        }
    except Exception as e:
        return {"error": f"Failed to retrieve file info: {str(e)}"}


# ==========================================
# 9. WORKSPACE DIAGNOSTIC SUMMARY
# ==========================================

@mcp.tool()
def workspace_summary(
    path: str,
    top_n: int = 5,
    ignore_mode: Literal["smart", "git_only", "none"] = "smart",
    respect_gitignore: bool = True,
) -> Dict[str, Any]:
    """
    Instant comprehensive overview of a project/workspace folder:
    file count breakdown by extension, total size, recent files, largest files, and Git status.
    
    Args:
        path: Path to the workspace root directory.
        top_n: Number of largest / recent files to highlight (default 5).
        ignore_mode: 'smart', 'git_only', or 'none'.
        respect_gitignore: Honor .gitignore if present.
    """
    root = Path(path).resolve()
    if not root.exists() or not root.is_dir():
        return {"error": f"Invalid workspace directory: {root}"}

    gi_spec = _load_gitignore_spec(root) if respect_gitignore and ignore_mode == "smart" else None

    ext_counts: Dict[str, int] = {}
    ext_sizes: Dict[str, int] = {}
    total_files = 0
    total_dirs = 0
    total_bytes = 0

    all_files_info = []

    for dirpath, dirnames, filenames in os.walk(root):
        current_p = Path(dirpath)
        if ignore_mode == "smart":
            dirnames[:] = [
                d for d in dirnames
                if d not in HEAVY_BUILD_DIRS
                and d not in GIT_DIRS
                and not _is_hidden(current_p / d)
                and not _matches_gitignore(gi_spec, str((current_p / d).relative_to(root)).replace("\\", "/"), is_dir=True)
            ]
        elif ignore_mode == "git_only":
            dirnames[:] = [d for d in dirnames if d not in GIT_DIRS]

        total_dirs += len(dirnames)

        for f in filenames:
            f_path = current_p / f
            if _is_hidden(f_path):
                continue
            rel_posix = str(f_path.relative_to(root)).replace("\\", "/")
            if _matches_gitignore(gi_spec, rel_posix, is_dir=False):
                continue

            try:
                st = f_path.stat()
                sz = st.st_size
                mtime = st.st_mtime
                ext = f_path.suffix.lower() or "[no extension]"

                total_files += 1
                total_bytes += sz
                ext_counts[ext] = ext_counts.get(ext, 0) + 1
                ext_sizes[ext] = ext_sizes.get(ext, 0) + sz

                all_files_info.append({
                    "name": f,
                    "relative_path": rel_posix,
                    "size_bytes": sz,
                    "size_formatted": _format_size(sz),
                    "modified_at": datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat(),
                    "mtime_ts": mtime,
                })
            except Exception:
                continue

    largest_raw = sorted(all_files_info, key=lambda x: x["size_bytes"], reverse=True)[:top_n]
    largest_files = [{k: v for k, v in item.items() if k != "mtime_ts"} for item in largest_raw]

    recent_raw = sorted(all_files_info, key=lambda x: x["mtime_ts"], reverse=True)[:top_n]
    recent_files = [{k: v for k, v in item.items() if k != "mtime_ts"} for item in recent_raw]

    top_extensions = [
        {"extension": k, "count": ext_counts[k], "total_size": _format_size(ext_sizes[k])}
        for k in sorted(ext_counts.keys(), key=lambda k: ext_counts[k], reverse=True)[:10]
    ]

    git_branch = None
    git_status = None
    git_dir = root / ".git"
    if git_dir.exists():
        try:
            res_b = subprocess.run(["git", "branch", "--show-current"], cwd=str(root), capture_output=True, text=True, timeout=3)
            if res_b.returncode == 0:
                git_branch = res_b.stdout.strip()
            res_s = subprocess.run(["git", "status", "--porcelain"], cwd=str(root), capture_output=True, text=True, timeout=3)
            if res_s.returncode == 0:
                chg = len([l for l in res_s.stdout.splitlines() if l.strip()])
                git_status = f"{chg} modified/untracked files" if chg else "clean working tree"
        except Exception:
            pass

    return {
        "workspace_root": str(root),
        "total_files": total_files,
        "total_directories": total_dirs,
        "total_size_bytes": total_bytes,
        "total_size_formatted": _format_size(total_bytes),
        "git_branch": git_branch,
        "git_status": git_status,
        "top_file_types": top_extensions,
        "largest_files": largest_files,
        "recently_modified_files": recent_files,
    }


# ==========================================
# 10. EXPORT COMPLETE INVENTORY TO FILE
# ==========================================

@mcp.tool()
def export_tree_to_file(
    path: str,
    output_file_path: Optional[str] = None,
    max_depth: int = 8,
    include_files: bool = True,
    format: Literal["markdown", "json"] = "markdown",
) -> Dict[str, Any]:
    """
    Export a complete un-truncated directory map or file inventory directly to a file on disk.
    This avoids consuming chat context window tokens while creating persistent workspace documentation.
    
    Args:
        path: Root directory to map.
        output_file_path: Target path to save the map (default is <path>/workspace_map.md or .json).
        max_depth: Maximum depth to export (default 8).
        include_files: Whether to include files (default True).
        format: 'markdown' or 'json'.
    """
    root = Path(path).resolve()
    if not root.exists() or not root.is_dir():
        return {"error": f"Invalid directory: {root}"}

    if output_file_path:
        out_p = Path(output_file_path).resolve()
    else:
        ext = "json" if format == "json" else "md"
        out_p = root / f"workspace_map.{ext}"

    try:
        out_p.parent.mkdir(parents=True, exist_ok=True)
        if format == "json":
            tree_data = get_directory_tree(
                path=str(root),
                max_depth=max_depth,
                include_files=include_files,
                max_nodes=100000,
                format="json",
            )
            with open(out_p, "w", encoding="utf-8") as f:
                json.dump(tree_data, f, indent=2)
        else:
            tree_text = get_directory_tree(
                path=str(root),
                max_depth=max_depth,
                include_files=include_files,
                max_nodes=100000,
                format="tree",
                tree_style="ascii",
            )
            header = f"# Workspace Map for {root.name}\nGenerated: {datetime.now(timezone.utc).isoformat()}\n\n```text\n"
            footer = "\n```\n"
            with open(out_p, "w", encoding="utf-8") as f:
                f.write(header + str(tree_text) + footer)

        st = out_p.stat()
        return {
            "success": True,
            "export_path": str(out_p),
            "size_formatted": _format_size(st.st_size),
            "format": format,
            "message": f"Full workspace map saved successfully to {out_p.name}",
        }
    except Exception as e:
        return {"error": f"Failed to export tree to file: {str(e)}"}


if __name__ == "__main__":
    mcp.run()
