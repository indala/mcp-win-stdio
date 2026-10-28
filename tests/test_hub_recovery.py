"""
Tests for Phase 6.1 Step 3: Crash Recovery & Stale-State Resilience.

Validates:
1. Automatic recovery and stale-metadata purging on dead PID.
2. PID reuse protection using 64-bit kernel creation timestamps (GetProcessTimes).
3. Live process protection: hung or unresponsive IPC NEVER purges metadata of a live Hub.
4. Concurrent acquire mutual exclusion via cross-process filesystem locking.
5. Force stop (--force) terminating hung Hub instances and clearing metadata.
6. Hub status reporting of 'unresponsive' state for live processes with hung IPC.
"""

import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from mcp_win_stdio.core.hub.control import (
    HubControlClient,
    HubInstanceManager,
    HubInstanceMetadata,
    get_process_creation_time,
    is_pid_alive,
)
from mcp_win_stdio.core.hub.security import interprocess_file_lock


def test_recovery_from_dead_pid_purges_stale_metadata(tmp_path):
    """When a Hub process terminates abruptly, subsequent is_running() must purge stale metadata."""
    meta_file = tmp_path / "hub_instance.json"
    mgr = HubInstanceManager(metadata_path=meta_file)

    # Spawn short-lived dummy process to obtain a dead PID
    proc = subprocess.Popen([sys.executable, "-c", "import sys; sys.exit(0)"])
    proc.wait()
    dead_pid = proc.pid
    assert is_pid_alive(dead_pid) is False

    # Simulate stale metadata left behind after crash
    stale_meta = HubInstanceMetadata(
        pid=dead_pid,
        started_at=time.time() - 100,
        pipe_name=r"\\.\pipe\mws-stale-pipe",
        authkey_hex="0123456789abcdef0123456789abcdef",
        config_path=None,
        config_source="default",
        http_host="127.0.0.1",
        http_port=8080,
        creation_time=123456789,
    )
    from mcp_win_stdio.core.hub.security import write_secure_json_file

    write_secure_json_file(meta_file, stale_meta.to_dict())
    assert meta_file.is_file() is True

    # is_running() must detect dead PID, purge stale metadata, and report False, None
    is_running, meta = mgr.is_running()
    assert is_running is False
    assert meta is None
    assert meta_file.exists() is False

    # Subsequent acquire must succeed cleanly
    my_pid = os.getpid()
    new_meta = mgr.acquire(pid=my_pid, pipe_name=r"\\.\pipe\mws-new-pipe")
    assert new_meta.pid == my_pid
    assert meta_file.is_file() is True
    mgr.release()


def test_pid_reuse_detected_by_creation_time_purges_stale_metadata(tmp_path):
    """
    If the OS recycles a PID for an unrelated process, the 64-bit creation timestamp
    must detect the mismatch and purge the stale metadata rather than treating it as live.
    """
    meta_file = tmp_path / "hub_instance.json"
    mgr = HubInstanceManager(metadata_path=meta_file)

    current_pid = os.getpid()
    live_ct = get_process_creation_time(current_pid)

    if live_ct is None:
        pytest.skip("Process creation time not available on this platform")

    # Write metadata with current PID but mismatched creation timestamp (simulating recycled PID)
    stale_ct = live_ct - 999999999
    stale_meta = HubInstanceMetadata(
        pid=current_pid,
        started_at=time.time() - 3600,
        pipe_name=r"\\.\pipe\mws-recycled-pipe",
        authkey_hex="0123456789abcdef0123456789abcdef",
        config_path=None,
        config_source="default",
        http_host="127.0.0.1",
        http_port=8080,
        creation_time=stale_ct,
    )
    from mcp_win_stdio.core.hub.security import write_secure_json_file

    write_secure_json_file(meta_file, stale_meta.to_dict())

    # is_running() must detect that live process is NOT the hub that wrote the file
    is_running, meta = mgr.is_running()
    assert is_running is False
    assert meta is None
    # Stale metadata was purged
    assert meta_file.exists() is False


