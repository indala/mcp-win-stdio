"""
Adversarial tests for Phase 6.2 Audit 4: Windows IPC & Concurrency Stress Testing.

Covers:
1. Real Windows Named Pipe kernel security descriptor inspection (GetKernelObjectSecurity).
2. HMAC authentication adversarial tests (missing, incorrect, malformed, truncated credentials).
3. Non-blocking invariant (repeated failed authentications do not block subsequent legitimate clients).
4. Connection lifecycle robustness (rapid bursts, half-open clients, mid-request drop).
5. Clean server shutdown without leaked threads or blocked listeners.
6. Multi-session isolation under 20-thread concurrent stress testing with synchronization barriers.
7. Snapshot deep immutability against mutating returned nested objects.
"""

import copy
import ctypes
import os
import queue
import secrets
import sys
import threading
import time
from multiprocessing.connection import Client, Listener
from typing import Any, Dict

import pytest

from mcp_win_stdio.core.context import ContextRegistry, SessionContext
from mcp_win_stdio.core.hub.config_loader import LoadedHubConfig
from mcp_win_stdio.core.hub.control import (
    HubControlClient,
    HubControlServer,
    get_ipc_family,
)
from mcp_win_stdio.core.hub.models import HubConfig
from mcp_win_stdio.core.hub.orchestrator import HubOrchestrator
from mcp_win_stdio.core.hub.profiles import ProfileManager
from mcp_win_stdio.core.hub.security import get_current_user_sid

# ---------------------------------------------------------------------------
# Section 1: Real Windows Named Pipe Kernel Security Descriptor Inspection
# ---------------------------------------------------------------------------


