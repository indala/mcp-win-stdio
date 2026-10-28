"""
Windows NTFS DACL and Security Descriptor hardening helpers.
Provides explicit, protected DACL enforcement for hub metadata directories
and sensitive files using Win32 Security APIs (advapi32/kernel32) with SDDL.
"""

import json
import logging
import os
import re
import secrets
import stat
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Optional, Set, Union

logger = logging.getLogger(__name__)

# Constants for Windows Security
SE_FILE_OBJECT = 1
DACL_SECURITY_INFORMATION = 0x00000004
PROTECTED_DACL_SECURITY_INFORMATION = 0x80000000
SDDL_REVISION_1 = 1
TOKEN_QUERY = 0x0008

# Standard Well-Known SIDs allowed in strict allowlist
WELL_KNOWN_ALLOWED_TRUSTEES: Set[str] = {
    "SY",  # Local SYSTEM
    "S-1-5-18",
    "BA",  # Built-in Administrators
    "S-1-5-32-544",
    "OW",  # Owner Rights
    "S-1-3-4",
    "CO",  # Creator Owner
    "S-1-3-0",
}

# Broad / unprivileged Windows trustees that MUST NEVER be present in secure DACLs
FORBIDDEN_TRUSTEES: Set[str] = {
    "WD",  # Everyone / World (S-1-1-0)
    "BU",  # Built-in Users (S-1-5-32-545)
    "AU",  # Authenticated Users (S-1-5-11)
    "AN",  # Anonymous (S-1-5-7)
    "BG",  # Built-in Guests (S-1-5-32-546)
    "NU",  # Network (S-1-5-2)
    "S-1-1-0",
    "S-1-5-32-545",
    "S-1-5-11",
    "S-1-5-7",
    "S-1-5-32-546",
    "S-1-5-2",
}


class WindowsSecurityError(RuntimeError):
    """Raised when Windows access control or security descriptor operations fail."""


if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes

    advapi32 = ctypes.windll.advapi32
    kernel32 = ctypes.windll.kernel32

    class _SID_AND_ATTRIBUTES(ctypes.Structure):
        _fields_ = [("Sid", wintypes.LPVOID), ("Attributes", wintypes.DWORD)]

    class _TOKEN_USER(ctypes.Structure):
        _fields_ = [("User", _SID_AND_ATTRIBUTES)]

    # Function signatures
    kernel32.OpenProcessToken.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.HANDLE),
    ]
    kernel32.OpenProcessToken.restype = wintypes.BOOL

    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL

    kernel32.LocalFree.argtypes = [wintypes.HLOCAL]
    kernel32.LocalFree.restype = wintypes.HLOCAL

    advapi32.GetTokenInformation.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
    ]
    advapi32.GetTokenInformation.restype = wintypes.BOOL

    advapi32.ConvertSidToStringSidW.argtypes = [
        wintypes.LPVOID,
        ctypes.POINTER(wintypes.LPWSTR),
    ]
    advapi32.ConvertSidToStringSidW.restype = wintypes.BOOL

    advapi32.ConvertStringSecurityDescriptorToSecurityDescriptorW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.LPVOID),
        ctypes.POINTER(wintypes.ULONG),
    ]
    advapi32.ConvertStringSecurityDescriptorToSecurityDescriptorW.restype = wintypes.BOOL

    advapi32.ConvertSecurityDescriptorToStringSecurityDescriptorW.argtypes = [
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.LPWSTR),
        ctypes.POINTER(wintypes.ULONG),
    ]
    advapi32.ConvertSecurityDescriptorToStringSecurityDescriptorW.restype = wintypes.BOOL

    advapi32.GetSecurityDescriptorDacl.argtypes = [
        wintypes.LPVOID,
        ctypes.POINTER(wintypes.BOOL),
        ctypes.POINTER(wintypes.LPVOID),
        ctypes.POINTER(wintypes.BOOL),
    ]
    advapi32.GetSecurityDescriptorDacl.restype = wintypes.BOOL

    advapi32.SetNamedSecurityInfoW.argtypes = [
        wintypes.LPWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.LPVOID,
        wintypes.LPVOID,
        wintypes.LPVOID,
    ]
    advapi32.SetNamedSecurityInfoW.restype = wintypes.DWORD

    advapi32.GetNamedSecurityInfoW.argtypes = [
        wintypes.LPWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.LPVOID),
        ctypes.POINTER(wintypes.LPVOID),
        ctypes.POINTER(wintypes.LPVOID),
        ctypes.POINTER(wintypes.LPVOID),
        ctypes.POINTER(wintypes.LPVOID),
    ]
    advapi32.GetNamedSecurityInfoW.restype = wintypes.DWORD


