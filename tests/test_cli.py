"""
Tests for mcp-win-stdio CLI, discovery, guides, and servers across modular sub-packages.
"""

import io
import os
import sys
from contextlib import redirect_stdout
from pathlib import Path

# Add all sub-packages and root src to sys.path
for p in Path("packages").glob("*/src"):
    sys.path.insert(0, str(p.resolve()))
sys.path.insert(0, os.path.abspath("src"))

from mcp_win_stdio.core.config import ensure_workspace_dirs
from mcp_win_stdio.core.discovery import get_server_info, list_available_servers
from mcp_win_stdio.cli import print_dashboard, cmd_guide
from mcp_win_stdio.excel.guide import print_excel_guide
from mcp_win_stdio.word.guide import print_word_guide
from mcp_win_stdio.explorer.guide import print_explorer_guide
from mcp_win_stdio.tsc.guide import print_tsc_guide
from mcp_win_stdio.db.guide import print_db_guide
from mcp_win_stdio.git.guide import print_git_guide
from mcp_win_stdio.ssh.guide import print_ssh_guide


def test_discovery():
    ensure_workspace_dirs()
    servers = list_available_servers()
    assert "excel" in servers
    assert "word" in servers
    assert "explorer" in servers
    assert "tsc" in servers
    assert "db" in servers
    assert "git" in servers
    assert "ssh" in servers

    assert servers["excel"]["tools_count"] == 20
    assert servers["word"]["tools_count"] == 10
    assert servers["explorer"]["tools_count"] == 11
    assert servers["tsc"]["tools_count"] == 6
    assert servers["db"]["tools_count"] == 23
    assert servers["git"]["tools_count"] == 33
    assert servers["ssh"]["tools_count"] == 27
    print("[PASS] Discovery test passed for all 7 servers.")


def test_guides():
    f = io.StringIO()
    with redirect_stdout(f):
        print_excel_guide()
        print_word_guide()
        print_explorer_guide()
        print_tsc_guide()
        print_db_guide()
        print_git_guide()
        print_ssh_guide()
    out = f.getvalue()
    assert "Excel MCP" in out
    assert "Word Document MCP" in out
    assert "Workspace Explorer MCP" in out
    assert "TypeScript Diagnostic Watcher" in out
    assert "Database MCP" in out
    assert "Git & GitHub MCP" in out
    assert "Multi-SSH" in out
    print("[PASS] Sub-package guides test passed for all 7 servers.")


def test_dashboard():
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
    assert "git" in out
    assert "ssh" in out
    print("[PASS] Dashboard test passed.")


def test_all_servers_import():
    from mcp_win_stdio.excel.server import mcp as excel_mcp
    from mcp_win_stdio.word.server import mcp as word_mcp
    from mcp_win_stdio.explorer.server import mcp as explorer_mcp
    from mcp_win_stdio.tsc.server import mcp as tsc_mcp
    from mcp_win_stdio.db.server import mcp as db_mcp
    from mcp_win_stdio.git.server import mcp as git_mcp
    from mcp_win_stdio.ssh.server import mcp as ssh_mcp

    assert excel_mcp is not None
    assert word_mcp is not None
    assert explorer_mcp is not None
    assert tsc_mcp is not None
    assert db_mcp is not None
    assert git_mcp is not None
    assert ssh_mcp is not None
    print("[PASS] All 7 servers imported successfully from packages/.")


def test_updater():
    from mcp_win_stdio.core.updater import parse_version, format_update_banner, check_for_update

    assert parse_version("0.2.4") == (0, 2, 4)
    assert parse_version("0.2.4") > parse_version("0.2.3")
    assert parse_version("1.0.0") > parse_version("0.9.9")

    banner = format_update_banner("0.2.3", "0.2.4")
    assert "UPDATE AVAILABLE" in banner
    assert "v0.2.3" in banner
    assert "v0.2.4" in banner
    print("[PASS] Updater tests passed.")


if __name__ == "__main__":
    test_discovery()
    test_guides()
    test_dashboard()
    test_all_servers_import()
    test_updater()
    print("ALL TESTS PASSED!")
