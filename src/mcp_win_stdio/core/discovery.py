"""
Discovery service for built-in MCP servers and user plugins in ~/.mcp-win-stdio/plugins.
"""

import importlib
import importlib.util
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional

from mcp_win_stdio.core.config import PLUGINS_DIR, ensure_workspace_dirs

BUILTIN_SERVERS = {
    "excel": {
        "name": "excel",
        "package": "mcp-win-stdio-excel",
        "title": "Excel MCP (Windows Native + Pandas)",
        "module": "mcp_win_stdio.excel.server",
        "description": "44 tools: Pandas queries, RapidFuzz reconciliation, OpenPyXL bulk write, native Excel Tables, row/column structural mutations, cell merging, cell formatting inspection, file-to-file in-memory ETL transformations, styling, charts, data transforms, and native Excel COM automation (PDF exports, recalc, pivots, macros).",
        "tools_count": 44,
        "is_builtin": True,
        "required_pip": ["mcp-win-stdio-excel"],
        "dependencies": ["pandas", "openpyxl", "rapidfuzz"],
        "optional_dependencies": ["win32com"],
    },
    "word": {
        "name": "word",
        "package": "mcp-win-stdio-word",
        "title": "Word MCP (Advanced Layout & Typography)",
        "module": "mcp_win_stdio.word.server",
        "description": "20 tools: multi-unit margins (in, cm, mm, pt), multi-column layout, paragraph spacing/indentation, typography (fonts, sizes, colors), images, tables, document authoring (create, headings, paragraphs), template placeholders filling, find/replace, and native Word COM PDF export.",
        "tools_count": 20,
        "is_builtin": True,
        "required_pip": ["mcp-win-stdio-word"],
        "dependencies": ["docx"],
        "optional_dependencies": ["win32com"],
    },
    "explorer": {
        "name": "explorer",
        "package": "mcp-win-stdio-explorer",
        "title": "Workspace Explorer MCP (Smart Tree & Grep)",
        "module": "mcp_win_stdio.explorer.server",
        "description": "14 tools: token-safe collapsible directory trees, .gitignore resolution, in-file grep, RapidFuzz fuzzy search, and Python/TS AST outline.",
        "tools_count": 14,
        "is_builtin": True,
        "required_pip": ["mcp-win-stdio-explorer"],
        "dependencies": ["pathspec", "rapidfuzz"],
        "optional_dependencies": [],
    },
    "tsc": {
        "name": "tsc",
        "package": "mcp-win-stdio-tsc",
        "title": "TypeScript Watcher MCP (0ms Diagnostic Cache)",
        "module": "mcp_win_stdio.tsc.server",
        "description": "8 tools: background tsc compiler watchers, in-memory diagnostic cache, 0ms error checks, fix suggestions, and dynamic project switching.",
        "tools_count": 8,
        "is_builtin": True,
        "required_pip": ["mcp-win-stdio-tsc"],
        "dependencies": ["mcp"],
        "optional_dependencies": [],
    },
    "db": {
        "name": "db",
        "package": "mcp-win-stdio-db",
        "title": "Unified Database MCP (PostgreSQL & MySQL)",
        "module": "mcp_win_stdio.db.server",
        "description": "31 tools: polyglot multi-server pooling, cross-schema resolution, DDL reconstruction, PII masking, health audit (unindexed FKs, unused indexes, bloated tables), schema diff with migration SQL, Mermaid ERD diagrams, row-level data diffing, slow queries, lock blocking trees, CSV/JSON streaming export, transactional batch CSV import, DBA management (create, drop, clone, dump), and 0ms connection caching.",
        "tools_count": 31,
        "is_builtin": True,
        "required_pip": ["mcp-win-stdio-db"],
        "dependencies": ["psycopg2", "pymysql"],
        "optional_dependencies": [],
    },
    "git": {
        "name": "git",
        "package": "mcp-win-stdio-git",
        "title": "Unified Git & GitHub MCP (Local Git + gh CLI)",
        "module": "mcp_win_stdio.git.server",
        "description": "46 tools: Local Git init/remotes/restore/branching, bookmark management, commits, diffs, conflicts, and remote GitHub PR checks, releases, issues, Actions.",
        "tools_count": 46,
        "is_builtin": True,
        "required_pip": ["mcp-win-stdio-git"],
        "dependencies": ["mcp"],
        "optional_dependencies": [],
    },
    "ssh": {
        "name": "ssh",
        "package": "mcp-win-stdio-ssh",
        "title": "Unified Multi-SSH MCP (Remote Execution & SFTP)",
        "module": "mcp_win_stdio.ssh.server",
        "description": "34 tools: multi-host pooling, ~/.ssh/config auto-discovery, interactive PTY shells, background jobs, systemd/docker services, package manager listing, SFTP file management, and port forwarding tunnels.",
        "tools_count": 34,
        "is_builtin": True,
        "required_pip": ["mcp-win-stdio-ssh"],
        "dependencies": ["paramiko", "cryptography"],
        "optional_dependencies": [],
    },
    "rag": {
        "name": "rag",
        "package": "mcp-win-stdio-rag",
        "title": "RAG MCP (Playwright Crawler, Graph Tree & Hybrid Search)",
        "module": "mcp_win_stdio.rag.server",
        "description": "8 tools: automated async Playwright web crawling, NetworkX link tree graphs, multi-RAG collection management, codebase indexing, and SQLite hybrid vector + BM25 search.",
        "tools_count": 8,
        "is_builtin": True,
        "required_pip": ["mcp-win-stdio-rag"],
        "dependencies": ["playwright", "networkx", "numpy"],
        "optional_dependencies": ["sklearn"],
    },
    "excel-db": {
        "name": "excel-db",
        "package": "mcp-win-stdio-excel-db",
        "title": "Excel & DB Power Engine (Streaming, Cross-Joins & Diff Auditor)",
        "module": "mcp_win_stdio.excel_db.server",
        "description": "9 tools: zero-context DB-to-Excel streaming, bulk Excel-to-DB upserting, in-memory cross-source SQL joins, automated reconciliation diffs, multi-master datasets comparison with tolerance, master data migration planning, transactional DB sync, and custom Python template pipeline.",
        "tools_count": 9,
        "is_builtin": True,
        "required_pip": ["mcp-win-stdio-excel-db"],
        "dependencies": ["pandas", "sqlalchemy", "openpyxl"],
        "optional_dependencies": [],
    },
}