def test_hung_ipc_never_purges_live_process_metadata(tmp_path):
    """
    CRITICAL INVARIANT: A health check or IPC ping timeout must NEVER delete metadata
    or terminate a process that is confirmed alive in the OS kernel.
    """
    meta_file = tmp_path / "hub_instance.json"
    mgr = HubInstanceManager(metadata_path=meta_file)

    # Spawn real running process that will keep running
    dummy = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    try:
        live_pid = dummy.pid
        live_ct = get_process_creation_time(live_pid)
        assert is_pid_alive(live_pid) is True

        # Point metadata to a dummy, non-existent pipe (simulating hung/unresponsive IPC)
        dummy_pipe = rf"\\.\pipe\mws-hung-pipe-{os.getpid()}-{time.time_ns()}"
        meta_live = HubInstanceMetadata(
            pid=live_pid,
            started_at=time.time() - 100,  # Older than 15s
            pipe_name=dummy_pipe,
            authkey_hex="0123456789abcdef0123456789abcdef",
            config_path=None,
            config_source="default",
            http_host="127.0.0.1",
            http_port=8080,
            creation_time=live_ct,
        )
        from mcp_win_stdio.core.hub.security import write_secure_json_file

        write_secure_json_file(meta_file, meta_live.to_dict())

        # Probe is_running() multiple times
        for _ in range(3):
            is_running, meta = mgr.is_running()
            # is_running is False because IPC ping timed out, BUT meta is preserved!
            assert is_running is False
            assert meta is not None
            assert meta.pid == live_pid
            # The file MUST still exist on disk!
            assert meta_file.is_file() is True
            # The process MUST still be alive in kernel!
            assert is_pid_alive(live_pid) is True

        # Attempting to start/acquire another instance MUST be rejected
        with pytest.raises(RuntimeError, match="MCP Hub is already running"):
            mgr.acquire(pid=os.getpid(), pipe_name=r"\\.\pipe\mws-other")

    finally:
        dummy.kill()
        dummy.wait()
        mgr.release()


def test_interprocess_file_lock_mutual_exclusion(tmp_path):
    """Verify that interprocess_file_lock enforces mutual exclusion across locks."""
    lock_file = tmp_path / "test.lock"

    # Acquire first lock
    with interprocess_file_lock(lock_file, timeout=2.0):
        # Attempt to acquire a second lock with small timeout -> must raise TimeoutError
        with pytest.raises(TimeoutError):
            with interprocess_file_lock(lock_file, timeout=0.3):
                pass

    # Once released, second acquisition succeeds immediately
    with interprocess_file_lock(lock_file, timeout=2.0):
        assert True


def test_concurrent_acquire_mutual_exclusion(tmp_path):
    """
    Test concurrent acquire() attempts on the same HubInstanceManager metadata path.
    Only one invocation must succeed; the other must receive RuntimeError.
    """
    meta_file = tmp_path / "hub_instance.json"
    mgr1 = HubInstanceManager(metadata_path=meta_file)
    mgr2 = HubInstanceManager(metadata_path=meta_file)

    results = []
    barrier = threading.Barrier(2)

    def worker(mgr_inst, dummy_pid, pipe):
        try:
            barrier.wait(timeout=5.0)
            meta = mgr_inst.acquire(pid=dummy_pid, pipe_name=pipe)
            results.append(("success", meta))
        except Exception as e:
            results.append(("error", str(e)))

    # Use current process PID for worker 1 (confirmed alive)
    # and a separate live child process PID for worker 2
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(10)"])
    try:
        t1 = threading.Thread(target=worker, args=(mgr1, os.getpid(), r"\\.\pipe\mws-pipe-1"))
        t2 = threading.Thread(target=worker, args=(mgr2, child.pid, r"\\.\pipe\mws-pipe-2"))

        t1.start()
        t2.start()
        t1.join(timeout=5.0)
        t2.join(timeout=5.0)

        successes = [r for r in results if r[0] == "success"]
        errors = [r for r in results if r[0] == "error"]

        assert len(successes) == 1, f"Expected 1 success, got {len(successes)}: {results}"
        assert len(errors) == 1, f"Expected 1 error, got {len(errors)}: {results}"
        assert "already running" in errors[0][1]

    finally:
        child.kill()
        child.wait()
        mgr1.release()