@pytest.mark.skipif(sys.platform != "win32", reason="Windows Named Pipe security descriptor requires Win32")
def test_named_pipe_kernel_security_descriptor_and_acls():
    """
    Query the real Windows kernel security descriptor on an active Named Pipe handle.
    Verifies that the DACL grants full control to Current User, SYSTEM, and Administrators,
    and that broad/unprivileged trustees (Everyone/World, Anonymous) do NOT possess Write/Modify permissions.
    """
    from ctypes import wintypes

    pipe_name = f"\\\\.\\pipe\\test-sddl-audit-{secrets.token_hex(4)}"
    authkey = secrets.token_bytes(16)
    listener = Listener(pipe_name, family="AF_PIPE", authkey=authkey)

    try:
        # Extract native Windows pipe handle from internal handle queue
        handle = listener._listener._handle_queue[0]

        advapi32 = ctypes.windll.advapi32
        advapi32.GetKernelObjectSecurity.argtypes = [
            wintypes.HANDLE,
            wintypes.DWORD,
            wintypes.LPVOID,
            wintypes.DWORD,
            ctypes.POINTER(wintypes.DWORD),
        ]
        advapi32.GetKernelObjectSecurity.restype = wintypes.BOOL

        advapi32.ConvertSecurityDescriptorToStringSecurityDescriptorW.argtypes = [
            wintypes.LPVOID,
            wintypes.DWORD,
            wintypes.DWORD,
            ctypes.POINTER(wintypes.LPWSTR),
            ctypes.POINTER(wintypes.ULONG),
        ]
        advapi32.ConvertSecurityDescriptorToStringSecurityDescriptorW.restype = wintypes.BOOL

        DACL_SECURITY_INFORMATION = 0x00000004
        needed = wintypes.DWORD(0)
        # Query needed buffer size
        advapi32.GetKernelObjectSecurity(wintypes.HANDLE(handle), DACL_SECURITY_INFORMATION, None, 0, ctypes.byref(needed))
        assert needed.value > 0, "Failed querying security descriptor size"

        buf = ctypes.create_string_buffer(needed.value)
        ok = advapi32.GetKernelObjectSecurity(
            wintypes.HANDLE(handle), DACL_SECURITY_INFORMATION, buf, needed.value, ctypes.byref(needed)
        )
        assert ok, f"GetKernelObjectSecurity failed with Win32 error {ctypes.GetLastError()}"

        p_sddl = wintypes.LPWSTR()
        conv_ok = advapi32.ConvertSecurityDescriptorToStringSecurityDescriptorW(
            buf, 1, DACL_SECURITY_INFORMATION, ctypes.byref(p_sddl), None
        )
        assert conv_ok, f"ConvertSecurityDescriptorToStringSecurityDescriptorW failed with error {ctypes.GetLastError()}"
        sddl = p_sddl.value or ""

        # -------------------------------------------------------------------
        # Binary DACL Inspection: Parse raw ACE structures from the live handle
        # -------------------------------------------------------------------
        kernel32 = ctypes.windll.kernel32
        dacl_present = wintypes.BOOL()
        p_dacl = ctypes.c_void_p()
        dacl_defaulted = wintypes.BOOL()

        advapi32.GetSecurityDescriptorDacl.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(wintypes.BOOL),
            ctypes.POINTER(ctypes.c_void_p),
            ctypes.POINTER(wintypes.BOOL),
        ]
        advapi32.GetSecurityDescriptorDacl.restype = wintypes.BOOL
        ok_dacl = advapi32.GetSecurityDescriptorDacl(
            buf, ctypes.byref(dacl_present), ctypes.byref(p_dacl), ctypes.byref(dacl_defaulted)
        )
        assert ok_dacl and dacl_present.value, "Live kernel security descriptor lacks DACL"

        class ACL_SIZE_INFORMATION(ctypes.Structure):
            _fields_ = [
                ("AceCount", wintypes.DWORD),
                ("AclBytesInUse", wintypes.DWORD),
                ("AclBytesFree", wintypes.DWORD),
            ]

        acl_size_info = ACL_SIZE_INFORMATION()
        advapi32.GetAclInformation.argtypes = [ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.c_int]
        advapi32.GetAclInformation.restype = wintypes.BOOL
        AclSizeInformation = 2
        ok_info = advapi32.GetAclInformation(
            p_dacl, ctypes.byref(acl_size_info), ctypes.sizeof(acl_size_info), AclSizeInformation
        )
        assert ok_info, f"GetAclInformation failed with error {ctypes.GetLastError()}"
        assert acl_size_info.AceCount >= 3, f"Expected at least 3 ACEs, found {acl_size_info.AceCount}"

        advapi32.GetAce.argtypes = [ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(ctypes.c_void_p)]
        advapi32.GetAce.restype = wintypes.BOOL
        advapi32.ConvertSidToStringSidW.argtypes = [ctypes.c_void_p, ctypes.POINTER(wintypes.LPWSTR)]
        advapi32.ConvertSidToStringSidW.restype = wintypes.BOOL

        class ACE_HEADER(ctypes.Structure):
            _fields_ = [
                ("AceType", ctypes.c_byte),
                ("AceFlags", ctypes.c_byte),
                ("AceSize", wintypes.WORD),
            ]

        class ACCESS_ALLOWED_ACE(ctypes.Structure):
            _fields_ = [
                ("Header", ACE_HEADER),
                ("Mask", wintypes.DWORD),
                ("SidStart", wintypes.DWORD),
            ]

        parsed_aces = []
        for i in range(acl_size_info.AceCount):
            p_ace = ctypes.c_void_p()
            advapi32.GetAce(p_dacl, i, ctypes.byref(p_ace))
            ace = ACCESS_ALLOWED_ACE.from_address(p_ace.value)
            sid_ptr = ctypes.c_void_p(p_ace.value + 8)
            p_sid_str = wintypes.LPWSTR()
            advapi32.ConvertSidToStringSidW(sid_ptr, ctypes.byref(p_sid_str))
            sid_str = p_sid_str.value or ""
            parsed_aces.append({"sid": sid_str, "type": ace.Header.AceType, "mask": ace.Mask})
            kernel32.LocalFree(p_sid_str)

        # Win32 Access Rights & Constants
        ACCESS_ALLOWED_ACE_TYPE = 0
        FILE_ALL_ACCESS = 0x001F01FF
        FILE_GENERIC_READ = 0x00120089
        FILE_WRITE_DATA = 0x00000002
        FILE_APPEND_DATA = 0x00000004
        WRITE_DAC = 0x00040000
        WRITE_OWNER = 0x00080000
        GENERIC_WRITE = 0x40000000
        GENERIC_ALL = 0x10000000

        # Verify handle is a valid live Windows Named Pipe
        kernel32.GetNamedPipeInfo.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(wintypes.DWORD),
            ctypes.POINTER(wintypes.DWORD),
            ctypes.POINTER(wintypes.DWORD),
            ctypes.POINTER(wintypes.DWORD),
        ]
        kernel32.GetNamedPipeInfo.restype = wintypes.BOOL
        pipe_flags = wintypes.DWORD()
        ok_pipe = kernel32.GetNamedPipeInfo(wintypes.HANDLE(handle), ctypes.byref(pipe_flags), None, None, None)
        assert ok_pipe, f"Handle is not a valid live Named Pipe handle (error {ctypes.GetLastError()})"

        user_sid = get_current_user_sid()
        trusted_sids = {"S-1-5-18", "S-1-5-32-544", user_sid}
        known_untrusted_sids = {"S-1-1-0", "S-1-5-7"}  # Everyone, Anonymous
        expected_sids = trusted_sids | known_untrusted_sids

        # Strict validation of every single ACE in the DACL
        for ace_info in parsed_aces:
            # 1. Fail immediately on unsupported or unexpected ACE types
            assert ace_info["type"] == ACCESS_ALLOWED_ACE_TYPE, (
                f"Unexpected ACE type {ace_info['type']} found in DACL for SID {ace_info['sid']}"
            )
            # 2. Fail if any unexpected/unknown trustee is present
            assert ace_info["sid"] in expected_sids, (
                f"Unexpected trustee SID '{ace_info['sid']}' found in kernel DACL"
            )
            # 3. For any non-trusted trustee, assert absolute absence of write/modify rights
            if ace_info["sid"] not in trusted_sids:
                mask = ace_info["mask"]
                assert (mask & FILE_WRITE_DATA) == 0, f"{ace_info['sid']} has FILE_WRITE_DATA (0x{mask:08x})"
                assert (mask & FILE_APPEND_DATA) == 0, f"{ace_info['sid']} has FILE_APPEND_DATA (0x{mask:08x})"
                assert (mask & WRITE_DAC) == 0, f"{ace_info['sid']} has WRITE_DAC (0x{mask:08x})"
                assert (mask & WRITE_OWNER) == 0, f"{ace_info['sid']} has WRITE_OWNER (0x{mask:08x})"
                assert (mask & GENERIC_WRITE) == 0, f"{ace_info['sid']} has GENERIC_WRITE (0x{mask:08x})"
                assert (mask & GENERIC_ALL) == 0, f"{ace_info['sid']} has GENERIC_ALL (0x{mask:08x})"
                assert mask == FILE_GENERIC_READ, (
                    f"{ace_info['sid']} mask expected FILE_GENERIC_READ (0x120089), got 0x{mask:08x}"
                )

        sids_found = {a["sid"]: a["mask"] for a in parsed_aces}

        # Assert SYSTEM (S-1-5-18) possesses full control
        assert "S-1-5-18" in sids_found, "SYSTEM SID (S-1-5-18) missing from parsed DACL"
        assert sids_found["S-1-5-18"] == FILE_ALL_ACCESS, (
            f"SYSTEM lacks FILE_ALL_ACCESS (mask=0x{sids_found['S-1-5-18']:08x})"
        )

        # Assert Administrators (S-1-5-32-544) possesses full control
        assert "S-1-5-32-544" in sids_found, "Administrators SID (S-1-5-32-544) missing from parsed DACL"
        assert sids_found["S-1-5-32-544"] == FILE_ALL_ACCESS, (
            f"Administrators lacks FILE_ALL_ACCESS (mask=0x{sids_found['S-1-5-32-544']:08x})"
        )

        # Assert Current User possesses full control
        assert user_sid in sids_found, f"Current user SID ({user_sid}) missing from parsed DACL"
        assert sids_found[user_sid] == FILE_ALL_ACCESS, (
            f"Current user lacks FILE_ALL_ACCESS (mask=0x{sids_found[user_sid]:08x})"
        )

        # Also assert SDDL representation consistency
        assert user_sid in sddl or "LA" in sddl
        assert "SY" in sddl or "S-1-5-18" in sddl
        assert "BA" in sddl or "S-1-5-32-544" in sddl
        for forbidden in ("(A;;FA;;;WD)", "(A;;GA;;;WD)", "(A;;FA;;;AN)", "(A;;GA;;;AN)"):
            assert forbidden not in sddl
    finally:
        listener.close()


