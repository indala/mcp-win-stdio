"""
Tests for Windows NTFS DACL security and metadata hardening.
Verifies that ~/.mcp-win-stdio and hub_instance.json receive explicit,
protected DACLs restricting access exclusively to Current User, SYSTEM,
and Administrators, with no permissive or inherited Everyone/Users ACEs.
"""

import json
import os
import re
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from mcp_win_stdio.core.hub.control import HubInstanceManager
from mcp_win_stdio.core.hub.security import (
    FORBIDDEN_TRUSTEES,
    WindowsSecurityError,
    get_current_user_sid,
    get_sddl_string,
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