def test_cli_hub_status_reports_unresponsive_for_live_process(tmp_path, capsys):
    """Verify CLI hub status reports 'unresponsive' state for live process with hung IPC."""
    meta_file = tmp_path / "hub_instance.json"
    dummy = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])

    try:
        live_pid = dummy.pid
        live_ct = get_process_creation_time(live_pid)

        import argparse

        from mcp_win_stdio.cli import cmd_hub_status

        stale_meta = HubInstanceMetadata(
            pid=live_pid,
            started_at=time.time(),
            pipe_name=rf"\\.\pipe\mws-dummy-pipe-{os.getpid()}-{time.time_ns()}",
            authkey_hex="0123456789abcdef0123456789abcdef",
            config_path=None,
            config_source="default",
            http_host="127.0.0.1",
            http_port=8080,
            creation_time=live_ct,
        )
        from mcp_win_stdio.core.hub.security import write_secure_json_file

        write_secure_json_file(meta_file, stale_meta.to_dict())

        # Run cmd_hub_status with --json
        args_json = argparse.Namespace(json=True, config=None)
        with patch("mcp_win_stdio.core.hub.control.USER_DIR", tmp_path):
            with patch("mcp_win_stdio.cli.USER_DIR", tmp_path):
                with pytest.raises(SystemExit) as exc:
                    cmd_hub_status(args_json)
                assert exc.value.code == 0

        out = capsys.readouterr().out
        data = json.loads(out)
        assert data["running"] is False
        assert data["state"] == "unresponsive"
        assert data["pid"] == live_pid
        assert meta_file.is_file() is True

    finally:
        dummy.kill()
        dummy.wait()


def test_cli_hub_stop_force_kills_hung_hub(tmp_path):
    """Verify that 'mws hub stop --force' terminates a hung Hub process and cleans metadata."""
    meta_file = tmp_path / "hub_instance.json"
    dummy = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])

    try:
        live_pid = dummy.pid
        live_ct = get_process_creation_time(live_pid)

        meta = HubInstanceMetadata(
            pid=live_pid,
            started_at=time.time(),
            pipe_name=rf"\\.\pipe\mws-dummy-pipe-{os.getpid()}-{time.time_ns()}",
            authkey_hex="0123456789abcdef0123456789abcdef",
            config_path=None,
            config_source="default",
            http_host="127.0.0.1",
            http_port=8080,
            creation_time=live_ct,
        )
        from mcp_win_stdio.core.hub.security import write_secure_json_file

        write_secure_json_file(meta_file, meta.to_dict())

        import argparse

        from mcp_win_stdio.cli import cmd_hub_stop

        args = argparse.Namespace(timeout=1.0, force=True)
        with patch("mcp_win_stdio.core.hub.control.USER_DIR", tmp_path):
            with patch("mcp_win_stdio.cli.USER_DIR", tmp_path):
                with pytest.raises(SystemExit) as exc:
                    cmd_hub_stop(args)
                assert exc.value.code == 0

        # Verify child is dead in OS kernel
        assert is_pid_alive(live_pid) is False
        # Verify metadata was released
        assert meta_file.exists() is False

    finally:
        if dummy.poll() is None:
            dummy.kill()
            dummy.wait()


def test_partial_startup_crash_recovery(tmp_path):
    """
    If a Hub process crashes halfway during startup (e.g. after writing metadata
    but before initializing control pipes or HTTP listeners), the dead PID is detected
    and purged cleanly upon the next invocation.
    """
    meta_file = tmp_path / "hub_instance.json"
    mgr = HubInstanceManager(metadata_path=meta_file)

    # Spawn process that immediately crashes
    crash_proc = subprocess.Popen([sys.executable, "-c", "import sys; sys.exit(42)"])
    crash_proc.wait()
    crashed_pid = crash_proc.pid

    # Write partial startup metadata
    partial_meta = HubInstanceMetadata(
        pid=crashed_pid,
        started_at=time.time(),
        pipe_name=rf"\\.\pipe\mws-partial-{crashed_pid}",
        authkey_hex="abcdef0123456789abcdef0123456789",
        config_path=None,
        config_source="default",
        http_host="127.0.0.1",
        http_port=8080,
    )
    from mcp_win_stdio.core.hub.security import write_secure_json_file

    write_secure_json_file(meta_file, partial_meta.to_dict())
    assert meta_file.is_file() is True

    # Next startup / status inquiry runs
    is_running, meta = mgr.is_running()
    assert is_running is False
    assert meta is None
    assert meta_file.exists() is False

    # Startup succeeds cleanly
    new_meta = mgr.acquire(pid=os.getpid(), pipe_name=r"\\.\pipe\mws-recovered-pipe")
    assert new_meta.pid == os.getpid()
    mgr.release()


