"""
Interactive PTY / Pseudo-Terminal Session Manager for mcp-win-stdio-ssh.
Maintains long-lived interactive shell sessions for REPLs, prompts, and CLI wizards.
"""

import re
import threading
import time
from typing import Any, Dict, List, Optional

import paramiko
from mcp_win_stdio.ssh.connection import get_cached_or_connect, resolve_host_info

_PTY_SESSIONS: Dict[str, Dict[str, Any]] = {}
_PTY_LOCK = threading.RLock()

# ANSI escape sequence filter
ANSI_ESCAPE_RE = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")


def strip_ansi(text: str) -> str:
    """Remove terminal ANSI escape codes for clean AI readable output."""
    return ANSI_ESCAPE_RE.sub("", text)


def start_pty_session(
    session_name: str,
    host: Optional[str] = None,
    term: str = "xterm-256color",
    width: int = 80,
    height: int = 24,
) -> Dict[str, Any]:
    """Start an interactive pseudo-terminal shell session."""
    host_info = resolve_host_info(host)
    client = get_cached_or_connect(host_info["name"])

    with _PTY_LOCK:
        if session_name in _PTY_SESSIONS:
            chan = _PTY_SESSIONS[session_name]["channel"]
            if not chan.closed:
                return {
                    "success": True,
                    "message": f"PTY session '{session_name}' is already active.",
                    "sessionName": session_name,
                    "host": host_info["name"],
                }

        channel = client.invoke_shell(term=term, width=width, height=height)
        channel.setblocking(False)

        # Allow initial prompt to render
        time.sleep(0.5)
        initial_buf = []
        while channel.recv_ready():
            try:
                data = channel.recv(4096)
                if data:
                    initial_buf.append(data.decode("utf-8", errors="replace"))
            except Exception:
                break

        _PTY_SESSIONS[session_name] = {
            "name": session_name,
            "host": host_info["name"],
            "channel": channel,
            "createdAt": time.strftime("%Y-%m-%d %H:%M:%S"),
            "buffer": initial_buf,
        }

        return {
            "success": True,
            "message": f"Interactive PTY session '{session_name}' started on '{host_info['name']}'.",
            "sessionName": session_name,
            "host": host_info["name"],
            "initialOutput": strip_ansi("".join(initial_buf)).strip(),
        }


def send_to_pty(
    session_name: str,
    input_text: str,
    wait_ms: int = 500,
) -> Dict[str, Any]:
    """Send text/commands into an active PTY session and collect immediate output."""
    with _PTY_LOCK:
        if session_name not in _PTY_SESSIONS:
            return {
                "error": True,
                "message": f"PTY session '{session_name}' not found. Active sessions: {list(_PTY_SESSIONS.keys())}",
            }

        sess = _PTY_SESSIONS[session_name]
        channel: paramiko.Channel = sess["channel"]

        if channel.closed:
            return {
                "error": True,
                "message": f"PTY session '{session_name}' has closed.",
            }

        # Ensure newline if not present
        to_send = input_text if input_text.endswith("\n") or input_text.endswith("\r") else input_text + "\n"
        channel.sendall(to_send.encode("utf-8"))

        time.sleep(max(wait_ms, 100) / 1000.0)

        chunks = []
        while channel.recv_ready():
            try:
                data = channel.recv(4096)
                if not data:
                    break
                decoded = data.decode("utf-8", errors="replace")
                chunks.append(decoded)
                sess["buffer"].append(decoded)
            except Exception:
                break

        out_str = "".join(chunks)
        clean_out = strip_ansi(out_str)

        return {
            "success": True,
            "sessionName": session_name,
            "output": clean_out,
            "rawOutput": out_str if len(out_str) < 2000 else out_str[:2000] + "... [truncated]",
            "isClosed": channel.closed,
        }


def read_pty_buffer(session_name: str, max_chars: int = 4000) -> Dict[str, Any]:
    """Read existing buffered output and any pending data from PTY session."""
    with _PTY_LOCK:
        if session_name not in _PTY_SESSIONS:
            return {
                "error": True,
                "message": f"PTY session '{session_name}' not found. Active sessions: {list(_PTY_SESSIONS.keys())}",
            }

        sess = _PTY_SESSIONS[session_name]
        channel: paramiko.Channel = sess["channel"]

        # Read any new data
        while not channel.closed and channel.recv_ready():
            try:
                data = channel.recv(4096)
                if data:
                    sess["buffer"].append(data.decode("utf-8", errors="replace"))
            except Exception:
                break

        full_buf = "".join(sess["buffer"])
        clean_buf = strip_ansi(full_buf)

        if len(clean_buf) > max_chars:
            clean_buf = clean_buf[-max_chars:]

        return {
            "success": True,
            "sessionName": session_name,
            "buffer": clean_buf,
            "isClosed": channel.closed,
        }


def list_pty_sessions() -> List[Dict[str, Any]]:
    """List all currently active PTY sessions."""
    res = []
    with _PTY_LOCK:
        for name, sess in _PTY_SESSIONS.items():
            chan = sess["channel"]
            res.append(
                {
                    "sessionName": name,
                    "host": sess["host"],
                    "createdAt": sess["createdAt"],
                    "isActive": not chan.closed,
                }
            )
    return res


def close_pty_session(session_name: str) -> Dict[str, Any]:
    """Terminate and remove a PTY session."""
    with _PTY_LOCK:
        if session_name not in _PTY_SESSIONS:
            return {
                "error": True,
                "message": f"PTY session '{session_name}' not found.",
            }

        sess = _PTY_SESSIONS.pop(session_name)
        try:
            sess["channel"].close()
        except Exception:
            pass

        return {
            "success": True,
            "message": f"PTY session '{session_name}' terminated.",
        }


def close_all_pty_sessions() -> int:
    """Close all open PTY sessions."""
    closed = 0
    with _PTY_LOCK:
        for name in list(_PTY_SESSIONS.keys()):
            sess = _PTY_SESSIONS.pop(name)
            try:
                sess["channel"].close()
                closed += 1
            except Exception:
                pass
    return closed
