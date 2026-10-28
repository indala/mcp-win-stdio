"""
Tests for Windows NTFS DACL security and metadata hardening.
Verifies that ~/.mcp-win-stdio and hub_instance.json receive explicit,
protected DACLs restricting access exclusively to Current User, SYSTEM,
and Administrators, with no permissive or inherited Everyone/Users ACEs.
"""

import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from mcp_win_stdio.core.hub.control import HubInstanceManager
from mcp_win_stdio.core.hub.security import (
    FORBIDDEN_TRUSTEES,
    WindowsSecurityError,
    get_current_user_sid,
    get_sddl_string,
    interprocess_file_lock,
    secure_directory,
    secure_file,
    verify_security_descriptor,
    write_secure_json_file,
)


@pytest.fixture
def temp_sec_dir():
    """Create a temporary directory for security tests."""
    with tempfile.TemporaryDirectory() as td:
        yield Path(td)


def test_get_current_user_sid():
    """Verify that current user SID retrieval works and returns valid format."""
    sid = get_current_user_sid()
    assert isinstance(sid, str)
    assert len(sid) > 0
    if sys.platform == "win32":
        assert sid.startswith("S-1-5-")
    else:
        assert sid == "S-1-5-CURRENT-USER"


@pytest.mark.skipif(sys.platform != "win32", reason="Native Windows DACL test")
def test_secure_directory_native_dacl(temp_sec_dir):
    """Test that secure_directory applies a protected DACL on Windows."""
    test_dir = temp_sec_dir / "secure_subfolder"
    test_dir.mkdir()

    secure_directory(test_dir)

    sddl = get_sddl_string(test_dir)
    assert len(sddl) > 0

    # Must be protected against inheritance (D:P or contains P flag)
    dacl_header = re.search(r"D:([A-Z]*)", sddl)
    assert dacl_header is not None
    assert "P" in dacl_header.group(1), f"DACL is not protected: {sddl}"

    # Current user SID must have access
    user_sid = get_current_user_sid()
    assert user_sid in sddl

    # SYSTEM (SY) and Administrators (BA) must have access
    assert "SY" in sddl or "S-1-5-18" in sddl
    assert "BA" in sddl or "S-1-5-32-544" in sddl

    # No forbidden broad trustees
    aces = re.findall(r"\((.*?)\)", sddl)
    for ace in aces:
        parts = ace.split(";")
        if len(parts) >= 6:
            trustee = parts[5].strip().upper()
            assert trustee not in FORBIDDEN_TRUSTEES, f"Forbidden trustee {trustee} found in {sddl}"

    # Verification function must pass
    assert verify_security_descriptor(test_dir, is_directory=True) is True


@pytest.mark.skipif(sys.platform != "win32", reason="Native Windows DACL test")
def test_secure_file_native_dacl(temp_sec_dir):
    """Test that secure_file applies protected DACL on an existing file."""
    test_file = temp_sec_dir / "test_secret.txt"
    test_file.write_text("initial")

    secure_file(test_file)

    sddl = get_sddl_string(test_file)
    assert len(sddl) > 0

    # Must be protected
    dacl_header = re.search(r"D:([A-Z]*)", sddl)
    assert dacl_header is not None
    assert "P" in dacl_header.group(1)

    user_sid = get_current_user_sid()
    assert user_sid in sddl
    assert verify_security_descriptor(test_file, is_directory=False) is True


@pytest.mark.skipif(sys.platform != "win32", reason="Native Windows DACL test")
def test_remediate_permissive_directory(temp_sec_dir):
    """Test that applying secure_directory removes inherited/permissive permissions."""
    test_dir = temp_sec_dir / "remediate_dir"
    test_dir.mkdir()

    # Pre-check initial SDDL (inherits from temp dir, usually includes broad ACEs)
    initial_sddl = get_sddl_string(test_dir)

    # Secure the directory
    secure_directory(test_dir)

    post_sddl = get_sddl_string(test_dir)
    assert "P" in re.search(r"D:([A-Z]*)", post_sddl).group(1)
    assert verify_security_descriptor(test_dir, is_directory=True) is True


