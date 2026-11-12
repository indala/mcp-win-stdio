"""
Unified JSONL Audit Logging for mws MCP Server.
Records thread-safe, structured JSON lines to ~/.mcp-win-stdio/logs/audit.jsonl with secret redaction.
"""

import json
import os
import re
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from mcp_win_stdio.core.config import LOGS_DIR, ensure_workspace_dirs

AUDIT_LOG_FILE = LOGS_DIR / "audit.jsonl"
_AUDIT_LOCK = threading.RLock()

# Common secret regex patterns (passwords, tokens, keys)
SECRET_PATTERNS = [
    re.compile(r"(password|passwd|pwd|secret|token|api[_-]?key|auth|bearer)\s*[:=]\s*([^\s,;'\"]+)", re.IGNORECASE),
    re.compile(r"(postgres(?:ql)?|mysql|mongodb|redis)://([^:]+):([^@]+)@", re.IGNORECASE),
    re.compile(r"Bearer\s+([A-Za-z0-9_\-\.]{8,})", re.IGNORECASE),
]


def redact_secrets(val: Any) -> Any:
    """Recursively mask sensitive values, passwords, and tokens in arguments and logs."""
    if isinstance(val, str):
        masked = val
        # 1. Redact connection URI passwords: user:pass@ -> user:******@
        masked = re.sub(
            r"((?:postgres(?:ql)?|mysql|mongodb|redis)://[^:]+:)([^@]+)(@)",
            r"\1******\3",
            masked,
            flags=re.IGNORECASE,
        )
        # 2. Redact Bearer and Basic authentication headers
        masked = re.sub(
            r"((?:Bearer|Basic)\s+)[A-Za-z0-9_\-\.\+/=]{6,}",
            r"\1******",
            masked,
            flags=re.IGNORECASE,
        )
        # 3. Redact inline command flags: --password=xyz, --password secret, -pSECRET, PASSWORD=xyz
        masked = re.sub(
            r"(--(?:password|passwd|token|api-key|secret)[=\s]+)(?:\"[^\"]*\"|'[^']*'|[^\s,;]+)",
            r"\1******",
            masked,
            flags=re.IGNORECASE,
        )
        masked = re.sub(
            r"(?<![a-zA-Z0-9_-])(-p)(?:\"[^\"]*\"|'[^']*'|[^\s,;]+)",
            r"\1******",
            masked,
        )
        masked = re.sub(
            r"((?:PASSWORD|PASSWD|TOKEN|SECRET|API_KEY|AUTH_TOKEN)=)(?:\"[^\"]*\"|'[^']*'|[^\s,;]+)",
            r"\1******",
            masked,
            flags=re.IGNORECASE,
        )
        # 4. Redact query parameters: ?token=xyz, &password=xyz, &api_key=xyz
        masked = re.sub(
            r"([?&](?:token|password|passwd|secret|api[_-]?key)=)(?:\"[^\"]*\"|'[^']*'|[^&\s,;]+)",
            r"\1******",
            masked,
            flags=re.IGNORECASE,
        )
        return masked
    elif isinstance(val, dict):
        out = {}
        for k, v in val.items():
            k_lower = str(k).lower()
            if any(s in k_lower for s in ("password", "passwd", "pwd", "secret", "token", "authkey", "private_key", "api_key", "apikey")):
                out[k] = "******"
            else:
                out[k] = redact_secrets(v)
        return out
    elif isinstance(val, list):
        return [redact_secrets(item) for item in val]
    return val


def log_audit_event(
    event_type: str,
    server: str,
    tool: str,
    duration_ms: float,
    status: str,
    arguments: Optional[Dict[str, Any]] = None,
    session_id: Optional[str] = None,
    output_bytes: Optional[int] = None,
    error: Optional[str] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Append a structured JSONL audit record.
    Thread-safe, open-append-close with secret redaction and argument key filtering.
    """
    ensure_workspace_dirs()
    LOGS_DIR.mkdir(parents=True, exist_ok=True)

    # Summarize argument keys to avoid bloating audit log with massive payloads
    arg_summary: Dict[str, Any] = {}
    if isinstance(arguments, dict):
        redacted_args = redact_secrets(arguments)
        for k, v in redacted_args.items():
            if isinstance(v, (str, bytes)):
                arg_summary[k] = f"<{len(v)} chars>" if len(v) > 60 else str(v)
            elif isinstance(v, (list, dict)):
                arg_summary[k] = f"<{type(v).__name__} len={len(v)}>"
            else:
                arg_summary[k] = v

    record = {
        "timestamp": round(time.time(), 3),
        "datetime": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
        "event_type": event_type,
        "server": str(server or "").lower().strip(),
        "tool": str(tool or "").strip(),
        "duration_ms": round(duration_ms, 2),
        "status": status,
        "session_id": session_id or "default",
        "arg_keys": list(arguments.keys()) if isinstance(arguments, dict) else [],
        "arg_summary": arg_summary,
        "output_bytes": output_bytes or 0,
    }

    if error:
        record["error"] = redact_secrets(str(error)[:300])
    if extra:
        record["extra"] = redact_secrets(extra)

    line = json.dumps(record) + "\n"

    with _AUDIT_LOCK:
        try:
            # Check rotation if file exceeds 10 MB
            if AUDIT_LOG_FILE.exists() and AUDIT_LOG_FILE.stat().st_size > 10 * 1024 * 1024:
                rotated = LOGS_DIR / f"audit_{time.strftime('%Y%m%d_%H%M%S')}.jsonl"
                try:
                    AUDIT_LOG_FILE.rename(rotated)
                except Exception:
                    pass

            # Open-append-close per call for cross-process safety on Windows
            with open(AUDIT_LOG_FILE, "a", encoding="utf-8") as f:
                f.write(line)
        except Exception:
            pass  # Logging must never crash the primary execution path
