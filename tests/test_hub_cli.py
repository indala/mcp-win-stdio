"""
Unit and integration tests for Hub CLI and Control Plane (Phase 5 Step 3).
Validates parser contracts, mutually exclusive flags, instance acquisition & ownership,
stale PID cleanup, cross-process IPC, status formatting (human & JSON), and graceful stop.
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from mcp_win_stdio.cli import cmd_hub_status, cmd_hub_stop
from mcp_win_stdio.core.hub.config_loader import LoadedHubConfig
from mcp_win_stdio.core.hub.control import (
    HubControlClient,
    HubControlServer,
    HubInstanceManager,
    is_pid_alive,
)
from mcp_win_stdio.core.hub.models import HubConfig
from mcp_win_stdio.core.hub.orchestrator import HubOrchestrator
from mcp_win_stdio.core.hub.profiles import ProfileManager


def test_parser_mutually_exclusive_flags():
    """--foreground and --daemon are strictly mutually exclusive."""
    cmd = [sys.executable, "-m", "mcp_win_stdio.cli", "hub", "start", "--foreground", "--daemon"]
    res = subprocess.run(cmd, capture_output=True, text=True, stdin=subprocess.DEVNULL)
    assert res.returncode != 0
    assert "not allowed with argument" in res.stderr.lower() or "error" in res.stderr.lower()


def test_instance_manager_acquire_and_release(tmp_path):
    """InstanceManager acquires lock, writes metadata, and releases cleanly."""
    inst_file = tmp_path / "hub_instance.json"
    mgr = HubInstanceManager(metadata_path=inst_file)

    assert not mgr.is_running()[0]

    # Acquire
    meta = mgr.acquire(
        pid=os.getpid(),
        pipe_name=r"\\.\pipe\test-pipe-inst",
        config_source="test",
        http_host="127.0.0.1",
        http_port=8080,
    )
    assert inst_file.is_file()
    assert meta.pid == os.getpid()

    # Second acquire must fail because it's already running (when IPC responds or PID alive)
    # Mocking IPC ping to return os.getpid()
    HubControlClient.ping = lambda pipe, auth, timeout=1.0: os.getpid()
    running, active_meta = mgr.is_running()
    assert running is True
    assert active_meta.pid == os.getpid()

    with pytest.raises(RuntimeError, match="MCP Hub is already running"):
        mgr.acquire(pid=os.getpid() + 1, pipe_name=r"\\.\pipe\other")

    # Release
    mgr.release()
    assert not inst_file.exists()


def test_stale_pid_metadata_purged_automatically(tmp_path):
    """If metadata references a non-existent PID, is_running() cleans it up safely."""
    inst_file = tmp_path / "hub_instance.json"
    mgr = HubInstanceManager(metadata_path=inst_file)

    # Write metadata with an impossibly high PID that doesn't exist
    fake_pid = 999999
    inst_file.write_text(
        json.dumps(
            {
                "pid": fake_pid,
                "started_at": time.time(),
                "pipe_name": r"\\.\pipe\ghost-pipe",
                "authkey_hex": "abcd1234abcd1234",
                "config_source": "test",
                "http_host": "127.0.0.1",
                "http_port": 8080,
            }
        ),
        encoding="utf-8",
    )

    running, meta = mgr.is_running()
    assert running is False
    assert meta is None
    # Stale file must have been purged
    assert not inst_file.exists()


def test_pid_alive_helper():
    """is_pid_alive accurately identifies current process and invalid PIDs."""
    assert is_pid_alive(os.getpid()) is True
    assert is_pid_alive(-1) is False
    assert is_pid_alive(0) is False
    assert is_pid_alive(9999999) is False


def test_control_server_ping_status_and_stop(tmp_path):
    """HubControlServer responds to ping, status, and stop over local named pipe IPC."""
    import secrets

    pipe_name = f"\\\\.\\pipe\\test-ctrl-{secrets.token_hex(4)}"
    authkey_hex = secrets.token_hex(16)

    cfg = HubConfig(schema_version="1.0")
    loaded = LoadedHubConfig(config=cfg, source_path=None, source_tier="test", profile_manager=ProfileManager())
    orchestrator = HubOrchestrator(loaded_config=loaded)
    orchestrator.start()

    stopped_flag = [False]

    def on_stop():
        stopped_flag[0] = True
        orchestrator.stop()

    server = HubControlServer(
        orchestrator=orchestrator,
        pipe_name=pipe_name,
        authkey_hex=authkey_hex,
        on_stop_requested=on_stop,
    )
    server.start()

    try:
        # 1. Ping
        pid = HubControlClient.ping(pipe_name, authkey_hex)
        assert pid == os.getpid()

        # 2. Status
        st = HubControlClient.get_status(pipe_name, authkey_hex)
        assert st is not None
        assert st["state"] == "running"
        assert st["http_port"] == 8080

        # 3. Stop
        stop_ack = HubControlClient.request_stop(pipe_name, authkey_hex)
        assert stop_ack is True

        time.sleep(0.5)
        assert stopped_flag[0] is True
        assert orchestrator.lifecycle_state.value == "stopped"
    finally:
        server.stop()
        orchestrator.stop()


def test_cli_status_json_when_stopped(capsys):
    """mws hub status --json outputs valid JSON with running=False when stopped."""
    import argparse

    args = argparse.Namespace(json=True)

    # Ensure no running instance
    mgr = HubInstanceManager()
    mgr.release()

    with pytest.raises(SystemExit) as exc:
        cmd_hub_status(args)
    assert exc.value.code == 0

    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert data["running"] is False
    assert data["state"] == "stopped"


def test_cli_stop_when_not_running(capsys):
    """mws hub stop gracefully reports when hub is not running."""
    import argparse

    args = argparse.Namespace(timeout=5.0)

    mgr = HubInstanceManager()
    mgr.release()

    with pytest.raises(SystemExit) as exc:
        cmd_hub_stop(args)
    assert exc.value.code == 0

    captured = capsys.readouterr()
    assert "not currently running" in captured.out


def test_cli_stop_rejects_negative_timeout(capsys):
    """mws hub stop --timeout -1 returns actionable error."""
    import argparse

    args = argparse.Namespace(timeout=-1.0)

    with pytest.raises(SystemExit) as exc:
        cmd_hub_stop(args)
    assert exc.value.code == 1

    captured = capsys.readouterr()
    assert "positive number" in captured.out


def test_cli_detached_daemon_lifecycle(tmp_path):
    """Test native detached process startup, polling, status query, and graceful stop."""
    config_file = tmp_path / "daemon_test_hub.yaml"
    config_file.write_text(
        "schema_version: '1.0'\nruntime:\n  http_bridge:\n    port: 8977\ntools:\n  allow: ['*']\nservers: {}\n",
        encoding="utf-8",
    )
    cmd_start = [
        sys.executable,
        "-m",
        "mcp_win_stdio.cli",
        "hub",
        "start",
        "--daemon",
        "--config",
        str(config_file),
    ]
    res_start = subprocess.run(cmd_start, capture_output=True, text=True, timeout=15, stdin=subprocess.DEVNULL)
    assert res_start.returncode == 0
    assert "MCP Hub started in background" in res_start.stdout

    try:
        # Status query
        cmd_status = [sys.executable, "-m", "mcp_win_stdio.cli", "hub", "status", "--json"]
        res_status = subprocess.run(cmd_status, capture_output=True, text=True, timeout=5, stdin=subprocess.DEVNULL)
        assert res_status.returncode == 0
        data = json.loads(res_status.stdout)
        assert data["running"] is True
        assert data["http_endpoint"] == "http://127.0.0.1:8977"
    finally:
        # Graceful stop
        cmd_stop = [sys.executable, "-m", "mcp_win_stdio.cli", "hub", "stop", "--timeout", "5.0"]
        res_stop = subprocess.run(cmd_stop, capture_output=True, text=True, timeout=10, stdin=subprocess.DEVNULL)
        assert res_stop.returncode == 0
        assert "stopped successfully" in res_stop.stdout