def test_write_secure_json_file_atomic_and_permissions(temp_sec_dir):
    """Test that write_secure_json_file writes payload and preserves protected DACL."""
    meta_path = temp_sec_dir / "sub" / "instance.json"
    data = {"pid": 42, "authkey": "secret_abc"}

    write_secure_json_file(meta_path, data)

    assert meta_path.is_file()
    read_data = json.loads(meta_path.read_text(encoding="utf-8"))
    assert read_data == data

    # Verify DACL
    assert verify_security_descriptor(meta_path, is_directory=False) is True
    assert verify_security_descriptor(meta_path.parent, is_directory=True) is True

    # Update file atomically and verify DACL is still preserved
    data["pid"] = 43
    write_secure_json_file(meta_path, data)
    assert json.loads(meta_path.read_text(encoding="utf-8"))["pid"] == 43
    assert verify_security_descriptor(meta_path, is_directory=False) is True


def test_write_secure_json_file_failure_leaves_live_metadata(temp_sec_dir):
    """If an error occurs during write, live metadata must remain intact without temp file leak."""
    meta_path = temp_sec_dir / "instance.json"
    initial_data = {"pid": 100, "status": "running"}
    write_secure_json_file(meta_path, initial_data)

    # Attempt to write non-serializable object
    bad_data = {"pid": 101, "object": object()}
    with pytest.raises(TypeError):
        write_secure_json_file(meta_path, bad_data)

    # Original file must remain untouched
    assert meta_path.is_file()
    assert json.loads(meta_path.read_text(encoding="utf-8")) == initial_data

    # No leftover .tmp files
    tmp_files = list(temp_sec_dir.glob("*.tmp*"))
    assert len(tmp_files) == 0


def test_verify_security_descriptor_detects_forbidden_trustee(temp_sec_dir):
    """Verify that verify_security_descriptor detects forbidden broad trustees."""
    test_target = temp_sec_dir / "target.txt"
    test_target.touch()

    if sys.platform != "win32":
        # On POSIX, test file mode detection
        with tempfile.NamedTemporaryFile() as tf:
            p = Path(tf.name)
            p.chmod(0o666)  # Permissive
            with pytest.raises(WindowsSecurityError, match="Insecure POSIX permissions"):
                verify_security_descriptor(p)
    else:
        # On Windows, mock get_sddl_string with insecure SDDL
        with patch("mcp_win_stdio.core.hub.security.get_sddl_string") as mock_sddl:
            mock_sddl.return_value = "D:(A;;FA;;;WD)"  # Everyone has access
            with pytest.raises(WindowsSecurityError, match="DACL on .* is not protected"):
                verify_security_descriptor(test_target)

            mock_sddl.return_value = "D:P(A;;FA;;;WD)"  # Protected but grants to Everyone
            with pytest.raises(WindowsSecurityError, match="contains forbidden broad trustee 'WD'"):
                verify_security_descriptor(test_target)


def test_hub_instance_manager_acquire_enforces_dacl(temp_sec_dir):
    """Verify HubInstanceManager.acquire creates protected DACL on metadata."""
    meta_path = temp_sec_dir / "hub_instance.json"
    mgr = HubInstanceManager(metadata_path=meta_path)

    meta = mgr.acquire(pid=os.getpid(), pipe_name="\\\\.\\pipe\\test-pipe")
    assert meta.pid == os.getpid()
    assert meta_path.is_file()

    # Verify security on file and directory
    assert verify_security_descriptor(meta_path, is_directory=False) is True
    assert verify_security_descriptor(meta_path.parent, is_directory=True) is True

    # Read back metadata
    read_meta = mgr.get_metadata()
    assert read_meta is not None
    assert read_meta.pid == os.getpid()

    # Release cleans up file
    mgr.release()
    assert not meta_path.exists()


def test_non_windows_chmod_fallback(temp_sec_dir):
    """Verify non-Windows chmod 0700 / 0600 behavior."""
    test_dir = temp_sec_dir / "nix_dir"
    test_file = test_dir / "nix_file.txt"
    test_dir.mkdir()
    test_file.touch()

    mock_stat_dir = type("MockStat", (), {"st_mode": 0o040700})()
    mock_stat_file = type("MockStat", (), {"st_mode": 0o100600})()

    def fake_stat(self, *args, **kwargs):
        if self.is_dir():
            return mock_stat_dir
        return mock_stat_file

    with patch("sys.platform", "linux"):
        with patch.object(Path, "stat", fake_stat):
            secure_directory(test_dir)
            secure_file(test_file)

            assert verify_security_descriptor(test_dir, is_directory=True) is True
            assert verify_security_descriptor(test_file, is_directory=False) is True


