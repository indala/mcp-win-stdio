import json
import os
import sys
import tempfile
import time
from pathlib import Path
import pytest

for p in Path("packages").glob("*/src"):
    sys.path.insert(0, str(p.resolve()))
sys.path.insert(0, os.path.abspath("src"))

from mcp_win_stdio.db import server


def test_list_connections_with_claude_desktop_env():
    """Test loading and rapid execution of list_connections using Claude Desktop config SERVERS env."""
    claude_cfg_path = Path(os.environ.get("APPDATA", "")) / "Claude" / "claude_desktop_config.json"
    if not claude_cfg_path.exists():
        pytest.skip("Claude Desktop configuration not found on this machine.")

    with open(claude_cfg_path, "r", encoding="utf-8") as f:
        cfg = json.load(f)

    db_cfg = cfg.get("mcpServers", {}).get("db", {})
    servers_val = db_cfg.get("env", {}).get("SERVERS")
    if not servers_val:
        pytest.skip("No SERVERS env in Claude Desktop db config.")

    # Apply SERVERS env and re-initialize config
    os.environ["SERVERS"] = servers_val
    server._RAW_CONFIG.clear()
    server._CONNECTION_REGISTRY.clear()
    server._ACTIVE_CONNECTION = None
    server._init_config()

    t0 = time.time()
    res = server.list_connections()
    elapsed_ms = (time.time() - t0) * 1000

    assert elapsed_ms < 50, f"list_connections took too long: {elapsed_ms}ms"
    assert res["totalConnections"] >= 2
    conn_names = [c["name"] for c in res["connections"]]
    assert "live_mysql_server" in conn_names
    assert "postgres_local_server" in conn_names
    assert "default" not in conn_names  # Ensure metadata 'default' is not exposed as a connection


def test_no_infinite_recursion_with_dangling_default():
    """Ensure that a connections.json containing only {'default': 'dangling'} does not cause recursion."""
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w", encoding="utf-8") as tf:
        json.dump({"default": "non_existent_server"}, tf)
        temp_cfg = tf.name

    old_cfg_env = os.environ.get("CONFIG_FILE")
    old_servers = os.environ.get("SERVERS")
    try:
        os.environ["CONFIG_FILE"] = temp_cfg
        os.environ.pop("SERVERS", None)
        server._RAW_CONFIG.clear()
        server._CONNECTION_REGISTRY.clear()
        server._ACTIVE_CONNECTION = None
        server._init_config()

        t0 = time.time()
        res = server.list_connections()
        elapsed_ms = (time.time() - t0) * 1000
        assert elapsed_ms < 50, f"list_connections hung or was slow: {elapsed_ms}ms"
        assert res["totalConnections"] == 0
    finally:
        if old_cfg_env:
            os.environ["CONFIG_FILE"] = old_cfg_env
        else:
            os.environ.pop("CONFIG_FILE", None)
        if old_servers:
            os.environ["SERVERS"] = old_servers
        try:
            os.remove(temp_cfg)
        except Exception:
            pass


def test_add_and_remove_connection():
    """Test dynamically adding and removing connection."""
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w", encoding="utf-8") as tf:
        json.dump({}, tf)
        temp_cfg = tf.name

    old_cfg_env = os.environ.get("CONFIG_FILE")
    os.environ["CONFIG_FILE"] = temp_cfg
    try:
        # Mock add without real connect by setting into registry
        server._RAW_CONFIG["test_temp_db"] = "postgresql://usr:pwd@localhost:5432/temp_db"
        server._save_connection("test_temp_db", "postgresql://usr:pwd@localhost:5432/temp_db")

        conns = server.list_connections()
        assert any(c["name"] == "test_temp_db" for c in conns["connections"])

        # Test remove
        rem_res = server.remove_connection("test_temp_db")
        assert rem_res["success"] is True
        assert "test_temp_db" not in rem_res["remainingConnections"]

        conns_after = server.list_connections()
        assert not any(c["name"] == "test_temp_db" for c in conns_after["connections"])
    finally:
        if old_cfg_env:
            os.environ["CONFIG_FILE"] = old_cfg_env
        else:
            os.environ.pop("CONFIG_FILE", None)
        server._RAW_CONFIG.pop("test_temp_db", None)
        server._CONNECTION_REGISTRY.pop("test_temp_db", None)
        try:
            os.remove(temp_cfg)
        except Exception:
            pass