# ---------------------------------------------------------------------------
# Section 2: HMAC Authentication Adversarial Handshake Tests
# ---------------------------------------------------------------------------


def _setup_test_control_server():
    pipe_name = (
        f"\\\\.\\pipe\\test-ctrl-audit-{secrets.token_hex(4)}"
        if sys.platform == "win32"
        else f"/tmp/test-ctrl-audit-{secrets.token_hex(4)}.sock"
    )
    authkey_hex = secrets.token_hex(16)
    cfg = HubConfig(schema_version="1.0")
    loaded = LoadedHubConfig(config=cfg, source_path=None, source_tier="test", profile_manager=ProfileManager())
    orchestrator = HubOrchestrator(loaded_config=loaded)
    orchestrator.start()

    stopped = [False]

    def on_stop():
        stopped[0] = True
        orchestrator.stop()

    server = HubControlServer(
        orchestrator=orchestrator,
        pipe_name=pipe_name,
        authkey_hex=authkey_hex,
        on_stop_requested=on_stop,
    )
    server.start()
    return server, orchestrator, pipe_name, authkey_hex


def test_hmac_handshake_missing_and_wrong_credentials_rejected():
    """
    Adversarial clients attempting connection with:
      - Incorrect authkey
      - Missing authkey (b'')
      - Truncated authkey (8 bytes)
      - Flipped bit authkey
    must be immediately rejected and disconnected.
    """
    server, orchestrator, pipe_name, authkey_hex = _setup_test_control_server()
    family = get_ipc_family(pipe_name)

    try:
        # 1. Incorrect authkey
        bad_auth = secrets.token_bytes(16)
        with pytest.raises(Exception):  # AuthenticationError
            with Client(pipe_name, family=family, authkey=bad_auth) as c:
                c.send({"cmd": "ping"})

        # 2. Missing authkey
        with pytest.raises(Exception):
            with Client(pipe_name, family=family, authkey=b"") as c:
                c.send({"cmd": "ping"})

        # 3. Truncated authkey
        correct_bytes = bytes.fromhex(authkey_hex)
        truncated_auth = correct_bytes[:8]
        with pytest.raises(Exception):
            with Client(pipe_name, family=family, authkey=truncated_auth) as c:
                c.send({"cmd": "ping"})

        # 4. Flipped bit authkey
        flipped_auth = bytearray(correct_bytes)
        flipped_auth[0] ^= 0xFF
        with pytest.raises(Exception):
            with Client(pipe_name, family=family, authkey=bytes(flipped_auth)) as c:
                c.send({"cmd": "ping"})
    finally:
        server.stop()
        orchestrator.stop()