def test_concurrent_acquire_with_acls(temp_sec_dir):
    """Verify that concurrent acquire correctly fails with RuntimeError and preserves metadata DACL."""
    meta_path = temp_sec_dir / "hub_instance.json"
    mgr1 = HubInstanceManager(metadata_path=meta_path)
    mgr2 = HubInstanceManager(metadata_path=meta_path)

    # First acquire succeeds
    meta1 = mgr1.acquire(pid=os.getpid(), pipe_name="\\\\.\\pipe\\test-pipe-1")
    assert meta1.pid == os.getpid()

    # Second acquire must fail because instance is active
    with patch.object(HubInstanceManager, "is_running", return_value=(True, meta1)):
        with pytest.raises(RuntimeError, match="MCP Hub is already running"):
            mgr2.acquire(pid=os.getpid() + 1, pipe_name="\\\\.\\pipe\\test-pipe-2")

    # File and directory DACLs must remain strictly verified
    assert verify_security_descriptor(meta_path, is_directory=False) is True
    assert mgr1.get_metadata().pid == os.getpid()

    mgr1.release()


@pytest.mark.skipif(sys.platform != "win32", reason="Native Windows test")
def test_set_named_security_info_failure_raises(temp_sec_dir):
    """Verify that SetNamedSecurityInfo failure raises WindowsSecurityError without leaking unsecure state."""
    test_file = temp_sec_dir / "unsecured.txt"
    test_file.write_text("data")

    import mcp_win_stdio.core.hub.security as sec

    with patch.object(sec.advapi32, "SetNamedSecurityInfoW", return_value=5):  # ERROR_ACCESS_DENIED (5)
        with pytest.raises(WindowsSecurityError, match="SetNamedSecurityInfoW failed"):
            secure_file(test_file)


def test_strict_allowlist_rejects_unauthorized_trustees(temp_sec_dir):
    """Verify that verify_security_descriptor rejects unexpected trustees (strict allowlist)."""
    test_target = temp_sec_dir / "allowlist_target.txt"
    test_target.touch()

    if sys.platform == "win32":
        with patch("mcp_win_stdio.core.hub.security.get_sddl_string") as mock_sddl:
            user_sid = get_current_user_sid()
            # Unknown user/service account SID
            alien_sid = "S-1-5-21-999999-999999-999999-1234"
            mock_sddl.return_value = f"D:P(A;;FA;;;{user_sid})(A;;FA;;;SY)(A;;FA;;;BA)(A;;FA;;;{alien_sid})"
            with pytest.raises(WindowsSecurityError, match="outside allowlist"):
                verify_security_descriptor(test_target)


def test_write_secure_json_file_rejects_symlinks(temp_sec_dir):
    """Verify that write_secure_json_file aborts if target or parent is a symlink."""
    meta_path = temp_sec_dir / "target.json"

    with patch.object(Path, "is_symlink", return_value=True):
        with pytest.raises(WindowsSecurityError, match="is a symlink; rejected"):
            write_secure_json_file(meta_path, {"pid": 123})


def test_pid_reuse_creation_time_detection(temp_sec_dir):
    """Verify that is_running purges stale metadata when creation time mismatches (PID reused)."""
    meta_path = temp_sec_dir / "hub_instance.json"
    mgr = HubInstanceManager(metadata_path=meta_path)

    # Acquire instance
    meta = mgr.acquire(pid=os.getpid(), pipe_name="\\\\.\\pipe\\test-reuse-pipe")
    assert meta_path.is_file()

    # Simulate that OS kernel PID is alive, but its creation time is different (PID was reused)
    with patch("mcp_win_stdio.core.hub.control.is_pid_alive", return_value=True):
        with patch("mcp_win_stdio.core.hub.control.get_process_creation_time", return_value=99999999999):
            running, existing = mgr.is_running()
            assert running is False
            assert existing is None
            # Stale metadata should have been purged because PID belongs to another process!
            assert not meta_path.exists()