def test_cli_hub_restart_stopped_instance(tmp_path):
    """Verify that restarting a stopped hub starts it freshly."""
    import argparse

    from mcp_win_stdio.cli import cmd_hub_restart

    args = argparse.Namespace(
        timeout=2.0,
        force=False,
        foreground=False,
        daemon=True,
        config=None,
        internal_daemon=False,
    )

    started = []

    def mock_start(a):
        started.append(True)

    with patch("mcp_win_stdio.core.hub.control.USER_DIR", tmp_path):
        with patch("mcp_win_stdio.cli.USER_DIR", tmp_path):
            with patch("mcp_win_stdio.cli.cmd_hub_start", side_effect=mock_start):
                cmd_hub_restart(args)

    assert len(started) == 1


@pytest.mark.skipif(sys.platform != "win32", reason="Windows Job Object daemon process tree test")
def test_force_stop_terminates_full_hub_process_tree(tmp_path):
    """
    End-to-End Test: Launch a Hub daemon with a supervised MCP child that spawns a grandchild.
    Execute 'mws hub stop --force' (which forcibly kills the hub PID via taskkill /F).
    Verify that the Windows Job Object kill-on-close mechanism guarantees that all 3 processes
    (Hub daemon, MCP child, and grandchild) are completely terminated by the OS kernel within bounded timeout.
    """
    sync_file = tmp_path / "tree_pids.json"
    child_script = tmp_path / "tree_child.py"
    child_code = f"""
import sys, os, time, json, subprocess
from mcp_win_stdio.core.hub.control import get_process_creation_time

sync_path = r"{sync_file}"
gc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
my_pid = os.getpid()
my_ct = get_process_creation_time(my_pid)
gc_ct = get_process_creation_time(gc.pid)

with open(sync_path, "w", encoding="utf-8") as f:
    json.dump({{"child_pid": my_pid, "child_ct": my_ct, "gc_pid": gc.pid, "gc_ct": gc_ct}}, f)

for line in iter(sys.stdin.readline, ""):
    req = json.loads(line)
    mid = req.get("id")
    method = req.get("method")
    if method == "initialize":
        res = {{"jsonrpc": "2.0", "id": mid, "result": {{"protocolVersion": "2024-11-05", "serverInfo": {{"name": "tree_child", "version": "1.0"}}}}}}
    elif method == "tools/list":
        res = {{"jsonrpc": "2.0", "id": mid, "result": {{"tools": []}}}}
    else:
        res = {{"jsonrpc": "2.0", "id": mid, "result": {{}}}}
    sys.stdout.write(json.dumps(res) + "\\n")
    sys.stdout.flush()
"""
    child_script.write_text(child_code, encoding="utf-8")

    # Write hub config
    cfg_file = tmp_path / "hub_tree.yaml"
    cfg_text = f"""schema_version: '1.0'
runtime:
  http_bridge:
    port: 8993
tools:
  allow: ['*']
servers:
  tree_srv:
    command: "{sys.executable.replace(chr(92), "/")}"
    args: ["{str(child_script).replace(chr(92), "/")}"]
"""
    cfg_file.write_text(cfg_text, encoding="utf-8")

    hub_pid = None
    child_pid = None
    gc_pid = None

    try:
        # Start hub daemon
        cmd_start = [
            sys.executable,
            "-m",
            "mcp_win_stdio.cli",
            "hub",
            "start",
            "--daemon",
            "--config",
            str(cfg_file),
        ]
        res_start = subprocess.run(cmd_start, capture_output=True, text=True, timeout=15, stdin=subprocess.DEVNULL)
        assert res_start.returncode == 0, f"Hub start failed: {res_start.stderr}"

        # Wait for sync file to be written by child
        deadline = time.time() + 10.0
        while time.time() < deadline:
            if sync_file.exists() and sync_file.stat().st_size > 0:
                try:
                    tree_data = json.loads(sync_file.read_text(encoding="utf-8"))
                    child_pid = tree_data["child_pid"]
                    gc_pid = tree_data["gc_pid"]
                    break
                except Exception:
                    pass
            time.sleep(0.2)

        assert child_pid is not None, "Child process failed to write sync file"
        assert gc_pid is not None, "Grandchild process failed to start"

        # Query hub PID via status --json
        cmd_status = [sys.executable, "-m", "mcp_win_stdio.cli", "hub", "status", "--json", "--config", str(cfg_file)]
        res_status = subprocess.run(cmd_status, capture_output=True, text=True, timeout=5, stdin=subprocess.DEVNULL)
        assert res_status.returncode == 0
        stat_data = json.loads(res_status.stdout)
        assert stat_data["running"] is True
        hub_pid = stat_data["pid"]

        # Confirm all 3 processes are alive in the OS kernel
        assert is_pid_alive(hub_pid) is True
        assert is_pid_alive(child_pid) is True
        assert is_pid_alive(gc_pid) is True

        # Now execute force-stop on the hub daemon: mws hub stop --force
        cmd_stop = [sys.executable, "-m", "mcp_win_stdio.cli", "hub", "stop", "--force", "--timeout", "3.0"]
        res_stop = subprocess.run(cmd_stop, capture_output=True, text=True, timeout=10, stdin=subprocess.DEVNULL)
        assert res_stop.returncode == 0, f"Hub stop failed: {res_stop.stderr}"

        # Verify kernel teardown of ALL 3 processes within bounded timeout
        deadline = time.time() + 6.0
        hub_dead = False
        child_dead = False
        gc_dead = False

        while time.time() < deadline:
            if not is_pid_alive(hub_pid):
                hub_dead = True
            if not is_pid_alive(child_pid):
                child_dead = True
            if not is_pid_alive(gc_pid):
                gc_dead = True
            if hub_dead and child_dead and gc_dead:
                break
            time.sleep(0.1)

        assert hub_dead is True, f"Hub daemon PID {hub_pid} survived force stop!"
        assert child_dead is True, f"Supervised MCP child PID {child_pid} survived hub force stop!"
        assert gc_dead is True, f"Grandchild PID {gc_pid} survived hub force stop!"

    finally:
        for p in (hub_pid, child_pid, gc_pid):
            if p and is_pid_alive(p):
                try:
                    subprocess.run(["taskkill", "/F", "/PID", str(p)], capture_output=True)
                except Exception:
                    pass


