"""
Tests for mcp-win-stdio CLI, discovery, guides, and servers.
"""

import sys
from mcp_win_stdio.core.config import ensure_workspace_dirs
from mcp_win_stdio.core.discovery import get_server_info, list_available_servers
from mcp_win_stdio.cli import print_dashboard
from mcp_win_stdio.guides.excel_guide import print_excel_guide
from mcp_win_stdio.guides.word_guide import print_word_guide
from mcp_win_stdio.guides.explorer_guide import print_explorer_guide
from mcp_win_stdio.guides.tsc_guide import print_tsc_guide
from mcp_win_stdio.guides.db_guide import print_db_guide


def test_discovery():
    ensure_workspace_dirs()
    servers = list_available_servers()
    assert "excel" in servers
    assert "word" in servers
    assert "explorer" in servers
    assert "tsc" in servers
    assert "db" in servers

    assert servers["excel"]["tools_count"] == 20
    assert servers["word"]["tools_count"] == 10
    assert servers["explorer"]["tools_count"] == 11
    assert servers["tsc"]["tools_count"] == 6
    assert servers["db"]["tools_count"] == 20
    print("[PASS] Discovery test passed.")


def test_guides():
    import io
    from contextlib import redirect_stdout
    f = io.StringIO()
    with redirect_stdout(f):
        print_excel_guide()
        print_word_guide()
        print_explorer_guide()
        print_tsc_guide()
        print_db_guide()
    out = f.getvalue()
    assert "Excel MCP" in out
    assert "Word Document MCP" in out
    assert "Workspace Explorer MCP" in out
    assert "TypeScript Diagnostic Watcher" in out
    assert "Database MCP" in out
    print("[PASS] Guides test passed.")


def test_dashboard():
    import io
    from contextlib import redirect_stdout
    f = io.StringIO()
    with redirect_stdout(f):
        print_dashboard()
    out = f.getvalue()
    assert "mcp-win-stdio" in out
    assert "excel" in out
    assert "word" in out
    assert "explorer" in out
    assert "tsc" in out
    assert "db" in out
    print("[PASS] Dashboard test passed.")


def test_all_servers_import():
    from mcp_win_stdio.excel.server import mcp as excel_mcp
    from mcp_win_stdio.word.server import mcp as word_mcp
    from mcp_win_stdio.explorer.server import mcp as explorer_mcp
    from mcp_win_stdio.tsc.server import mcp as tsc_mcp
    from mcp_win_stdio.db.server import mcp as db_mcp

    assert excel_mcp is not None
    assert word_mcp is not None
    assert explorer_mcp is not None
    assert tsc_mcp is not None
    assert db_mcp is not None
    print("[PASS] All 5 servers import successfully.")


if __name__ == "__main__":
    test_discovery()
    test_guides()
    test_dashboard()
    test_all_servers_import()
    print("ALL TESTS PASSED!")

