"""
Artifact Spilling & Inspection Manager for mws MCP Gateway.
Protects LLM context windows by automatically spilling large result payloads (>32 KB)
to atomic JSON artifact files with bounded previews, path-traversal protection, and pagination.
"""

import json
import logging
import os
import re
import secrets
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from mcp_win_stdio.core.config import EXPORTS_DIR, ensure_workspace_dirs

logger = logging.getLogger("mcp_win_stdio.artifacts")

ARTIFACTS_DIR = EXPORTS_DIR / "artifacts"
_ARTIFACT_LOCK = threading.RLock()

# Strict ID validation regex: art_YYYYMMDD_<8-char-hex>
ARTIFACT_ID_PATTERN = re.compile(r"^art_\d{8}_[a-f0-9]{8,16}$")

# Default thresholds
SPILL_THRESHOLD_BYTES = 32 * 1024  # 32 KB
MAX_PREVIEW_BYTES = 4 * 1024       # 4 KB bounded preview
MAX_PREVIEW_ROWS = 5               # Top 5 records
TTL_HOURS = 24.0                   # Auto-prune files older than 24h
MAX_DIR_BYTES = 500 * 1024 * 1024  # 500 MB max directory cap
_LIST_CONTAINER_KEYS = (
    "rows",
    "data",
    "items",
    "results",
    "records",
    "resources",
    "resourceTemplates",
    "prompts",
    "contents",
)


def _ensure_artifacts_dir() -> Path:
    ensure_workspace_dirs()
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    return ARTIFACTS_DIR


def generate_artifact_id() -> str:
    """Generate a collision-resistant, date-prefixed artifact ID."""
    date_str = time.strftime("%Y%m%d")
    token = secrets.token_hex(4)
    return f"art_{date_str}_{token}"


def prune_expired_artifacts(ttl_hours: float = TTL_HOURS) -> int:
    """Prune artifact files older than TTL or prune oldest if directory cap is exceeded."""
    if not ARTIFACTS_DIR.exists():
        return 0

    now = time.time()
    cutoff = now - (ttl_hours * 3600)
    pruned = 0

    with _ARTIFACT_LOCK:
        files: List[Tuple[Path, float, int]] = []
        total_size = 0
        try:
            for p in ARTIFACTS_DIR.glob("art_*.json"):
                try:
                    stat = p.stat()
                    if stat.st_mtime < cutoff:
                        p.unlink(missing_ok=True)
                        pruned += 1
                    else:
                        files.append((p, stat.st_mtime, stat.st_size))
                        total_size += stat.st_size
                except Exception:
                    pass

            # If directory size still exceeds cap, remove oldest files first
            if total_size > MAX_DIR_BYTES:
                files.sort(key=lambda x: x[1])  # Oldest mtime first
                for p, _, sz in files:
                    try:
                        p.unlink(missing_ok=True)
                        pruned += 1
                        total_size -= sz
                        if total_size <= MAX_DIR_BYTES * 0.8:  # Prune down to 80%
                            break
                    except Exception:
                        pass
        except Exception as e:
            logger.debug("Error during artifact pruning: %s", e)

    return pruned


def write_artifact_atomically(data: Any, handle: Optional[str] = None) -> Tuple[str, Path, int]:
    """
    Atomically writes a payload to an artifact file using a tempfile + atomic rename.
    Returns (handle, artifact_path, byte_count).
    """
    artifacts_dir = _ensure_artifacts_dir()
    art_id = handle or generate_artifact_id()
    final_path = artifacts_dir / f"{art_id}.json"

    json_bytes = json.dumps(data, indent=2, ensure_ascii=False).encode("utf-8")
    byte_count = len(json_bytes)

    with _ARTIFACT_LOCK:
        # Atomic write pattern: write to NamedTemporaryFile in same folder, then replace
        with tempfile.NamedTemporaryFile("wb", dir=artifacts_dir, delete=False) as tmp:
            tmp.write(json_bytes)
            tmp_path = Path(tmp.name)

        # Atomic file replacement
        tmp_path.replace(final_path)

    return art_id, final_path, byte_count


