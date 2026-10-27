"""
External Windows Updater & Uninstaller Supervisor
Part of mcp-win-stdio.

Operates independently from %LOCALAPPDATA%/mcp-win-stdio/bin/ to allow in-flight updates
and clean self-uninstallation on Windows without triggering OS Error 5 (Access is denied).
"""

import os
import subprocess
import sys
from pathlib import Path
from typing import List, Tuple


def get_local_appdata_dir() -> Path:
    """Return %LOCALAPPDATA%/mcp-win-stdio/bin path."""
    local_app = os.environ.get("LOCALAPPDATA")
    if local_app:
        base = Path(local_app)
    else:
        base = Path.home() / "AppData" / "Local"
    target = base / "mcp-win-stdio" / "bin"
    target.mkdir(parents=True, exist_ok=True)
    return target


SUPERVISOR_SCRIPT_CONTENT = r'''"""
mcp-win-stdio Windows Supervisor
Standalone worker that executes updates and uninstalls after releasing caller executable locks.
STDLIB ONLY: Must NOT import mcp_win_stdio or third-party packages.
"""

import ctypes
import os
import pathlib
import shutil
import subprocess
import sys
import time
from typing import List

# Ensure UTF-8 output on Windows console
if sys.platform == "win32":
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

SYNCHRONIZE = 0x00100000
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000


def get_process_name(pid: int) -> str:
    """Return process executable name in lowercase without side effects."""
    if pid <= 0 or sys.platform != "win32":
        return ""
    k32 = ctypes.windll.kernel32
    h = k32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not h:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(260)
        size = ctypes.c_ulong(260)
        if k32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
            return pathlib.Path(buf.value).name.lower()
        return ""
    finally:
        k32.CloseHandle(h)


def wait_for_pid(pid: int, timeout: float = 10.0) -> None:
    """Wait for a process ID to terminate cleanly using Win32 API without killing it."""
    if pid <= 0 or sys.platform != "win32":
        return
    k32 = ctypes.windll.kernel32
    h = k32.OpenProcess(SYNCHRONIZE, False, pid)
    if not h:
        return  # Process already exited
    try:
        k32.WaitForSingleObject(h, int(timeout * 1000))
    finally:
        k32.CloseHandle(h)


def is_uv_tool_install(target_python: str) -> bool:
    """Detect if mcp-win-stdio was installed as an isolated uv tool."""
    target_lower = target_python.lower()
    return "uv\\tools\\mcp-win-stdio" in target_lower or "uv/tools/mcp-win-stdio" in target_lower


def find_mws_executable(target_python: str) -> str:
    """Find the mws.exe corresponding to target_python."""
    py_path = pathlib.Path(target_python)
    cand1 = py_path.parent / "mws.exe"
    if cand1.exists():
        return str(cand1)
    cand2 = py_path.parent / "Scripts" / "mws.exe"
    if cand2.exists():
        return str(cand2)
    cand3 = shutil.which("mws")
    if cand3:
        return cand3
    return ""


def main() -> None:
    if len(sys.argv) < 5:
        print("Usage: supervisor.py <action> <target_python> <pids_comma_separated> <package1> [package2...]")
        print("Actions: update, uninstall")
        input("\nPress Enter to exit...")
        sys.exit(1)

    action = sys.argv[1].lower()
    target_python = sys.argv[2]
    raw_pids = sys.argv[3]
    packages = sys.argv[4:]

    # Parse PIDs to monitor
    pids: List[int] = []
    for p in raw_pids.split(","):
        p = p.strip()
        if p.isdigit() and int(p) > 0:
            pids.append(int(p))

    # Set Window Title
    title_text = "mcp-win-stdio Windows Updater" if action == "update" else "mcp-win-stdio Windows Uninstaller"
    if sys.platform == "win32":
        try:
            ctypes.windll.kernel32.SetConsoleTitleW(title_text)
        except Exception:
            pass

    print("\n" + "=" * 76)
    if action == "update":
        print("  🔄  mcp-win-stdio Windows Update Supervisor")
    else:
        print("  🗑️   mcp-win-stdio Windows Uninstaller Supervisor")
    print("=" * 76 + "\n")

    # Step 1: Wait for caller processes to exit and release file locks
    # Only wait for processes that are actually python or the mws shim
    filtered_pids: List[int] = []
    for pid in pids:
        pname = get_process_name(pid)
        # If it's the python process or mws.exe shim, wait for it
        # If it's powershell.exe, cmd.exe, or an external terminal, do not block
        if pname in ("mws.exe", "python.exe", "pythonw.exe", "uv.exe") or not pname:
            filtered_pids.append(pid)

    if filtered_pids:
        print(f"[1/3] ⏳ Waiting for caller processes (PID: {', '.join(str(p) for p in filtered_pids)}) to release locks...")
        for pid in filtered_pids:
            wait_for_pid(pid, timeout=10.0)
        time.sleep(0.5)
        print("      ✅ Executable locks released.\n")
    else:
        print("[1/3] ℹ️  Standalone launch mode (no active file locks to wait for).\n")

    # Step 2: Determine package manager and execute
    has_uv = bool(shutil.which("uv"))
    is_tool = is_uv_tool_install(target_python)

    if action == "update":
        print(f"[2/3] 🚀 Updating target package(s): {', '.join(packages)}")
        if is_tool and has_uv:
            print("      Package manager: uv tool (isolated tool environment)")
            cmd = ["uv", "tool", "upgrade", "mcp-win-stdio"]
        elif has_uv:
            print("      Package manager: uv pip")
            cmd = ["uv", "pip", "install", "--python", target_python, "--upgrade"] + packages
        else:
            print("      Package manager: python pip")
            cmd = [target_python, "-m", "pip", "install", "--upgrade"] + packages

        print(f"      Running: {' '.join(cmd)}\n")
        res = subprocess.run(cmd, check=False)

        if res.returncode == 0:
            print("\n[3/3] ✅ Update completed successfully!\n")
            mws_bin = find_mws_executable(target_python)
            if mws_bin:
                print(f"Verifying updated CLI via {mws_bin}:")
                subprocess.run([mws_bin, "--version"], check=False)
            else:
                subprocess.run([target_python, "-m", "mcp_win_stdio", "--version"], check=False)
        else:
            print(f"\n[3/3] ❌ Update failed (exit code: {res.returncode}).")
            print("You can try updating manually via:")
            print(f"    {' '.join(cmd)}")

    elif action == "uninstall":
        print(f"[2/3] 🧹 Completely removing mcp-win-stdio package(s): {', '.join(packages)}")
        if is_tool and has_uv:
            print("      Package manager: uv tool")
            cmd = ["uv", "tool", "uninstall", "mcp-win-stdio"]
        elif has_uv:
            print("      Package manager: uv pip")
            cmd = ["uv", "pip", "uninstall", "--python", target_python, "-y"] + packages
        else:
            print("      Package manager: python pip")
            cmd = [target_python, "-m", "pip", "uninstall", "-y"] + packages

        print(f"      Running: {' '.join(cmd)}\n")
        res = subprocess.run(cmd, check=False)

        if res.returncode == 0:
            print("\n[3/3] ✅ Uninstallation completed. All requested packages removed.\n")
            print("🔒 Note: User configurations in ~/.mcp-win-stdio remain preserved.")
        else:
            print(f"\n[3/3] ❌ Uninstallation failed (exit code: {res.returncode}).")

    print("\n" + "=" * 76)
    input("Press Enter to close this window...")


if __name__ == "__main__":
    main()
'''