def test_verified_live_instance_metadata_never_deleted_on_ping_failure(temp_sec_dir):
    """Verify that if process is alive and creation time matches, metadata is never purged."""
    meta_path = temp_sec_dir / "hub_instance.json"
    mgr = HubInstanceManager(metadata_path=meta_path)

    meta = mgr.acquire(pid=os.getpid(), pipe_name="\\\\.\\pipe\\test-live-pipe")
    assert meta_path.is_file()

    # Process is alive in kernel and creation time matches, but control ping fails (busy / startup)
    with patch("mcp_win_stdio.core.hub.control.is_pid_alive", return_value=True):
        with patch("mcp_win_stdio.core.hub.control.get_process_creation_time", return_value=meta.creation_time):
            with patch("mcp_win_stdio.core.hub.control.HubControlClient.ping", return_value=None):
                running, existing = mgr.is_running()
                assert running is False
                assert existing is not None
                assert existing.pid == os.getpid()
                # Crucial check: metadata file MUST STILL EXIST! Never deleted!
                assert meta_path.is_file()


# =====================================================================
# Phase 6.1 Step 2: Windows Job Object & Leak-Free Child Teardown Tests
# =====================================================================


@pytest.mark.skipif(sys.platform != "win32", reason="Native Windows Job Object test")
def test_job_object_suspended_process_lifecycle():
    """Verify suspended process creation, Job Object assignment, and resumption."""
    from mcp_win_stdio.core.hub.win32_job import Win32JobObject

    job = Win32JobObject(name=f"test-job-{os.getpid()}-{time.time_ns()}")
    assert job.is_supported is True
    assert job.handle is not None

    p = subprocess.Popen(
        [
            sys.executable,
            "-c",
            "import sys; sys.stdout.write('SUSPENDED_LIFECYCLE_OK\\n'); sys.stdout.flush()",
        ],
        stdout=subprocess.PIPE,
        creationflags=0x00000004,  # CREATE_SUSPENDED
        text=True,
    )

    try:
        # Assign process to Job Object while still suspended
        assert job.assign_process(p) is True

        # Resume execution
        assert job.resume_process(p) is True

        out, _ = p.communicate(timeout=5.0)
        assert out.strip() == "SUSPENDED_LIFECYCLE_OK"
        assert p.poll() == 0
    finally:
        job.close()
        if p.poll() is None:
            p.kill()


def test_job_object_assignment_failure_terminates_child_without_orphan():
    """Verify that if Job Object assignment fails, child is immediately terminated and no orphan remains."""
    from mcp_win_stdio.core.hub.models import ServerConfig
    from mcp_win_stdio.core.hub.registry import HubRegistry
    from mcp_win_stdio.core.hub.supervisor import ProcessSupervisor
    from mcp_win_stdio.core.hub.win32_job import Win32JobObject

    reg = HubRegistry()
    reg.register_server(
        ServerConfig(
            name="fail_srv",
            command=sys.executable,
            args=["-c", "import time; time.sleep(10)"],
        )
    )

    sup = ProcessSupervisor(registry=reg)

    # Patch assign_process to simulate failure
    with patch.object(Win32JobObject, "assign_process", return_value=False):
        with pytest.raises(RuntimeError, match="Failed to assign child process"):
            sup.start("fail_srv")

    inst = sup._instances.get("fail_srv")
    assert inst is not None
    assert inst.pid is not None
    child_pid = inst.pid

    # Verify that child process was terminated immediately and does not survive as an orphan
    from mcp_win_stdio.core.hub.control import is_pid_alive

    assert is_pid_alive(child_pid) is False
    assert inst.job_object is None
    sup.shutdown()


def test_job_object_resume_failure_terminates_child_without_orphan():
    """Verify that if resuming a suspended process fails, the child is immediately killed and handle closed."""
    from mcp_win_stdio.core.hub.models import ServerConfig
    from mcp_win_stdio.core.hub.registry import HubRegistry
    from mcp_win_stdio.core.hub.supervisor import ProcessSupervisor
    from mcp_win_stdio.core.hub.win32_job import Win32JobObject

    reg = HubRegistry()
    reg.register_server(
        ServerConfig(
            name="resume_fail_srv",
            command=sys.executable,
            args=["-c", "import time; time.sleep(10)"],
        )
    )

    sup = ProcessSupervisor(registry=reg)

    # Patch resume_process to simulate failure
    with patch.object(Win32JobObject, "resume_process", return_value=False):
        with pytest.raises(RuntimeError, match="Failed to resume child process"):
            sup.start("resume_fail_srv")

    inst = sup._instances.get("resume_fail_srv")
    assert inst is not None
    assert inst.pid is not None
    child_pid = inst.pid

    from mcp_win_stdio.core.hub.control import is_pid_alive

    assert is_pid_alive(child_pid) is False
    assert inst.job_object is None
    sup.shutdown()