def maybe_spill_to_artifact(
    data: Any,
    threshold_bytes: int = SPILL_THRESHOLD_BYTES,
) -> Tuple[bool, Any]:
    """
    Checks if data should be spilled to an artifact file.
    Rule 1: NEVER spill error results.
    Rule 2: Only spill if serialized JSON exceeds threshold_bytes.
    Returns (spilled: bool, result_payload).
    """
    # 1. Never spill error responses
    if isinstance(data, dict):
        if data.get("isError") or data.get("status") == "error":
            return False, data

    # Quick estimate on strings/dicts before full serialization
    estimated_size = 0
    if isinstance(data, str):
        estimated_size = len(data)
    elif isinstance(data, (dict, list)):
        # Sample size estimate
        estimated_size = len(str(data))
    else:
        return False, data

    if estimated_size < threshold_bytes:
        return False, data

    # Serialize to measure true byte length
    try:
        raw_json = json.dumps(data, ensure_ascii=False)
        byte_len = len(raw_json.encode("utf-8"))
    except Exception:
        return False, data

    if byte_len <= threshold_bytes:
        return False, data

    # Spilling triggered
    handle, final_path, total_bytes = write_artifact_atomically(data)

    # Build bounded preview (max 5 rows and max 4 KB)
    preview: Any = None
    total_items = None

    if isinstance(data, dict):
        # Look for primary list container (e.g. 'rows', 'data', 'tools', 'items')
        for key in _LIST_CONTAINER_KEYS:
            if isinstance(data.get(key), list):
                total_items = len(data[key])
                sample = data[key][:MAX_PREVIEW_ROWS]
                sample_str = json.dumps(sample)
                if len(sample_str.encode("utf-8")) > MAX_PREVIEW_BYTES:
                    # Further bound preview to 1-2 items if rows are massive text blobs
                    sample = data[key][:1]
                preview = {key: sample}
                break

        if preview is None:
            # Fallback key summary
            preview = {k: f"<{len(str(v))} chars>" if isinstance(v, (str, list, dict)) else v for k, v in list(data.items())[:8]}
    elif isinstance(data, list):
        total_items = len(data)
        sample = data[:MAX_PREVIEW_ROWS]
        sample_str = json.dumps(sample)
        if len(sample_str.encode("utf-8")) > MAX_PREVIEW_BYTES:
            sample = data[:1]
        preview = sample
    else:
        preview = str(data)[:500] + "..."

    summary_wrapper = {
        "_artifact": {
            "handle": handle,
            "status": "spilled_to_artifact",
            "size_bytes": total_bytes,
            "size_formatted": f"{round(total_bytes / 1024, 1)} KB",
            "total_items": total_items,
            "preview": preview,
            "message": (
                f"Output ({round(total_bytes / 1024, 1)} KB) was automatically spilled to disk to protect LLM context tokens. "
                f"Call read_artifact(handle='{handle}', offset=0, limit=50) to page through or query data."
            ),
        }
    }
    return True, summary_wrapper


def read_artifact_payload(
    handle: str,
    offset: int = 0,
    limit: int = 50,
    query: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Safely read, paginate, and filter an artifact file.
    Security: Validates ID format and ensures file is strictly relative to ARTIFACTS_DIR.
    """
    clean_handle = str(handle or "").strip()
    if not ARTIFACT_ID_PATTERN.match(clean_handle):
        return {
            "isError": True,
            "error": f"Invalid artifact handle '{clean_handle}'. Must match format 'art_YYYYMMDD_<token>'.",
        }

    artifacts_dir = _ensure_artifacts_dir().resolve()
    target_file = (artifacts_dir / f"{clean_handle}.json").resolve()

    # Traversal security verification
    if not target_file.is_relative_to(artifacts_dir) or not target_file.exists():
        return {
            "isError": True,
            "error": f"Artifact handle '{clean_handle}' expired, not found, or invalid. Please rerun the originating query to regenerate.",
        }

    # Update access time so recently read artifacts are not prematurely pruned
    try:
        now = time.time()
        os.utime(target_file, (now, now))
    except Exception:
        pass

    try:
        with open(target_file, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        return {
            "isError": True,
            "error": f"Failed reading artifact file: {e}",
        }

    # Bound limit to 100 to prevent infinite recursive spilling
    safe_limit = max(1, min(limit, 100))

    # Slice and paginate if list or dict with list
    rows_container = None
    if isinstance(data, list):
        rows_container = data
    elif isinstance(data, dict):
        for k in _LIST_CONTAINER_KEYS:
            if isinstance(data.get(k), list):
                rows_container = data[k]
                break

    if rows_container is not None:
        total = len(rows_container)
        # Optional basic keyword filter if query passed
        if query:
            q_clean = query.lower().strip()
            filtered = [
                row for row in rows_container
                if q_clean in json.dumps(row, ensure_ascii=False).lower()
            ]
        else:
            filtered = rows_container

        matched_total = len(filtered)
        start = max(0, offset)
        end = start + safe_limit
        paged_slice = filtered[start:end]

        return {
            "handle": clean_handle,
            "total_items": total,
            "matched_items": matched_total,
            "offset": start,
            "limit": safe_limit,
            "returned_items": len(paged_slice),
            "has_more": end < matched_total,
            "items": paged_slice,
        }

    # Return full data if not a list
    return {
        "handle": clean_handle,
        "data": data,
    }
