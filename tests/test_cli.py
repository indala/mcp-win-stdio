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


def test_discovery():
    ensure_workspace_dirs()
    servers = list_available_servers()
    assert "excel" in servers
    assert "word" in servers
    assert "explorer" in servers
    assert "tsc" in servers

    assert servers["excel"]["tools_count"] == 20
    assert servers["word"]["tools_count"] == 10
    assert servers["explorer"]["tools_count"] == 11
    assert servers["tsc"]["tools_count"] == 6
    print("[PASS] Discovery test passed.")


def test_guides(capsys):
    print_excel_guide()
    print_word_guide()
    print_explorer_guide()
    print_tsc_guide()
    captured = capsys.readouterr()
    assert "Excel MCP" in captured.out
    assert "Word Document MCP" in captured.out
    assert "Workspace Explorer MCP" in captured.out
    assert "TypeScript Diagnostic Watcher" in captured.out
    print("[PASS] Guides test passed.")


def test_dashboard(capsys):
    print_dashboard()
    captured = capsys.readouterr()
    assert "mcp-win-stdio" in captured.out
    assert "excel" in captured.out
    assert "word" in captured.out
    assert "explorer" in captured.out
    assert "tsc" in captured.out
    print("[PASS] Dashboard test passed.")


def test_tsc_server_import():
    from mcp_win_stdio.tsc.server import mcp as tsc_mcp
    assert tsc_mcp is not None
    print("[PASS] TSC server import test passed.")


if __name__ == "__main__":
    test_discovery()
    test_tsc_server_import()
    print("ALL TESTS PASSED!")