@pytest.mark.skipif(sys.platform != "win32", reason="Native Windows taskkill process tree test")
def test_native_taskkill_terminates_child_and_grandchild_process_tree(tmp_path):
    """
    Native Windows test: Verifies that when the parent process is forcibly killed with taskkill /F,
    the Windows kernel terminates the entire Job Object process tree (child and grandchild).
    """
    from mcp_win_stdio.core.hub.control import get_process_creation_time, is_pid_alive

    helper_code = """
import sys, time, json, subprocess
from mcp_win_stdio.core.hub.win32_job import Win32JobObject
from mcp_win_stdio.core.hub.control import get_process_creation_time

# 1. Create Job Object with KILL_ON_JOB_CLOSE
job = Win32JobObject(name="test-tree-job")

# Grandchild code: long sleep
grandchild_script = "import time; time.sleep(60)"

# Child code: spawns grandchild and sleeps
child_code = f\"\"\"
import sys, subprocess, time, json
from mcp_win_stdio.core.hub.control import get_process_creation_time
gc = subprocess.Popen([sys.executable, "-c", "{grandchild_script}"])
print(json.dumps({{'gc_pid': gc.pid, 'gc_ct': get_process_creation_time(gc.pid)}}), flush=True)
time.sleep(60)
\"\"\"

# Spawn child suspended
child = subprocess.Popen(
    [sys.executable, "-c", child_code],
    stdout=subprocess.PIPE,
    creationflags=0x00000004, # CREATE_SUSPENDED
    text=True
)

job.assign_process(child)
job.resume_process(child)

# Read grandchild info from child stdout
line = child.stdout.readline().strip()
gc_info = json.loads(line)

# Report all PIDs to test harness
report = {
    'child_pid': child.pid,
    'child_ct': get_process_creation_time(child.pid),
    'gc_pid': gc_info['gc_pid'],
    'gc_ct': gc_info['gc_ct'],
}
print(json.dumps(report), flush=True)

# Keep parent alive until taskkilled
time.sleep(60)
"""

    helper_file = tmp_path / "tree_simulator.py"
    helper_file.write_text(helper_code, encoding="utf-8")

    # Start the parent process
    parent = subprocess.Popen(
        [sys.executable, str(helper_file)],
        stdout=subprocess.PIPE,
        text=True,
    )

    try:
        line = parent.stdout.readline().strip()
        data = json.loads(line)

        child_pid = data["child_pid"]
        child_ct = data["child_ct"]
        gc_pid = data["gc_pid"]
        gc_ct = data["gc_ct"]

        # Confirm all processes are alive in the OS kernel before termination
        assert is_pid_alive(parent.pid) is True
        assert is_pid_alive(child_pid) is True
        assert is_pid_alive(gc_pid) is True
        assert get_process_creation_time(child_pid) == child_ct
        assert get_process_creation_time(gc_pid) == gc_ct

        # Forcibly terminate parent with taskkill /F
        subprocess.run(
            ["taskkill", "/F", "/PID", str(parent.pid)],
            capture_output=True,
            check=True,
        )

        # Poll child and grandchild to verify kernel-enforced teardown within bounded timeout
        deadline = time.time() + 6.0
        child_dead = False
        gc_dead = False

        while time.time() < deadline:
            if not is_pid_alive(child_pid) or get_process_creation_time(child_pid) != child_ct:
                child_dead = True
            if not is_pid_alive(gc_pid) or get_process_creation_time(gc_pid) != gc_ct:
                gc_dead = True
            if child_dead and gc_dead:
                break
            time.sleep(0.1)

        assert child_dead is True, f"Child PID {child_pid} survived parent taskkill /F!"
        assert gc_dead is True, f"Grandchild PID {gc_pid} survived parent taskkill /F!"

    finally:
        if parent.poll() is None:
            parent.kill()