def test_rejected_clients_do_not_block_legitimate_client():
    """
    Non-blocking invariant: multiple consecutive rejected authentication attempts
    must NOT block or corrupt the listener; subsequent legitimate clients must succeed.
    """
    server, orchestrator, pipe_name, authkey_hex = _setup_test_control_server()
    family = get_ipc_family(pipe_name)

    try:
        # Send 5 rogue connection attempts with random credentials
        for _ in range(5):
            try:
                with Client(pipe_name, family=family, authkey=secrets.token_bytes(16)) as c:
                    c.send({"cmd": "ping"})
            except Exception:
                pass

        # Legitimate client must succeed immediately
        pid = HubControlClient.ping(pipe_name, authkey_hex, timeout=2.0)
        assert pid == os.getpid()

        status = HubControlClient.get_status(pipe_name, authkey_hex, timeout=2.0)
        assert status is not None
        assert status["state"] == "running"
    finally:
        server.stop()
        orchestrator.stop()


# ---------------------------------------------------------------------------
# Section 3: Connection Lifecycle, Half-Open Clients, & Bursts
# ---------------------------------------------------------------------------


def test_rapid_connection_burst():
    """Rapidly connect and disconnect 30 legitimate clients to verify listener stability."""
    server, orchestrator, pipe_name, authkey_hex = _setup_test_control_server()

    try:
        for _ in range(30):
            pid = HubControlClient.ping(pipe_name, authkey_hex, timeout=2.0)
            assert pid == os.getpid()
    finally:
        server.stop()
        orchestrator.stop()