def get_current_user_sid() -> str:
    """Retrieve string SID for the current process token on Windows."""
    if sys.platform != "win32":
        return "S-1-5-CURRENT-USER"

    token = wintypes.HANDLE()
    if not kernel32.OpenProcessToken(kernel32.GetCurrentProcess(), TOKEN_QUERY, ctypes.byref(token)):
        err = ctypes.GetLastError()
        raise WindowsSecurityError(f"OpenProcessToken failed with Win32 error code {err}")

    try:
        ret_len = wintypes.DWORD(0)
        advapi32.GetTokenInformation(token, 1, None, 0, ctypes.byref(ret_len))
        if ret_len.value == 0:
            err = ctypes.GetLastError()
            raise WindowsSecurityError(f"GetTokenInformation length query failed with error {err}")

        buf = ctypes.create_string_buffer(ret_len.value)
        if not advapi32.GetTokenInformation(token, 1, buf, ret_len.value, ctypes.byref(ret_len)):
            err = ctypes.GetLastError()
            raise WindowsSecurityError(f"GetTokenInformation failed with error {err}")

        token_user = ctypes.cast(buf, ctypes.POINTER(_TOKEN_USER)).contents
        p_str_sid = wintypes.LPWSTR()
        if not advapi32.ConvertSidToStringSidW(token_user.User.Sid, ctypes.byref(p_str_sid)):
            err = ctypes.GetLastError()
            raise WindowsSecurityError(f"ConvertSidToStringSidW failed with error {err}")

        try:
            sid_str = p_str_sid.value
            if not sid_str:
                raise WindowsSecurityError("ConvertSidToStringSidW returned an empty SID string")
            return sid_str
        finally:
            kernel32.LocalFree(p_str_sid)
    finally:
        kernel32.CloseHandle(token)


def get_sddl_string(path: Union[str, Path]) -> str:
    """Retrieve DACL SDDL string for a path on Windows."""
    if sys.platform != "win32":
        return ""

    path_str = str(path)
    p_sd_out = wintypes.LPVOID()
    p_dacl_out = wintypes.LPVOID()

    err = advapi32.GetNamedSecurityInfoW(
        path_str,
        SE_FILE_OBJECT,
        DACL_SECURITY_INFORMATION,
        None,
        None,
        ctypes.byref(p_dacl_out),
        None,
        ctypes.byref(p_sd_out),
    )
    if err != 0:
        raise WindowsSecurityError(f"GetNamedSecurityInfoW failed for '{path_str}' with Win32 error {err}")

    try:
        p_out_sddl = wintypes.LPWSTR()
        ok = advapi32.ConvertSecurityDescriptorToStringSecurityDescriptorW(
            p_sd_out,
            SDDL_REVISION_1,
            DACL_SECURITY_INFORMATION,
            ctypes.byref(p_out_sddl),
            None,
        )
        if not ok:
            err_code = ctypes.GetLastError()
            raise WindowsSecurityError(
                f"ConvertSecurityDescriptorToStringSecurityDescriptorW failed with error {err_code}"
            )
        try:
            res = p_out_sddl.value or ""
            return res
        finally:
            kernel32.LocalFree(p_out_sddl)
    finally:
        kernel32.LocalFree(p_sd_out)


def verify_security_descriptor(path: Union[str, Path], is_directory: bool = False) -> bool:
    """
    Verify that the target path has a protected, non-inherited DACL granting access
    exclusively to the current user, SYSTEM, and Administrators, with no permissive/broad ACEs.
    """
    path_obj = Path(path)
    if not path_obj.exists():
        raise WindowsSecurityError(f"Cannot verify non-existent path: {path}")

    if sys.platform != "win32":
        mode = path_obj.stat().st_mode
        # Ensure group and others have zero permissions (0o700 for dir, 0o600 for file)
        if mode & 0o077 != 0:
            raise WindowsSecurityError(
                f"Insecure POSIX permissions {oct(stat.S_IMODE(mode))} on {path}; expected 0700/0600"
            )
        return True

    user_sid = get_current_user_sid()
    sddl = get_sddl_string(path)

    allowed_trustees: Set[str] = {
        user_sid.upper(),
        *WELL_KNOWN_ALLOWED_TRUSTEES,
    }

    # 1. Verify DACL is protected (inheritance blocked)
    # SDDL flags after D: must contain P (Protected)
    dacl_header_match = re.search(r"D:([A-Z]*)", sddl)
    if not dacl_header_match or "P" not in dacl_header_match.group(1):
        raise WindowsSecurityError(f"DACL on '{path}' is not protected against inheritance (SDDL: {sddl})")

    # 2. Strict allowlist ACE parse and verification
    aces = re.findall(r"\((.*?)\)", sddl)
    if not aces:
        raise WindowsSecurityError(f"DACL on '{path}' is empty or lacks ACEs (SDDL: {sddl})")

    has_user_access = False

    for ace in aces:
        parts = ace.split(";")
        if len(parts) >= 6:
            ace_type = parts[0].strip().upper()
            # Enforce that every ACE is an Access-Allowed ACE ("A")
            if ace_type != "A":
                raise WindowsSecurityError(f"DACL on '{path}' contains non-allow ACE type '{ace_type}' (SDDL: {sddl})")

            trustee = parts[5].strip().upper()
            # Explicit denylist check
            if trustee in FORBIDDEN_TRUSTEES:
                raise WindowsSecurityError(
                    f"DACL on '{path}' contains forbidden broad trustee '{trustee}' (SDDL: {sddl})"
                )
            # Strict allowlist check: reject unexpected trustees (service accounts, other users)
            if trustee not in allowed_trustees:
                raise WindowsSecurityError(
                    f"DACL on '{path}' contains unauthorized trustee '{trustee}' outside allowlist (SDDL: {sddl})"
                )

            if trustee == user_sid.upper():
                has_user_access = True

    if not has_user_access:
        raise WindowsSecurityError(
            f"DACL on '{path}' does not grant access to current user SID '{user_sid}' (SDDL: {sddl})"
        )

    return True