def test_corrupted_metadata_with_live_pid_preserves_evidence(tmp_path):
    """
    If hub_instance.json contains malformed/truncated JSON but the text still contains
    a live PID (and matching creation time), is_running() must never delete the file
    and acquire() must reject starting a duplicate instance.
    """
    meta_file = tmp_path / "hub_instance.json"
    mgr = HubInstanceManager(metadata_path=meta_file)

    dummy = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    try:
        live_pid = dummy.pid
        live_ct = get_process_creation_time(live_pid)
        assert is_pid_alive(live_pid) is True

        # Write truncated/corrupt JSON containing the live PID
        corrupted_content = f'{{"pid": {live_pid}, "creation_time": {live_ct or 0}, "broken_syntax": '
        meta_file.write_text(corrupted_content, encoding="utf-8")

        running, meta = mgr.is_running()
        assert running is False
        assert meta is not None
        assert meta.pid == live_pid
        assert meta_file.is_file() is True

        # Attempting to acquire must fail to prevent duplicate hub launch
        with pytest.raises(RuntimeError, match=f"MCP Hub is already running \\(PID {live_pid}\\)"):
            mgr.acquire(pid=os.getpid(), pipe_name=r"\\.\pipe\mws-conflict-pipe")

    finally:
        try:
            dummy.kill()
            dummy.wait(timeout=2.0)
        except Exception:
            pass