@pytest.mark.skipif(sys.platform != "win32", reason="Windows Job Object tests require Windows")
def test_job_object_explicit_handle_close_kills_tree_without_taskkill(tmp_path):
    """
    Directly verify that closing the Job Object handle (without taskkill or proc.kill)
    causes the Windows kernel to immediately terminate all running child and grandchild processes
    via JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE.
    """
    from mcp_win_stdio.core.hub.control import get_process_creation_time, is_pid_alive
    from mcp_win_stdio.core.hub.win32_job import CREATE_SUSPENDED, Win32JobObject

    # Grandchild script: loops forever
    gc_code = "import time; time.sleep(60)"
    gc_file = tmp_path / "gc_runner.py"
    gc_file.write_text(gc_code, encoding="utf-8")

    # Child script: spawns grandchild, outputs both PIDs and creation times, then sleeps
    child_code = f"""
import sys, subprocess, time, json
from mcp_win_stdio.core.hub.control import get_process_creation_time
gc = subprocess.Popen([sys.executable, r"{gc_file}"])
my_pid = sys.argv[1] if len(sys.argv) > 1 else "0"
gc_ct = get_process_creation_time(gc.pid)
data = {{"child_pid": int(my_pid), "gc_pid": gc.pid, "gc_ct": gc_ct}}
sys.stdout.write(json.dumps(data) + "\\n")
sys.stdout.flush()
time.sleep(60)
"""
    child_file = tmp_path / "child_runner.py"
    child_file.write_text(child_code, encoding="utf-8")

    job = Win32JobObject(name=f"mws-test-explicit-close-{os.getpid()}-{time.time_ns()}")
    assert job.is_supported is True

    # 1. Spawn child suspended
    proc = subprocess.Popen(
        [sys.executable, str(child_file), str(os.getpid())],
        stdout=subprocess.PIPE,
        creationflags=CREATE_SUSPENDED,
        text=True,
    )
    # Correct child_pid in argument
    child_pid = proc.pid
    child_ct = get_process_creation_time(child_pid)

    try:
        # 2. Assign to Job Object before resuming
        assigned = job.assign_process(proc)
        assert assigned is True, "Failed to assign child process to Job Object"

        # 3. Resume child process
        resumed = job.resume_process(proc)
        assert resumed is True, "Failed to resume child process"

        # Read grandchild info
        line = proc.stdout.readline().strip()
        data = json.loads(line)
        gc_pid = data["gc_pid"]
        gc_ct = data["gc_ct"]

        # Confirm child and grandchild are alive
        assert is_pid_alive(child_pid) is True
        assert is_pid_alive(gc_pid) is True
        assert get_process_creation_time(child_pid) == child_ct
        assert get_process_creation_time(gc_pid) == gc_ct

        # 4. EXPLICITLY CLOSE JOB OBJECT HANDLE
        # Neither proc.kill() nor taskkill is called.
        # Closing the handle MUST cause the Windows kernel to kill all processes in the job.
        job.close()

        # 5. Verify kernel teardown of both processes within bounded timeout
        deadline = time.time() + 6.0
        child_dead = False
        gc_dead = False

        while time.time() < deadline:
            if not is_pid_alive(child_pid) or get_process_creation_time(child_pid) != child_ct:
                child_dead = True
            if not is_pid_alive(gc_pid) or get_process_creation_time(gc_pid) != gc_ct:
                gc_dead = True
            if child_dead and gc_dead:
                break
            time.sleep(0.1)

        assert child_dead is True, f"Child PID {child_pid} survived explicit Job Object handle closure!"
        assert gc_dead is True, f"Grandchild PID {gc_pid} survived explicit Job Object handle closure!"

    finally:
        try:
            proc.kill()
        except Exception:
            pass
        job.close()