def _apply_windows_dacl(path: Union[str, Path], sddl: str) -> None:
    """Compile SDDL and apply explicit protected DACL to a Windows path."""
    path_str = str(path)
    p_sd = wintypes.LPVOID()

    if not advapi32.ConvertStringSecurityDescriptorToSecurityDescriptorW(
        sddl, SDDL_REVISION_1, ctypes.byref(p_sd), None
    ):
        err = ctypes.GetLastError()
        raise WindowsSecurityError(
            f"ConvertStringSecurityDescriptorToSecurityDescriptorW failed for SDDL '{sddl}': error {err}"
        )

    try:
        dacl_present = wintypes.BOOL()
        p_dacl = wintypes.LPVOID()
        dacl_defaulted = wintypes.BOOL()

        if not advapi32.GetSecurityDescriptorDacl(
            p_sd,
            ctypes.byref(dacl_present),
            ctypes.byref(p_dacl),
            ctypes.byref(dacl_defaulted),
        ):
            err = ctypes.GetLastError()
            raise WindowsSecurityError(f"GetSecurityDescriptorDacl failed: error {err}")

        if not dacl_present.value:
            raise WindowsSecurityError("Generated security descriptor lacks a DACL")

        res = advapi32.SetNamedSecurityInfoW(
            path_str,
            SE_FILE_OBJECT,
            DACL_SECURITY_INFORMATION | PROTECTED_DACL_SECURITY_INFORMATION,
            None,
            None,
            p_dacl,
            None,
        )
        if res != 0:
            raise WindowsSecurityError(f"SetNamedSecurityInfoW failed for '{path_str}' with Win32 error code {res}")
    finally:
        kernel32.LocalFree(p_sd)


def secure_directory(path: Union[str, Path]) -> None:
    """
    Apply a protected, explicit DACL to a directory.
    Grants access exclusively to Current User (full control, container/object inherit),
    SYSTEM (S-1-5-18), and Administrators (S-1-5-32-544).
    Disables inheritance from parent directories.
    """
    path_obj = Path(path)
    path_obj.mkdir(parents=True, exist_ok=True)

    if sys.platform == "win32":
        user_sid = get_current_user_sid()
        # D:P = Discretionary ACL, Protected (no inheritance)
        # (A;OICI;FA;;;{user_sid}) = Allow, Container/Object inherit, File All Access
        # (A;OICI;FA;;;SY) = Allow SYSTEM
        # (A;OICI;FA;;;BA) = Allow Built-in Administrators
        sddl = f"D:P(A;OICI;FA;;;{user_sid})(A;OICI;FA;;;SY)(A;OICI;FA;;;BA)"
        _apply_windows_dacl(path_obj, sddl)
        verify_security_descriptor(path_obj, is_directory=True)
    else:
        path_obj.chmod(0o700)
        verify_security_descriptor(path_obj, is_directory=True)


def secure_file(path: Union[str, Path]) -> None:
    """
    Apply a protected, explicit DACL to an existing file.
    Grants access exclusively to Current User (FA), SYSTEM (FA), and Administrators (FA).
    Disables inheritance from parent directories.
    """
    path_obj = Path(path)
    if not path_obj.exists():
        raise WindowsSecurityError(f"Cannot secure non-existent file: {path}")

    if sys.platform == "win32":
        user_sid = get_current_user_sid()
        sddl = f"D:P(A;;FA;;;{user_sid})(A;;FA;;;SY)(A;;FA;;;BA)"
        _apply_windows_dacl(path_obj, sddl)
        verify_security_descriptor(path_obj, is_directory=False)
    else:
        path_obj.chmod(0o600)
        verify_security_descriptor(path_obj, is_directory=False)