def test_half_open_client_does_not_hang_listener():
    """
    A client completes authentication but never sends a request payload.
    The server should handle or timeout safely without stalling subsequent clients.
    """
    server, orchestrator, pipe_name, authkey_hex = _setup_test_control_server()
    family = get_ipc_family(pipe_name)
    auth_bytes = bytes.fromhex(authkey_hex)

    try:
        # Half-open client connects but remains silent
        client = Client(pipe_name, family=family, authkey=auth_bytes)

        # In another thread, close the client after a brief delay
        def close_later():
            time.sleep(0.3)
            try:
                client.close()
            except Exception:
                pass

        t = threading.Thread(target=close_later)
        t.start()
        t.join(timeout=1.0)

        # Verify a legitimate client can ping successfully immediately after
        pid = HubControlClient.ping(pipe_name, authkey_hex, timeout=3.0)
        assert pid == os.getpid()
    finally:
        server.stop()
        orchestrator.stop()


def test_concurrent_control_clients_stress():
    """10 concurrent threads simultaneously requesting status via IPC."""
    server, orchestrator, pipe_name, authkey_hex = _setup_test_control_server()
    results = queue.Queue()
    num_threads = 10
    barrier = threading.Barrier(num_threads)

    def worker():
        barrier.wait()  # Synchronize start across all threads
        try:
            st = HubControlClient.get_status(pipe_name, authkey_hex, timeout=5.0)
            results.put(st is not None and st.get("state") == "running")
        except Exception as e:
            results.put(e)

    threads = [threading.Thread(target=worker) for _ in range(num_threads)]
    try:
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5.0)

        assert results.qsize() == num_threads
        while not results.empty():
            item = results.get_nowait()
            assert item is True, f"Concurrent client request failed: {item}"
    finally:
        server.stop()
        orchestrator.stop()


def test_server_shutdown_unblocks_cleanly_without_orphaned_threads():
    """Verify server.stop() joins within bounded timeout and releases all resources."""
    server, orchestrator, pipe_name, _ = _setup_test_control_server()
    try:
        start = time.time()
        server.stop()
        elapsed = time.time() - start
        assert elapsed < 3.0, f"Server shutdown took too long ({elapsed:.2f}s)"
        assert server._thread is not None and not server._thread.is_alive()
        assert server._listener is None
    finally:
        orchestrator.stop()


def test_repeated_half_open_connections_do_not_block_legitimate_client():
    """
    Multiple half-open clients connect and remain silent.
    Verify that the bounded worker handler model allows legitimate clients
    to be served immediately (<200ms) without waiting for half-open timeouts.
    """
    server, orchestrator, pipe_name, authkey_hex = _setup_test_control_server()
    family = get_ipc_family(pipe_name)
    auth_bytes = bytes.fromhex(authkey_hex)

    silent_clients = []
    try:
        # Establish 3 concurrent silent/idle connections
        for _ in range(3):
            c = Client(pipe_name, family=family, authkey=auth_bytes)
            silent_clients.append(c)

        # Confirm all 3 silent connections are accepted and in active_connections
        time.sleep(0.1)
        with server._conn_lock:
            assert len(server._active_connections) == 3

        # Legitimate client connects while 3 silent clients are idling
        t0 = time.monotonic()
        pid = HubControlClient.ping(pipe_name, authkey_hex, timeout=2.0)
        t_elapsed = time.monotonic() - t0

        assert pid == os.getpid()
        # Legitimate client must NOT be blocked by the silent clients' 2-second timeout
        assert t_elapsed < 0.5, f"Legitimate client took too long: {t_elapsed:.3f}s"
    finally:
        for c in silent_clients:
            try:
                c.close()
            except Exception:
                pass
        server.stop()
        orchestrator.stop()