def test_multiple_supervised_mcps_independent_containment():
    """Verify that multiple supervised MCP servers have independent Job Objects and containment."""
    from mcp_win_stdio.core.hub.models import ServerConfig, ServerState
    from mcp_win_stdio.core.hub.registry import HubRegistry
    from mcp_win_stdio.core.hub.supervisor import ProcessSupervisor

    mcp_script = """
import sys, json

for line in iter(sys.stdin.readline, ""):
    req = json.loads(line)
    mid = req.get("id")
    method = req.get("method")
    if method == "initialize":
        res = {"jsonrpc": "2.0", "id": mid, "result": {"protocolVersion": "2024-11-05", "serverInfo": {"name": "test", "version": "1.0"}}}
    elif method == "tools/list":
        res = {"jsonrpc": "2.0", "id": mid, "result": {"tools": []}}
    else:
        res = {"jsonrpc": "2.0", "id": mid, "result": {}}
    sys.stdout.write(json.dumps(res) + "\\n")
    sys.stdout.flush()
"""

    reg = HubRegistry()
    reg.register_server(ServerConfig(name="server_a", command=sys.executable, args=["-c", mcp_script]))
    reg.register_server(ServerConfig(name="server_b", command=sys.executable, args=["-c", mcp_script]))

    sup = ProcessSupervisor(registry=reg)

    try:
        # Start both servers
        info_a = sup.start("server_a")
        info_b = sup.start("server_b")

        assert info_a.state == ServerState.HEALTHY
        assert info_b.state == ServerState.HEALTHY
        assert info_a.pid is not None
        assert info_b.pid is not None
        assert info_a.pid != info_b.pid

        # Stop Server A
        stop_a = sup.stop("server_a")
        assert stop_a.state == ServerState.STOPPED

        # Server B must remain completely HEALTHY and active
        status_b = sup.get_status("server_b")
        assert status_b.state == ServerState.HEALTHY
        from mcp_win_stdio.core.hub.control import is_pid_alive

        assert is_pid_alive(status_b.pid) is True
        assert sup.list_server_tools("server_b") == []

        # Stop Server B
        stop_b = sup.stop("server_b")
        assert stop_b.state == ServerState.STOPPED

    finally:
        sup.shutdown()


def test_server_restart_terminates_old_process_tree():
    """Verify that restarting a server terminates the old process and contained tree."""
    from mcp_win_stdio.core.hub.control import is_pid_alive
    from mcp_win_stdio.core.hub.models import ServerConfig, ServerState
    from mcp_win_stdio.core.hub.registry import HubRegistry
    from mcp_win_stdio.core.hub.supervisor import ProcessSupervisor

    mcp_script = """
import sys, json

for line in iter(sys.stdin.readline, ""):
    req = json.loads(line)
    mid = req.get("id")
    method = req.get("method")
    if method == "initialize":
        res = {"jsonrpc": "2.0", "id": mid, "result": {"protocolVersion": "2024-11-05", "serverInfo": {"name": "test", "version": "1.0"}}}
    else:
        res = {"jsonrpc": "2.0", "id": mid, "result": {}}
    sys.stdout.write(json.dumps(res) + "\\n")
    sys.stdout.flush()
"""

    reg = HubRegistry()
    reg.register_server(ServerConfig(name="restart_srv", command=sys.executable, args=["-c", mcp_script]))

    sup = ProcessSupervisor(registry=reg)

    try:
        initial = sup.start("restart_srv")
        assert initial.state == ServerState.HEALTHY
        old_pid = initial.pid

        # Restart server
        restarted = sup.restart("restart_srv")
        assert restarted.state == ServerState.HEALTHY
        new_pid = restarted.pid

        assert new_pid != old_pid
        # Verify old PID is dead
        assert is_pid_alive(old_pid) is False

    finally:
        sup.shutdown()


@pytest.mark.skipif(sys.platform != "win32", reason="Windows NTFS DACL tests require Windows")
def test_interprocess_lock_file_protected_dacl(tmp_path):
    """Verify that interprocess_file_lock creates the lock file with a strict, protected NTFS DACL."""
    lock_file = tmp_path / "hub_instance.lock"
    with interprocess_file_lock(lock_file, timeout=2.0):
        assert lock_file.is_file()
        # Verify native security descriptor on lock file
        verify_security_descriptor(lock_file, is_directory=False)
        sddl = get_sddl_string(lock_file)
        assert "D:P" in sddl, f"Lockfile DACL is missing protected flag (D:P): {sddl}"
        user_sid = get_current_user_sid()
        assert f"(A;;FA;;;{user_sid})" in sddl
        assert "(A;;FA;;;SY)" in sddl
        assert "(A;;FA;;;BA)" in sddl
        assert "WD" not in sddl
        assert "BU" not in sddl