def write_secure_json_file(path: Union[str, Path], data: Dict[str, Any]) -> None:
    """
    Safely and atomically write sensitive JSON metadata to disk:
      1. Ensure parent directory exists and is secured with protected DACL.
      2. Create an empty temporary file.
      3. Apply protected DACL to the empty temporary file BEFORE writing sensitive secrets.
      4. Write the JSON payload.
      5. Re-verify/enforce protected DACL on the temporary file.
      6. Atomically replace the target file.
      7. Re-enforce and verify the protected DACL on the destination file.
      8. Clean up temp file safely on any error without destroying live instance metadata.
    """
    target_path = Path(path).resolve()
    parent_dir = target_path.parent

    # Prevent symlink/junction redirection attacks
    if parent_dir.is_symlink():
        raise WindowsSecurityError(f"Parent directory '{parent_dir}' is a symlink; rejected")
    if target_path.is_symlink():
        raise WindowsSecurityError(f"Target path '{target_path}' is a symlink; rejected")

    secure_directory(parent_dir)

    # Unpredictable random temporary file name
    rand_suffix = secrets.token_hex(16)
    tmp_path = parent_dir / f".tmp.{target_path.name}.{os.getpid()}.{rand_suffix}.tmp"

    try:
        # Step 3: Create empty file with exclusive creation semantics (O_CREAT | O_EXCL)
        flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
        if hasattr(os, "O_BINARY"):
            flags |= os.O_BINARY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW

        fd = os.open(str(tmp_path), flags, 0o600)
        os.close(fd)

        # Step 4: Secure permissions before secrets enter the file
        secure_file(tmp_path)

        # Step 5: Write payload
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
            f.flush()
            os.fsync(f.fileno())

        # Step 6: Enforce DACL again after write
        secure_file(tmp_path)

        # Before replace, re-verify target is not a symlink/reparse point
        if target_path.is_symlink():
            raise WindowsSecurityError(f"Target path '{target_path}' became a symlink during write; aborting")

        # Step 7: Atomic replacement
        tmp_path.replace(target_path)

        # Step 8: Re-secure and verify final target
        secure_file(target_path)
        verify_security_descriptor(target_path, is_directory=False)
    except Exception:
        # Step 9: Clean up tmp file on failure; do NOT delete target_path!
        try:
            if tmp_path.exists():
                tmp_path.unlink(missing_ok=True)
        except Exception:
            pass
        raise


@contextmanager
def interprocess_file_lock(lock_path: Union[str, Path], timeout: float = 10.0):
    """
    Acquire an exclusive cross-process filesystem lock.
    Uses Win32/msvcrt byte locking on Windows, and fcntl.flock on POSIX.
    Blocks up to timeout seconds. Raises TimeoutError if lock cannot be acquired.
    Kernel automatically releases lock if process crashes or is killed.
    """
    path_obj = Path(lock_path).resolve()
    parent_dir = path_obj.parent
    parent_dir.mkdir(parents=True, exist_ok=True)

    if sys.platform == "win32":
        try:
            secure_directory(parent_dir)
        except Exception:
            pass

    deadline = time.time() + max(0.1, timeout)
    f = None

    try:
        f = open(path_obj, "a+b")
        if sys.platform == "win32":
            try:
                secure_file(path_obj)
            except Exception:
                pass

        # Ensure at least 1 byte exists in file for byte-range locking
        f.seek(0, os.SEEK_END)
        if f.tell() == 0:
            f.write(b"\x00")
            f.flush()
        fd = f.fileno()

        locked = False
        while time.time() < deadline:
            if sys.platform == "win32":
                import msvcrt

                try:
                    f.seek(0)
                    msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                    locked = True
                    break
                except (OSError, IOError):
                    time.sleep(0.05)
            else:
                import fcntl

                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    locked = True
                    break
                except (OSError, IOError):
                    time.sleep(0.05)

        if not locked:
            raise TimeoutError(f"Timed out after {timeout:.1f}s acquiring lockfile '{path_obj}'")

        try:
            yield
        finally:
            if sys.platform == "win32":
                import msvcrt

                try:
                    f.seek(0)
                    msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
                except Exception:
                    pass
            else:
                import fcntl

                try:
                    fcntl.flock(fd, fcntl.LOCK_UN)
                except Exception:
                    pass
    finally:
        if f is not None:
            try:
                f.close()
            except Exception:
                pass
