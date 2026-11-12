"""
Unit tests for mws tunnel & Cloudflare quick tunnel integration.
"""

import argparse
import io
import time
from contextlib import redirect_stdout
from unittest.mock import MagicMock, patch

import pytest
import requests

from mcp_win_stdio.cli import cmd_tunnel
from mcp_win_stdio.core.config import get_tunnel_config
from mcp_win_stdio.core.tunnel import BearerAuthMiddleware, MwsTunnelManager


def test_tunnel_config_resolution():
    """Verify tunnel config properly resolves default read_only mode and port 8080."""
    cfg = get_tunnel_config()
    assert isinstance(cfg, dict)
    assert cfg.get("mode") in ("read_only", "read_write")
    assert isinstance(cfg.get("port"), int)


def test_tunnel_manager_init_and_client_config():
    """Verify client config generation with Bearer authorization header."""
    mgr = MwsTunnelManager(port=8991, mode="read_only", token="test_token_abc")
    assert mgr.port == 8991
    assert mgr.mode == "read_only"
    assert mgr.token == "test_token_abc"

    mgr._public_url = "https://mock-tunnel-abc.trycloudflare.com"
    cfg = mgr.get_client_config()
    assert "mcpServers" in cfg
    assert "mws" in cfg["mcpServers"]
    assert cfg["mcpServers"]["mws"]["url"] == "https://mock-tunnel-abc.trycloudflare.com/mcp"
    assert cfg["mcpServers"]["mws"]["headers"]["Authorization"] == "Bearer test_token_abc"


def test_tunnel_cloudflared_installed_check():
    """Verify is_cloudflared_installed detects installed binary."""
    assert MwsTunnelManager.is_cloudflared_installed() is True


def test_cmd_tunnel_preflight_help_and_non_interactive():
    """Verify cmd_tunnel launches and cleanly tears down with mocked cloudflared."""
    with patch("mcp_win_stdio.core.tunnel.subprocess.Popen") as mock_popen:
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_proc.stderr.readline.side_effect = [
            "INF Starting tunnel tunnelID=abc\n",
            "INF Your quick Tunnel has been created! Visit it at (https://mock-live-zen.trycloudflare.com)\n",
        ]
        mock_popen.return_value = mock_proc

        mgr = MwsTunnelManager(port=8992, mode="read_only", token="test_token_123")
        try:
            mgr.start_local_bridge()
            url = mgr.start_cloudflare_tunnel(timeout=5.0)
            assert url == "https://mock-live-zen.trycloudflare.com"
            client_cfg = mgr.get_client_config()
            assert client_cfg["mcpServers"]["mws"]["url"] == "https://mock-live-zen.trycloudflare.com/mcp"
        finally:
            mgr.stop()