def check_server_installed(server_info: Dict[str, Any]) -> bool:
    """Check if the standalone server package and its dependencies are installed and importable."""
    if not server_info.get("is_builtin"):
        return Path(server_info.get("path", "")).exists()

    mod = server_info.get("module")
    if mod:
        try:
            if not importlib.util.find_spec(mod):
                return False
        except Exception:
            return False

    for dep in server_info.get("dependencies", []):
        try:
            if not importlib.util.find_spec(dep):
                return False
        except Exception:
            return False
    return True


def list_available_servers() -> Dict[str, Dict[str, Any]]:
    """Return dictionary of all available servers with live installation status."""
    ensure_workspace_dirs()
    servers = {}

    for name, srv in BUILTIN_SERVERS.items():
        data = dict(srv)
        data["is_installed"] = check_server_installed(data)
        servers[name] = data

    # Discover custom user plugins in ~/.mcp-win-stdio/plugins
    if PLUGINS_DIR.exists():
        for item in PLUGINS_DIR.glob("*.py"):
            if item.name.startswith("__"):
                continue
            plugin_name = item.stem
            servers[plugin_name] = {
                "name": plugin_name,
                "title": f"User Plugin: {plugin_name}",
                "path": str(item),
                "module": None,
                "description": f"Custom user plugin script loaded from {item}",
                "tools_count": "dynamic",
                "is_builtin": False,
                "is_installed": True,
                "required_pip": [],
                "dependencies": [],
                "optional_dependencies": [],
            }
    return servers


def get_server_info(name: str) -> Optional[Dict[str, Any]]:
    """Get metadata and live installation status for a specific server."""
    servers = list_available_servers()
    return servers.get(name.lower())
