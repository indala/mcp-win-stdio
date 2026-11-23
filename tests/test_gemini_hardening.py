import time
from unittest.mock import MagicMock
import pytest
from starlette.requests import Request
from starlette.responses import Response

from mcp_win_stdio.core.tunnel import TunnelAuthMiddleware
from mcp_win_stdio.core.tunnel_auth import BearerAuthProvider
from mcp_win_stdio.db.server import (
    _extract_mysql_matched_changed_rows,
    _get_connection,
    _RAW_CONFIG,
    _CONNECTION_REGISTRY,
)


def test_unknown_connection_alias_fails_fast():
    """Verify that an unknown connection alias raises ValueError immediately with configured aliases."""
    _RAW_CONFIG.clear()
    _CONNECTION_REGISTRY.clear()
    _RAW_CONFIG["live_mysql_server"] = "mysql://user:pass@srv604.hstgr.io:3306/db"
    _RAW_CONFIG["showreel_dev"] = "postgresql://user:pass@localhost:5432/showreel_dev"

    start_time = time.time()
    with pytest.raises(ValueError) as excinfo:
        _get_connection("ijitest")

    duration = time.time() - start_time
    err_msg = str(excinfo.value)

    assert "Unknown connection alias 'ijitest'" in err_msg
    assert "live_mysql_server" in err_msg
    assert "showreel_dev" in err_msg
    # Must fail fast (< 0.2s) instead of waiting for a 2.0s localhost probe timeout
    assert duration < 0.5


def test_extract_mysql_matched_changed_rows():
    """Verify regex parsing of MySQL OK packet message string."""
    mock_cur = MagicMock()
    mock_conn = MagicMock()
    mock_cur._result.message = b"Rows matched: 1  Changed: 0  Warnings: 0"

    matched, changed = _extract_mysql_matched_changed_rows(mock_cur, mock_conn)
    assert matched == 1
    assert changed == 0

    # Test when changes occurred
    mock_cur._result.message = "Rows matched: 5  Changed: 3  Warnings: 0"
    matched, changed = _extract_mysql_matched_changed_rows(mock_cur, mock_conn)
    assert matched == 5
    assert changed == 3

    # Test when message is empty or unrelated
    mock_cur._result.message = None
    mock_conn._result.message = None
    matched, changed = _extract_mysql_matched_changed_rows(mock_cur, mock_conn)
    assert matched is None
    assert changed is None


@pytest.mark.anyio
async def test_tunnel_health_and_buffering_headers():
    """Verify /health endpoint returns uptime, permission_mode, and CORS headers."""
    auth_provider = BearerAuthProvider(token="test-token")
    app = MagicMock()

    async def mock_call_next(request):
        return Response("ok", media_type="text/plain")

    middleware = TunnelAuthMiddleware(app=app, auth_provider=auth_provider, permission_mode="read_write")

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/health",
        "headers": [],
    }
    request = Request(scope)
    resp = await middleware.dispatch(request, mock_call_next)

    assert resp.status_code == 200
    import json
    body = json.loads(resp.body.decode("utf-8"))
    assert body["status"] == "ok"
    assert body["service"] == "mws-tunnel"
    assert body["permission_mode"] == "read_write"
    assert "uptime_seconds" in body
    assert resp.headers["access-control-allow-origin"] == "*"
    assert resp.headers["cache-control"] == "no-cache, no-store, must-revalidate"