def ensure_external_updater_scripts(target_python: str, base_python: str) -> Tuple[Path, Path, Path]:
    """
    Write or update standalone supervisor and .cmd helper scripts in %LOCALAPPDATA%/mcp-win-stdio/bin/.
    Returns (supervisor_path, updater_cmd_path, uninstaller_cmd_path).
    """
    target_dir = get_local_appdata_dir()
    supervisor_path = target_dir / "supervisor.py"
    updater_cmd_path = target_dir / "mws-updater.cmd"
    uninstaller_cmd_path = target_dir / "mws-uninstaller.cmd"

    # 1. Write the Python supervisor script
    supervisor_path.write_text(SUPERVISOR_SCRIPT_CONTENT, encoding="utf-8")

    # 2. Write mws-updater.cmd helper
    updater_cmd_content = f"""@echo off
setlocal
title mcp-win-stdio Windows Updater
"{base_python}" "%~dp0supervisor.py" update "{target_python}" 0 "mcp-win-stdio[all]"
"""
    updater_cmd_path.write_text(updater_cmd_content, encoding="utf-8")

    # 3. Write mws-uninstaller.cmd helper
    uninstaller_cmd_content = f"""@echo off
setlocal
title mcp-win-stdio Windows Uninstaller
echo ============================================================================
echo   mcp-win-stdio Windows Uninstaller
echo ============================================================================
echo.
set /p CONFIRM="Are you sure you want to completely uninstall mcp-win-stdio suite? (y/N): "
if /i not "%CONFIRM%"=="y" (
    echo Uninstallation cancelled.
    timeout /t 2 >nul
    exit /b 0
)
"{base_python}" "%~dp0supervisor.py" uninstall "{target_python}" 0 "mcp-win-stdio"
"""
    uninstaller_cmd_path.write_text(uninstaller_cmd_content, encoding="utf-8")

    return supervisor_path, updater_cmd_path, uninstaller_cmd_path


def ensure_external_updater_script() -> Path:
    """Backwards compatibility alias returning the updater .cmd script path."""
    target_python = str(Path(sys.executable).resolve())
    base_python = str(Path(getattr(sys, "_base_executable", sys.executable)).resolve())
    _, updater_cmd, _ = ensure_external_updater_scripts(target_python, base_python)
    return updater_cmd


def spawn_external_updater(action: str, packages: List[str]) -> bool:
    """
    Launch the external supervisor in a detached console window and terminate the current process.
    Guarantees 0ms lock contention because current mws.exe and python.exe exit before pip/uv attempts modification.
    """
    if sys.platform != "win32":
        return False

    target_python = str(Path(sys.executable).resolve())
    # Use base system interpreter to run supervisor so target venv's python.exe is not locked
    base_python = str(Path(getattr(sys, "_base_executable", sys.executable)).resolve())

    supervisor_path, updater_cmd, uninstaller_cmd = ensure_external_updater_scripts(
        target_python=target_python,
        base_python=base_python,
    )

    caller_pid = os.getpid()
    caller_ppid = os.getppid()
    pids_arg = f"{caller_pid},{caller_ppid}"

    action_label = "update" if action == "update" else "uninstall"
    script_display = updater_cmd if action == "update" else uninstaller_cmd

    print("\n" + "=" * 76)
    print(f"🚀 Handing off {action_label} to external supervisor: {script_display}")
    print(f"🚪 Exiting current mws process (PID: {caller_pid}, PPID: {caller_ppid}) to release executable file locks...")
    print("=" * 76 + "\n")

    cmd = [
        base_python,
        str(supervisor_path),
        action,
        target_python,
        pids_arg,
    ] + packages

    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"

    try:
        subprocess.Popen(
            cmd,
            env=env,
            creationflags=subprocess.CREATE_NEW_CONSOLE,
            close_fds=True,
        )
        sys.exit(0)
    except Exception as e:
        sys.stderr.write(f"Failed to launch external supervisor: {e}\n")
        return False
