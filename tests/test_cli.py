"""
Tests for mcp-win-stdio CLI, discovery, and servers.
"""

import subprocess
import sys
from mcp_win_stdio.core.discovery import list_available_servers, get_server_info
from mcp_win_stdio.core.config import ensure_workspace_dirs

def test_discovery():
    ensure_workspace_dirs()
    servers = list_available_servers()
    assert "excel" in servers
    assert "explorer" in servers
    assert servers["excel"]["tools_count"] == 20
    assert servers["explorer"]["tools_count"] == 11
    print("[PASS] Discovery test passed.")

def test_imports():
    from mcp_win_stdio.servers.excel.server import mcp as excel_mcp
    from mcp_win_stdio.servers.explorer.server import mcp as explorer_mcp
    assert excel_mcp is not None
    assert explorer_mcp is not None
    print("[PASS] Server import test passed.")

if __name__ == "__main__":
    test_discovery()
    test_imports()
    print("ALL BASIC TESTS PASSED!")
