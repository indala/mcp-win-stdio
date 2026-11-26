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
    """Verify is_cloudflared_installed detects installed binary and missing binary."""
    with patch("shutil.which", return_value=r"C:\bin\cloudflared.exe"):
        assert MwsTunnelManager.is_cloudflared_installed() is True
    with patch("shutil.which", return_value=None):
        assert MwsTunnelManager.is_cloudflared_installed() is False


def test_cmd_tunnel_preflight_help_and_non_interactive():
    """Verify cmd_tunnel launches and cleanly tears down with mocked cloudflared."""
    with patch.object(MwsTunnelManager, "is_cloudflared_installed", return_value=True), \
         patch("mcp_win_stdio.core.tunnel.subprocess.Popen") as mock_popen:
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


def test_tunnel_url_discovery_ignores_api_trycloudflare():
    """Verify cloudflared discovery ignores api.trycloudflare.com log lines and extracts arbitrary tunnel names."""
    with patch.object(MwsTunnelManager, "is_cloudflared_installed", return_value=True), \
         patch("mcp_win_stdio.core.tunnel.subprocess.Popen") as mock_popen:
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_proc.stderr.readline.side_effect = [
            "INF Requesting quick tunnel from https://api.trycloudflare.com/tunnel\n",
            "INF Connected to https://api.trycloudflare.com\n",
            "|  https://any-arbitrary-tunnel-name-8888.trycloudflare.com  |\n",
        ]
        mock_popen.return_value = mock_proc

        mgr = MwsTunnelManager(port=8993, mode="read_only", token="test_token_456")
        try:
            url = mgr.start_cloudflare_tunnel(timeout=5.0)
            assert url == "https://any-arbitrary-tunnel-name-8888.trycloudflare.com"
        finally:
            mgr.stop()


def test_tunnel_process_failure_logs_and_diagnostics():
    """Verify that unexpected cloudflared termination preserves stderr logs and provides diagnostics."""
    with patch.object(MwsTunnelManager, "is_cloudflared_installed", return_value=True), \
         patch("mcp_win_stdio.core.tunnel.subprocess.Popen") as mock_popen:
        mock_proc = MagicMock()
        mock_proc.poll.return_value = 1
        mock_proc.stderr.read.return_value = "failed to request quick Tunnel: wsarecv connection was forcibly closed"
        mock_popen.return_value = mock_proc

        mgr = MwsTunnelManager(port=8994, mode="read_only", token="test_token_789")
        try:
            with pytest.raises(RuntimeError) as exc_info:
                mgr.start_cloudflare_tunnel(timeout=5.0)
            msg = str(exc_info.value)
            assert "cloudflared process terminated unexpectedly (exit code 1)" in msg
            assert "wsarecv connection was forcibly closed" in msg
            assert "DIAGNOSIS" in msg
        finally:
            mgr.stop()


def test_ngrok_tunnel_url_discovery_and_domain():
    """Verify ngrok JSON log parsing and --domain flag forwarding."""
    with patch("mcp_win_stdio.core.tunnel.MwsTunnelManager.is_ngrok_installed", return_value=True), \
         patch("mcp_win_stdio.core.tunnel.subprocess.Popen") as mock_popen:
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_proc.stdout.readline.side_effect = [
            '{"lvl":"info","msg":"starting web service","addr":"127.0.0.1:4040"}\n',
            '{"lvl":"info","msg":"started tunnel","obj":"tunnels","addr":"http://127.0.0.1:8995","url":"https://my-custom.ngrok.app"}\n',
        ]
        mock_popen.return_value = mock_proc

        mgr = MwsTunnelManager(
            port=8995,
            mode="read_only",
            token="test_ngrok_tok",
            provider="ngrok",
            domain="my-custom.ngrok.app",
        )
        try:
            url = mgr.start_tunnel(timeout=5.0)
            assert url == "https://my-custom.ngrok.app"
            called_cmd = mock_popen.call_args[0][0]
            assert "--domain" in called_cmd
            assert "my-custom.ngrok.app" in called_cmd
            assert mgr.get_client_config()["mcpServers"]["mws"]["url"] == "https://my-custom.ngrok.app/mcp"
        finally:
            mgr.stop()


def test_ngrok_authtoken_error_diagnosis():
    """Verify ngrok missing authtoken failure surfaces actionable diagnostic hint."""
    with patch("mcp_win_stdio.core.tunnel.MwsTunnelManager.is_ngrok_installed", return_value=True), \
         patch("mcp_win_stdio.core.tunnel.subprocess.Popen") as mock_popen:
        mock_proc = MagicMock()
        mock_proc.poll.return_value = 1
        mock_proc.stdout.read.return_value = "ERR_NGROK_4018: authentication failed: Usage of ngrok requires a verified account and authtoken."
        mock_proc.stderr.read.return_value = ""
        mock_popen.return_value = mock_proc

        mgr = MwsTunnelManager(port=8996, mode="read_only", token="tok", provider="ngrok")
        try:
            with pytest.raises(RuntimeError) as exc_info:
                mgr.start_ngrok_tunnel(timeout=5.0)
            msg = str(exc_info.value)
            assert "ngrok process terminated unexpectedly" in msg
            assert "ngrok config add-authtoken" in msg
        finally:
            mgr.stop()