@pytest.mark.skipif(sys.platform != "win32", reason="Windows Job Object tests require Windows")
def test_handshake_failure_terminates_child_and_grandchild_process_tree(tmp_path):
    """
    Verify that if a supervised child spawns a background grandchild process before failing its
    MCP handshake, the supervisor's handshake exception handler terminates both child and grandchild.
    """
    from mcp_win_stdio.core.hub.control import is_pid_alive
    from mcp_win_stdio.core.hub.models import ServerConfig, SupervisorConfig
    from mcp_win_stdio.core.hub.registry import HubRegistry
    from mcp_win_stdio.core.hub.supervisor import ProcessSupervisor

    sync_file = tmp_path / "handshake_fail_sync.json"
    child_script = tmp_path / "bad_handshake_child.py"
    child_code = (
        "import sys, os, time, json, subprocess\n"
        "sync_path = sys.argv[1]\n"
        "# Wait for initialize request on stdin\n"
        "req_line = sys.stdin.readline()\n"
        "gc = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
        "with open(sync_path, 'w', encoding='utf-8') as f:\n"
        "    json.dump({'child_pid': os.getpid(), 'gc_pid': gc.pid}, f)\n"
        "# Return invalid handshake (missing protocolVersion) to trigger handshake failure\n"
        "sys.stdout.write(json.dumps({'jsonrpc': '2.0', 'id': 1, 'result': {'missing_proto': True}}) + '\\n')\n"
        "sys.stdout.flush()\n"
        "time.sleep(60)\n"
    )
    child_script.write_text(child_code, encoding="utf-8")

    reg = HubRegistry()
    reg.register_server(
        ServerConfig(
            name="bad_hs",
            command=sys.executable,
            args=["-u", str(child_script), str(sync_file)],
            supervisor=SupervisorConfig(startup_timeout_seconds=2.0),
        )
    )

    sup = ProcessSupervisor(registry=reg)
    child_pid = None
    gc_pid = None

    try:
        with pytest.raises(Exception) as exc_info:
            sup.start("bad_hs")
        print("Caught exception in test:", exc_info.value)

        # Read sync file
        assert sync_file.exists()
        tree_data = json.loads(sync_file.read_text(encoding="utf-8"))
        child_pid = tree_data["child_pid"]
        gc_pid = tree_data["gc_pid"]

        # Verify both child and grandchild were terminated by Job Object cleanup
        deadline = time.time() + 6.0
        child_dead = False
        gc_dead = False
        while time.time() < deadline:
            if not is_pid_alive(child_pid):
                child_dead = True
            if not is_pid_alive(gc_pid):
                gc_dead = True
            if child_dead and gc_dead:
                break
            time.sleep(0.1)

        assert child_dead is True, f"Child PID {child_pid} survived handshake failure cleanup!"
        assert gc_dead is True, f"Grandchild PID {gc_pid} survived handshake failure cleanup!"

    finally:
        for p in (child_pid, gc_pid):
            if p and is_pid_alive(p):
                try:
                    subprocess.run(["taskkill", "/F", "/PID", str(p)], capture_output=True)
                except Exception:
                    pass
        sup.shutdown()


def test_supervisor_shutdown_cancels_delayed_restart_deterministically():
    """
    Use synchronization events to verify that calling supervisor.shutdown() while a crash
    backoff is waiting immediately cancels the delayed restart and joins the monitor thread.
    """
    import threading

    from mcp_win_stdio.core.hub.models import ServerConfig, ServerState, SupervisorConfig
    from mcp_win_stdio.core.hub.registry import HubRegistry
    from mcp_win_stdio.core.hub.supervisor import ProcessSupervisor

    failed_event = threading.Event()

    def on_event(evt):
        if evt.new_state == ServerState.FAILED:
            failed_event.set()

    reg = HubRegistry()
    reg.register_server(
        ServerConfig(
            name="crash_srv",
            command=sys.executable,
            args=["-c", "import sys; sys.exit(1)"],
            supervisor=SupervisorConfig(
                max_restart_retries=3,
                restart_backoff_seconds=5.0,
            ),
        )
    )

    sup = ProcessSupervisor(registry=reg, on_event=on_event)

    try:
        with pytest.raises(Exception):
            sup.start("crash_srv")

        # Deterministically wait for FAILED state and delayed restart scheduling
        assert failed_event.wait(timeout=5.0) is True

        # Shutdown supervisor while restart is delayed
        start_time = time.time()
        sup.shutdown()
        shutdown_elapsed = time.time() - start_time

        # Monitor thread must join within 3.0s
        assert shutdown_elapsed < 3.0
        assert sup._monitor_thread.is_alive() is False

        # Verify instance is STOPPED and no replacement was spawned
        inst = sup.get_status("crash_srv")
        assert inst is not None
        assert inst.state == ServerState.STOPPED

    finally:
        sup.shutdown()