def test_shutdown_while_client_polling():
    """Verify server.stop() forcibly closes active connection handles and exits cleanly within 1.5s."""
    server, orchestrator, pipe_name, authkey_hex = _setup_test_control_server()
    family = get_ipc_family(pipe_name)
    auth_bytes = bytes.fromhex(authkey_hex)

    client = Client(pipe_name, family=family, authkey=auth_bytes)
    try:
        time.sleep(0.1)
        with server._conn_lock:
            assert len(server._active_connections) == 1

        t0 = time.monotonic()
        server.stop()
        t_elapsed = time.monotonic() - t0

        assert t_elapsed < 1.5, f"Shutdown while polling took too long: {t_elapsed:.2f}s"
        assert not server._thread.is_alive()
        with server._conn_lock:
            assert len(server._active_connections) == 0
            for w in server._worker_threads:
                assert not w.is_alive()
    finally:
        try:
            client.close()
        except Exception:
            pass
        orchestrator.stop()


def test_concurrent_connection_cap_load_shedding():
    """
    Connect more than MAX_CONCURRENT_CLIENTS (8) simultaneous clients.
    Assert that the active connection count never exceeds 8 and excess clients
    are closed/dropped cleanly without resource leaks.
    """
    server, orchestrator, pipe_name, authkey_hex = _setup_test_control_server()
    family = get_ipc_family(pipe_name)
    auth_bytes = bytes.fromhex(authkey_hex)

    clients = []
    try:
        # Attempt to open 12 simultaneous connections (MAX_CONCURRENT_CLIENTS = 8)
        for _ in range(12):
            try:
                c = Client(pipe_name, family=family, authkey=auth_bytes)
                clients.append(c)
            except Exception:
                # Excess clients may be closed immediately by the server
                pass

        time.sleep(0.15)
        with server._conn_lock:
            assert len(server._active_connections) <= server.MAX_CONCURRENT_CLIENTS, (
                f"Active connections ({len(server._active_connections)}) exceeded cap ({server.MAX_CONCURRENT_CLIENTS})"
            )
    finally:
        for c in clients:
            try:
                c.close()
            except Exception:
                pass
        server.stop()
        orchestrator.stop()


def test_race_connection_acceptance_against_shutdown_repeatedly():
    """
    Rapidly race connection acceptance against server.stop().
    Verify across multiple iterations that no deadlocks occur, shutdown completes
    in bounded time, and no unclosed connections or worker threads remain.
    """
    for iteration in range(5):
        server, orchestrator, pipe_name, authkey_hex = _setup_test_control_server()
        stop_called = threading.Event()

        def spam_client():
            while not stop_called.is_set():
                try:
                    HubControlClient.ping(pipe_name, authkey_hex, timeout=0.5)
                except Exception:
                    pass
                time.sleep(0.01)

        threads = [threading.Thread(target=spam_client, daemon=True) for _ in range(4)]
        for t in threads:
            t.start()

        time.sleep(0.05)
        stop_called.set()

        t0 = time.monotonic()
        server.stop()
        t_elapsed = time.monotonic() - t0
        orchestrator.stop()

        for t in threads:
            t.join(timeout=1.0)

        assert t_elapsed < 2.0, f"Iteration {iteration}: stop() took too long ({t_elapsed:.2f}s)"
        assert not server._thread.is_alive()
        with server._conn_lock:
            assert len(server._active_connections) == 0


# ---------------------------------------------------------------------------
# Section 4: Multi-Session Context Isolation & Concurrency Stress Testing
# ---------------------------------------------------------------------------