def test_direct_tunnel_modes_and_ssl_validation(tmp_path):
    """Verify direct provider URL resolution (HTTP, explicit public_url, and HTTPS with SSL files)."""
    # 1. Explicit public_url
    mgr = MwsTunnelManager(
        port=3000,
        host="0.0.0.0",
        mode="read_only",
        token="direct_tok",
        provider="direct",
        public_url="https://123.45.67.89:3000/",
    )
    assert mgr.start_tunnel() == "https://123.45.67.89:3000"
    assert mgr.get_client_config()["mcpServers"]["mws"]["url"] == "https://123.45.67.89:3000/mcp"

    # 2. HTTPS scheme inferred when ssl_certfile and ssl_keyfile are provided
    cert = tmp_path / "cert.pem"
    key = tmp_path / "key.pem"
    cert.write_text("dummy cert", encoding="utf-8")
    key.write_text("dummy key", encoding="utf-8")

    mgr_ssl = MwsTunnelManager(
        port=3000,
        host="123.45.67.89",
        mode="read_only",
        token="direct_ssl_tok",
        provider="direct",
        ssl_certfile=str(cert),
        ssl_keyfile=str(key),
    )
    assert mgr_ssl.start_tunnel() == "https://123.45.67.89:3000"

    # 3. Validation errors when only one SSL file is passed or file is missing
    with pytest.raises(ValueError):
        MwsTunnelManager(port=3000, provider="direct", ssl_certfile=str(cert))

    with pytest.raises(FileNotFoundError):
        MwsTunnelManager(
            port=3000,
            provider="direct",
            ssl_certfile=str(tmp_path / "missing.pem"),
            ssl_keyfile=str(key),
        )


def test_direct_cert_generation_import_and_discovery(tmp_path):
    """Verify ~/.mcp-win-stdio/certs/ generation, import, and auto-discovery."""
    from mcp_win_stdio.core.tunnel import (
        generate_direct_self_signed_cert,
        get_stored_direct_certs,
        import_direct_certs,
    )

    certs_dir = tmp_path / "certs"
    assert get_stored_direct_certs(certs_dir) is None

    cert_p, key_p = generate_direct_self_signed_cert("123.45.67.89", certs_dir=certs_dir, days=90)
    assert cert_p.is_file()
    assert key_p.is_file()
    assert "BEGIN CERTIFICATE" in cert_p.read_text(encoding="utf-8")

    discovered = get_stored_direct_certs(certs_dir)
    assert discovered == (cert_p, key_p)

    # Import custom certs into a separate certs dir
    src_cert = tmp_path / "zerossl_cert.pem"
    src_key = tmp_path / "zerossl_key.pem"
    src_cert.write_text("ZEROSSL CERT", encoding="utf-8")
    src_key.write_text("ZEROSSL KEY", encoding="utf-8")

    import_dir = tmp_path / "imported_certs"
    imp_c, imp_k = import_direct_certs(src_cert, src_key, certs_dir=import_dir)
    assert imp_c.read_text(encoding="utf-8") == "ZEROSSL CERT"
    assert imp_k.read_text(encoding="utf-8") == "ZEROSSL KEY"


def test_ngrok_authtoken_detection_and_interactive_redirect(tmp_path, monkeypatch):
    """Verify authtoken detection and automatic browser redirect + inline token save."""
    from mcp_win_stdio.cli import _ensure_tunnel_provider_binary

    monkeypatch.delenv("NGROK_AUTHTOKEN", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)

    assert MwsTunnelManager.has_ngrok_authtoken() is False

    # Env var detection
    monkeypatch.setenv("NGROK_AUTHTOKEN", "env_tok_123")
    assert MwsTunnelManager.has_ngrok_authtoken() is True
    monkeypatch.delenv("NGROK_AUTHTOKEN", raising=False)

    # Interactive redirect + save
    with patch("mcp_win_stdio.core.tunnel.MwsTunnelManager.is_ngrok_installed", return_value=True), \
         patch("mcp_win_stdio.core.tunnel.MwsTunnelManager.configure_ngrok_authtoken", return_value=True) as mock_cfg, \
         patch("sys.stdin.isatty", return_value=True), \
         patch("webbrowser.open") as mock_open, \
         patch("builtins.input", return_value="2abc_ngrok_token_xyz"):
        _ensure_tunnel_provider_binary("ngrok", MwsTunnelManager)
        mock_open.assert_called_once_with("https://dashboard.ngrok.com/get-started/your-authtoken")
        mock_cfg.assert_called_once_with("2abc_ngrok_token_xyz")

