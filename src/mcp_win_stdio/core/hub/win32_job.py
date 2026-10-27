"""
Win32 Job Object management for guaranteed child process isolation and cleanup.
Ensures child processes are automatically terminated by the Windows kernel if the parent exits.
"""

import logging
import subprocess
import sys
import threading
from typing import Any, Optional, Union

logger = logging.getLogger(__name__)

# Win32 Constants
JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
JobObjectExtendedLimitInformation = 9
PROCESS_SET_QUOTA = 0x0100
PROCESS_TERMINATE = 0x0001

if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes

    class IO_COUNTERS(ctypes.Structure):
        _fields_ = [
            ("ReadOperationCount", ctypes.c_uint64),
            ("WriteOperationCount", ctypes.c_uint64),
            ("OtherOperationCount", ctypes.c_uint64),
            ("ReadTransferCount", ctypes.c_uint64),
            ("WriteTransferCount", ctypes.c_uint64),
            ("OtherTransferCount", ctypes.c_uint64),
        ]

    class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_int64),
            ("PerJobUserTimeLimit", ctypes.c_int64),
            ("LimitFlags", wintypes.DWORD),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", wintypes.DWORD),
            ("SchedulingClass", wintypes.DWORD),
        ]

    class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
            ("IoInfo", IO_COUNTERS),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryLimit", ctypes.c_size_t),
            ("PeakJobMemoryLimit", ctypes.c_size_t),
        ]


class Win32JobObject:
    """
    Encapsulates a Windows Job Object configured with JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE.
    When this job object is closed or when the host process terminates, all attached
    child processes are unconditionally terminated by the OS kernel.
    """

    def __init__(self, name: Optional[str] = None):
        self._name = name
        self._lock = threading.Lock()
        self._handle: Optional[int] = None
        self._is_supported = sys.platform == "win32"

        if self._is_supported:
            self._create_job_object()

    @property
    def is_supported(self) -> bool:
        """Return True if Windows Job Objects are supported on this platform."""
        return self._is_supported

    @property
    def handle(self) -> Optional[int]:
        """Return the raw Windows Job Object handle, if active."""
        return self._handle

    def _create_job_object(self) -> None:
        """Create the Win32 Job Object and configure kill-on-close policy."""
        try:
            k32 = ctypes.windll.kernel32
            handle = k32.CreateJobObjectW(None, self._name)
            if not handle:
                err = ctypes.GetLastError()
                logger.warning("Failed to create Win32 Job Object (err=%d)", err)
                return

            info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
            info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            success = k32.SetInformationJobObject(
                handle,
                JobObjectExtendedLimitInformation,
                ctypes.byref(info),
                ctypes.sizeof(info),
            )
            if not success:
                err = ctypes.GetLastError()
                logger.warning("Failed to set JobObjectExtendedLimitInformation (err=%d)", err)
                k32.CloseHandle(handle)
                return

            self._handle = handle
            logger.debug("Win32 Job Object initialized (handle=%s, name=%s)", handle, self._name)
        except Exception as e:
            logger.warning("Error initializing Win32 Job Object: %s", e)
            self._handle = None

    def assign_process(self, target: Union[subprocess.Popen, int]) -> bool:
        """
        Assign a process to this Job Object.

        Args:
            target: A subprocess.Popen instance or integer PID.

        Returns:
            bool: True if assignment succeeded, False otherwise.
        """
        if not self._is_supported or not self._handle:
            return True

        with self._lock:
            if not self._handle:
                return False

            k32 = ctypes.windll.kernel32

            # 1. Handle subprocess.Popen
            if isinstance(target, subprocess.Popen):
                h_proc = getattr(target, "_handle", None)
                if h_proc is not None:
                    # int(h_proc) gives the process handle
                    res = k32.AssignProcessToJobObject(self._handle, int(h_proc))
                    if not res:
                        err = ctypes.GetLastError()
                        logger.warning("AssignProcessToJobObject failed for Popen (pid=%s, err=%d)", target.pid, err)
                        return False
                    return True
                # Fallback to PID if _handle is somehow absent
                target = target.pid

            # 2. Handle integer PID
            if isinstance(target, int):
                h_proc = k32.OpenProcess(PROCESS_SET_QUOTA | PROCESS_TERMINATE, False, target)
                if not h_proc:
                    err = ctypes.GetLastError()
                    logger.warning("OpenProcess failed for PID %d (err=%d)", target, err)
                    return False
                try:
                    res = k32.AssignProcessToJobObject(self._handle, h_proc)
                    if not res:
                        err = ctypes.GetLastError()
                        logger.warning("AssignProcessToJobObject failed for PID %d (err=%d)", target, err)
                        return False
                    return True
                finally:
                    k32.CloseHandle(h_proc)

            return False

    def terminate(self, exit_code: int = 1) -> bool:
        """
        Immediately terminate all processes in this Job Object.

        Args:
            exit_code: Exit code to assign to terminated processes.

        Returns:
            bool: True if termination call succeeded.
        """
        if not self._is_supported or not self._handle:
            return True

        with self._lock:
            if not self._handle:
                return False
            k32 = ctypes.windll.kernel32
            res = k32.TerminateJobObject(self._handle, exit_code)
            return bool(res)

    def close(self) -> None:
        """Close the Job Object handle. Will trigger kill-on-close for remaining processes."""
        with self._lock:
            if self._handle:
                try:
                    ctypes.windll.kernel32.CloseHandle(self._handle)
                except Exception as e:
                    logger.debug("Error closing job handle: %s", e)
                finally:
                    self._handle = None

    def __enter__(self) -> "Win32JobObject":
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()

    def __del__(self) -> None:
        self.close()