def test_corrupted_metadata_with_dead_pid_purged(tmp_path):
    """
    If hub_instance.json is corrupted/empty and belongs to a dead PID (or has no salvageable PID),
    is_running() must purge the corrupted file under the interprocess lock, allowing subsequent acquire().
    """
    meta_file = tmp_path / "hub_instance.json"
    mgr = HubInstanceManager(metadata_path=meta_file)

    proc = subprocess.Popen([sys.executable, "-c", "import sys; sys.exit(0)"])
    proc.wait()
    dead_pid = proc.pid
    assert is_pid_alive(dead_pid) is False

    # Case 1: Corrupted JSON with dead PID
    meta_file.write_text(f'{{"pid": {dead_pid}, "creation_time": 12345, "broken": ', encoding="utf-8")
    running, meta = mgr.is_running()
    assert running is False
    assert meta is None
    assert meta_file.exists() is False

    # Case 2: Completely empty file
    meta_file.write_text("", encoding="utf-8")
    running, meta = mgr.is_running()
    assert running is False
    assert meta is None
    assert meta_file.exists() is False

    # Subsequent acquire must succeed cleanly
    my_pid = os.getpid()
    new_meta = mgr.acquire(pid=my_pid, pipe_name=r"\\.\pipe\mws-clean-pipe")
    assert new_meta.pid == my_pid
    assert meta_file.is_file() is True
    mgr.release()


def test_port_collision_aborts_startup_and_rolls_back_completely(tmp_path):
    """
    Verify that if the HTTP Bridge port is already in use, cmd_hub_start unwinds
    completely: control server is stopped, orchestrator is stopped, instance metadata
    is released/unlinked, and process exits with code 1.
    """
    import argparse
    import socket

    from mcp_win_stdio.cli import cmd_hub_start

    # Bind a socket on 127.0.0.1 to occupy a port
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    sock.listen(1)
    port = sock.getsockname()[1]

    cfg_file = tmp_path / "hub_collision.yaml"
    cfg_file.write_text(
        f"""schema_version: '1.0'
runtime:
  http_bridge:
    port: {port}
""",
        encoding="utf-8",
    )

    args = argparse.Namespace(
        config=str(cfg_file),
        port=port,
        host="127.0.0.1",
        daemon=False,
        foreground=True,
    )

    try:
        with patch("mcp_win_stdio.core.hub.control.USER_DIR", tmp_path):
            with patch("mcp_win_stdio.cli.USER_DIR", tmp_path):
                with pytest.raises(SystemExit) as exc_info:
                    cmd_hub_start(args)

                assert exc_info.value.code == 1

        # Check metadata file is unlinked (rolled back)
        meta_file = tmp_path / "hub_instance.json"
        assert meta_file.exists() is False

    finally:
        sock.close()


def test_cli_hub_restart_aborts_when_existing_hub_unresponsive(tmp_path):
    """
    Verify that 'mws hub restart' (with force=False) aborts with status 1 if the
    existing hub process is alive but fails to stop, and NEVER launches a replacement hub.
    """
    import argparse

    from mcp_win_stdio.cli import cmd_hub_restart
    from mcp_win_stdio.core.hub.security import write_secure_json_file

    meta_file = tmp_path / "hub_instance.json"
    dummy = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])

    try:
        live_pid = dummy.pid
        live_ct = get_process_creation_time(live_pid)

        # Write metadata pointing to dummy process with an inactive control pipe
        meta_data = HubInstanceMetadata(
            pid=live_pid,
            started_at=time.time() - 50,
            pipe_name=rf"\\.\pipe\mws-unresponsive-pipe-{time.time_ns()}",
            authkey_hex="abcdef0123456789abcdef0123456789",
            config_path=None,
            config_source="default",
            http_host="127.0.0.1",
            http_port=8080,
            creation_time=live_ct,
        )
        write_secure_json_file(meta_file, meta_data.to_dict())

        args = argparse.Namespace(
            config=None,
            force=False,
            timeout=1.0,
        )

        started = []

        def mock_start(a):
            started.append(True)

        with patch("mcp_win_stdio.core.hub.control.USER_DIR", tmp_path):
            with patch("mcp_win_stdio.cli.USER_DIR", tmp_path):
                with patch("mcp_win_stdio.cli.cmd_hub_start", side_effect=mock_start):
                    with pytest.raises(SystemExit) as exc_info:
                        cmd_hub_restart(args)

                    assert exc_info.value.code == 1

        # Assert no replacement was spawned!
        assert len(started) == 0
        # Dummy process must remain alive (not killed without --force)
        assert is_pid_alive(live_pid) is True
        # Metadata must still be preserved
        assert meta_file.is_file() is True

    finally:
        try:
            dummy.kill()
            dummy.wait(timeout=2.0)
        except Exception:
            pass