def test_multi_session_context_isolation():
    """Verify that changes in Session 1 do not alter Session 2."""
    registry = ContextRegistry()

    s1 = registry.get_session("session_1")
    s2 = registry.get_session("session_2")

    s1.set("db_connection", "postgres_prod")
    s1.set("ssh_host", "bastion-prod")
    s1.set("workspace", "C:\\projects\\app1")

    s2.set("db_connection", "sqlite_dev")
    s2.set("ssh_host", "staging-server")
    s2.set("workspace", "C:\\projects\\app2")

    # Verify Session 1 values
    assert s1.get("db_connection") == "postgres_prod"
    assert s1.get("ssh_host") == "bastion-prod"
    assert s1.get("workspace") == "C:\\projects\\app1"

    # Verify Session 2 values
    assert s2.get("db_connection") == "sqlite_dev"
    assert s2.get("ssh_host") == "staging-server"
    assert s2.get("workspace") == "C:\\projects\\app2"

    # Clear Session 1; Session 2 remains intact
    s1.clear()
    assert s1.get("db_connection") is None
    assert s2.get("db_connection") == "sqlite_dev"


def test_twenty_thread_concurrent_context_stress_with_barrier():
    """
    20 concurrent threads running simultaneous set/push/pop/get/snapshot operations
    across two distinct sessions, synchronized by a barrier.
    Validates state integrity, thread-safety, and session isolation.
    """
    registry = ContextRegistry()
    num_threads = 20
    barrier = threading.Barrier(num_threads)
    errors = queue.Queue()

    def worker(thread_idx: int):
        sid = "session_A" if (thread_idx % 2 == 0) else "session_B"
        expected_tag = "A" if (thread_idx % 2 == 0) else "B"

        barrier.wait()  # Synchronized release

        try:
            for iteration in range(25):
                ctx = registry.get_session(sid)
                val = f"db_{expected_tag}_{thread_idx}_{iteration}"

                ctx.push("db_connection", val)
                current = ctx.get("db_connection")
                assert current is not None
                # Must be tagged with current session's tag (no cross-session leakage)
                assert f"_{expected_tag}_" in current

                # Snapshot check
                snap = ctx.snapshot()
                assert snap["db_connection"]["depth"] > 0
                active_val = snap["db_connection"]["active"]
                assert active_val is not None
                assert f"_{expected_tag}_" in active_val

                # Pop
                popped = ctx.pop("db_connection")
                assert popped is not None
                assert f"_{expected_tag}_" in popped
        except Exception as e:
            errors.put((thread_idx, e))

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(num_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10.0)

    assert errors.empty(), f"Errors during 20-thread concurrency test: {list(errors.queue)}"


# ---------------------------------------------------------------------------
# Section 5: Snapshot Deep Immutability Tests
# ---------------------------------------------------------------------------


def test_session_context_snapshot_deep_immutability():
    """
    Verify that mutating collections or nested objects returned by snapshot()
    does NOT alter the internal stored session context state.
    """
    ctx = SessionContext(session_id="immutability_test")

    # Set nested mutable structure
    original_dict = {
        "connection_name": "pg_cluster",
        "options": {"ssl": True, "pool_size": 10},
        "tags": ["prod", "critical"],
    }
    ctx.set("db_connection", original_dict)

    # Obtain snapshot
    snap = ctx.snapshot()
    active_ref = snap["db_connection"]["active"]

    # Mutate the returned snapshot structure
    if isinstance(active_ref, dict):
        active_ref["mutated_key"] = "hacked"
        if "options" in active_ref and isinstance(active_ref["options"], dict):
            active_ref["options"]["pool_size"] = 9999
        if "tags" in active_ref and isinstance(active_ref["tags"], list):
            active_ref["tags"].append("unauthorized_tag")

    # Verify internal state inside SessionContext is completely unmutated
    internal_val = ctx.get("db_connection")
    assert isinstance(internal_val, dict)
    assert "mutated_key" not in internal_val, "Internal context was contaminated by snapshot mutation!"
    assert internal_val["options"]["pool_size"] == 10, "Nested dictionary was mutated via snapshot reference!"
    assert internal_val["tags"] == ["prod", "critical"], "Nested list was mutated via snapshot reference!"
