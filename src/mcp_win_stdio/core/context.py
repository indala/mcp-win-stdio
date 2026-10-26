"""
Session Context Manager for mcp-win-stdio (mws).
Provides in-memory, typed, session-isolated context stacking across AI agents.
Allows agents to set or push active targets (database connections, SSH hosts,
workspaces, workbooks, servers) once and have subsequent tool invocations
inherit those values automatically without argument repetition or cross-agent pollution.
"""

import threading
import time
from typing import Any, Dict, List, Optional, Tuple

SUPPORTED_CONTEXT_TYPES = {
    "server": "Active MCP server namespace (e.g. 'db', 'excel', 'ssh', 'git')",
    "db_connection": "Active database connection alias (e.g. 'postgres_prod', 'ijitest')",
    "ssh_host": "Active SSH remote host alias (e.g. 'hostinger-prod', 'staging')",
    "workspace": "Active workspace or repository directory path",
    "workbook": "Active Excel workbook file path or name",
}


class SessionContext:
    """
    Isolated, typed in-memory stack collection for a single client session.
    Thread-safe and tracks access timestamps for automated lifecycle management.
    """

    def __init__(self, session_id: str = "default") -> None:
        self.session_id = session_id
        self._lock = threading.RLock()
        self.created_at = time.time()
        self.last_accessed_at = time.time()
        self._stacks: Dict[str, List[Any]] = {
            ctype: [] for ctype in SUPPORTED_CONTEXT_TYPES
        }

    def _touch(self) -> None:
        self.last_accessed_at = time.time()

    def set(self, context_type: str, value: Any) -> Any:
        ctype = context_type.lower().strip()
        with self._lock:
            self._touch()
            if ctype not in self._stacks:
                self._stacks[ctype] = []
            if not self._stacks[ctype]:
                self._stacks[ctype].append(value)
            else:
                self._stacks[ctype][-1] = value
            return value

    def push(self, context_type: str, value: Any) -> Any:
        ctype = context_type.lower().strip()
        with self._lock:
            self._touch()
            if ctype not in self._stacks:
                self._stacks[ctype] = []
            self._stacks[ctype].append(value)
            return value

    def pop(self, context_type: str) -> Optional[Any]:
        ctype = context_type.lower().strip()
        with self._lock:
            self._touch()
            if ctype in self._stacks and self._stacks[ctype]:
                return self._stacks[ctype].pop()
            return None

    def get(self, context_type: str, default: Optional[Any] = None) -> Optional[Any]:
        ctype = context_type.lower().strip()
        with self._lock:
            self._touch()
            stack = self._stacks.get(ctype)
            if stack and len(stack) > 0:
                return stack[-1]
            return default

    def clear(self, context_type: Optional[str] = None) -> None:
        with self._lock:
            self._touch()
            if context_type:
                ctype = context_type.lower().strip()
                if ctype in self._stacks:
                    self._stacks[ctype].clear()
            else:
                for s in self._stacks.values():
                    s.clear()

    def snapshot(self) -> Dict[str, Dict[str, Any]]:
        with self._lock:
            self._touch()
            result = {}
            for ctype, desc in SUPPORTED_CONTEXT_TYPES.items():
                stack = self._stacks.get(ctype, [])
                result[ctype] = {
                    "active": stack[-1] if stack else None,
                    "depth": len(stack),
                    "description": desc,
                }
            return result

    def resolve_arguments(
        self,
        server: Optional[str],
        tool_name: str,
        arguments: Optional[Dict[str, Any]],
        expected_params: Optional[List[str]] = None,
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        with self._lock:
            self._touch()
            args = dict(arguments or {})
            injected: Dict[str, Any] = {}

            # 1. Database connection injection
            if "connection" not in args and "conn" not in args:
                is_db_tool = (server in ("db", "excel-db")) or (
                    expected_params and any(p in ("connection", "conn") for p in expected_params)
                )
                if is_db_tool:
                    active_db = self.get("db_connection")
                    if active_db:
                        args["connection"] = active_db
                        injected["connection"] = active_db

            # 2. SSH host injection
            if "host" not in args and "ssh_host" not in args:
                is_ssh_tool = (server == "ssh") or (
                    expected_params and any(p in ("host", "ssh_host") for p in expected_params)
                )
                if is_ssh_tool:
                    active_host = self.get("ssh_host")
                    if active_host:
                        args["host"] = active_host
                        injected["host"] = active_host

            # 3. Workspace injection
            if not any(k in args for k in ("workspace", "workspace_root", "directory", "project_root")):
                if expected_params and any(p in ("workspace", "workspace_root", "directory", "project_root") for p in expected_params):
                    active_ws = self.get("workspace")
                    if active_ws:
                        target_param = next(
                            (p for p in expected_params if p in ("workspace", "workspace_root", "directory", "project_root")),
                            "workspace",
                        )
                        args[target_param] = active_ws
                        injected[target_param] = active_ws

            # 4. Excel workbook injection
            if not any(k in args for k in ("workbook", "workbook_path", "file_path")):
                if server in ("excel", "excel-db") or (
                    expected_params and any(p in ("workbook", "workbook_path", "file_path") for p in expected_params)
                ):
                    active_wb = self.get("workbook")
                    if active_wb:
                        target_param = "file_path"
                        if expected_params:
                            for candidate in ("file_path", "workbook_path", "workbook"):
                                if candidate in expected_params:
                                    target_param = candidate
                                    break
                        args[target_param] = active_wb
                        injected[target_param] = active_wb

            return args, injected


class ContextRegistry:
    """
    Registry managing isolated SessionContexts for different clients / session IDs.
    Guarantees thread-safe access, LRU lifecycle pruning, and strict session isolation.
    """

    def __init__(self, max_sessions: int = 100, max_idle_seconds: float = 7200.0) -> None:
        self._lock = threading.RLock()
        self._sessions: Dict[str, SessionContext] = {}
        self.max_sessions = max_sessions
        self.max_idle_seconds = max_idle_seconds

    def _prune_if_needed(self) -> None:
        now = time.time()
        # 1. Prune expired sessions older than max_idle_seconds (skip 'default')
        expired = [
            sid
            for sid, s in self._sessions.items()
            if sid != "default" and (now - s.last_accessed_at) > self.max_idle_seconds
        ]
        for sid in expired:
            del self._sessions[sid]

        # 2. If still exceeding max_sessions, prune oldest idle sessions
        if len(self._sessions) > self.max_sessions:
            candidates = sorted(
                [(sid, s.last_accessed_at) for sid, s in self._sessions.items() if sid != "default"],
                key=lambda x: x[1],
            )
            to_remove = len(self._sessions) - self.max_sessions
            for sid, _ in candidates[:to_remove]:
                del self._sessions[sid]

    def get_session(self, session_id: Optional[str] = None) -> SessionContext:
        sid = (session_id or "default").strip()
        with self._lock:
            self._prune_if_needed()
            if sid not in self._sessions:
                self._sessions[sid] = SessionContext(session_id=sid)
            return self._sessions[sid]

    def list_sessions(self) -> List[Dict[str, Any]]:
        now = time.time()
        with self._lock:
            results = []
            for sid, s in self._sessions.items():
                results.append({
                    "session_id": sid,
                    "idle_seconds": round(now - s.last_accessed_at, 1),
                    "created_seconds_ago": round(now - s.created_at, 1),
                })
            return results

    def set(self, context_type: str, value: Any, session_id: Optional[str] = None) -> Any:
        return self.get_session(session_id).set(context_type, value)

    def push(self, context_type: str, value: Any, session_id: Optional[str] = None) -> Any:
        return self.get_session(session_id).push(context_type, value)

    def pop(self, context_type: str, session_id: Optional[str] = None) -> Optional[Any]:
        return self.get_session(session_id).pop(context_type)

    def get(self, context_type: str, default: Optional[Any] = None, session_id: Optional[str] = None) -> Optional[Any]:
        return self.get_session(session_id).get(context_type, default)

    def clear(self, context_type: Optional[str] = None, session_id: Optional[str] = None) -> None:
        if session_id:
            sid = session_id.strip()
            with self._lock:
                if sid in self._sessions:
                    self._sessions[sid].clear(context_type)
        else:
            with self._lock:
                for session in list(self._sessions.values()):
                    session.clear(context_type)

    def snapshot(self, session_id: Optional[str] = None) -> Dict[str, Dict[str, Any]]:
        return self.get_session(session_id).snapshot()

    def resolve_arguments(
        self,
        server: Optional[str],
        tool_name: str,
        arguments: Optional[Dict[str, Any]],
        expected_params: Optional[List[str]] = None,
        session_id: Optional[str] = None,
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        return self.get_session(session_id).resolve_arguments(
            server=server,
            tool_name=tool_name,
            arguments=arguments,
            expected_params=expected_params,
        )


# Global singleton context manager for the gateway
GLOBAL_CONTEXT = ContextRegistry()
ContextManager = ContextRegistry
