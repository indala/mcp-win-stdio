"""
External Windows Updater & Uninstaller Supervisor
Part of mcp-win-stdio.

Operates from %LOCALAPPDATA%/mcp-win-stdio/bin/ to allow in-flight updates
and clean self-uninstallation on Windows without triggering OS Error 5 (Access is denied).
"""

import os
import subprocess
import sys
from pathlib import Path
from typing import List


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


def ensure_external_updater_script() -> Path:
    """Write or update the standalone Windows updater batch script in AppData/Local."""
    target_dir = get_local_appdata_dir()
    script_path = target_dir / "mws-updater.cmd"

    content = r"""@echo off
setlocal enabledelayedexpansion
title mcp-win-stdio Windows Updater

set ACTION=%~1
set CALLER_PID=%~2
set PYTHON_EXE=%~3
set PACKAGE_TARGET=%~4

echo.
echo ============================================================================
echo   🔄 mcp-win-stdio Windows Updater Service
echo ============================================================================
echo.

:: 1. Wait for caller process to exit cleanly and release Windows executable locks
if not "%CALLER_PID%"=="" (
    echo [1/3] Waiting for active mws process (PID: %CALLER_PID%) to close...
    powershell -NoProfile -Command "$ErrorActionPreference = 'SilentlyContinue'; $p = Get-Process -Id %CALLER_PID% -ErrorAction SilentlyContinue; if ($p) { $p.WaitForExit(7000) }"
)

:: Extra short delay to ensure OS handles are fully recycled
timeout /t 1 /nobreak >nul

:: 2. Perform requested operation
if "%ACTION%"=="update" (
    echo [2/3] Installing latest packages from PyPI...
    where uv >nul 2>&1
    if !ERRORLEVEL! EQU 0 (
        echo Using package manager: uv pip
        uv pip install --python "%PYTHON_EXE%" --upgrade %PACKAGE_TARGET%
    ) else (
        echo Using package manager: python pip
        "%PYTHON_EXE%" -m pip install --upgrade %PACKAGE_TARGET%
    )

    if !ERRORLEVEL! EQU 0 (
        echo.
        echo [3/3] ✅ Update completed successfully!
        echo.
        echo Relaunching mws...
        timeout /t 1 /nobreak >nul
        where mws >nul 2>&1
        if !ERRORLEVEL! EQU 0 (
            mws --version
        ) else (
            "%PYTHON_EXE%" -m mcp_win_stdio --version
        )
        echo.
        echo Press any key to close this updater window.
        pause >nul
    ) else (
        echo.
        echo [!] Update encountered an error. Please verify your internet connection.
        echo Press any key to close.
        pause >nul
    )
) else if "%ACTION%"=="uninstall" (
    echo [2/3] Completely removing mcp-win-stdio packages...
    where uv >nul 2>&1
    if !ERRORLEVEL! EQU 0 (
        uv pip uninstall --python "%PYTHON_EXE%" -y %PACKAGE_TARGET%
    ) else (
        "%PYTHON_EXE%" -m pip uninstall -y %PACKAGE_TARGET%
    )
    echo.
    echo [3/3] ✅ Uninstallation completed. All packages removed.
    echo.
    echo Press any key to close.
    pause >nul
)
"""
    script_path.write_text(content, encoding="utf-8")
    return script_path


def spawn_external_updater(action: str, packages: List[str]) -> bool:
    """
    Launch the external updater in a detached console window and terminate the current process.
    This guarantees 0ms lock contention because current mws.exe exits before uv/pip attempts to overwrite it.
    """
    if sys.platform != "win32":
        return False

    script_path = ensure_external_updater_script()
    pkg_str = " ".join(f'"{p}"' for p in packages)
    caller_pid = str(os.getpid())
    python_exe = str(Path(sys.executable).resolve())

    print("\n" + "=" * 76)
    print(f"🚀 Handing off {action} to external updater service: {script_path}")
    print(f"🚪 Exiting current mws process (PID: {caller_pid}) to release executable file locks...")
    print("=" * 76 + "\n")

    # Launch detached CMD window
    cmd = f'start "mcp-win-stdio Updater" "{script_path}" {action} {caller_pid} "{python_exe}" {pkg_str}'
    try:
        subprocess.Popen(
            cmd,
            shell=True,
            creationflags=subprocess.CREATE_NEW_CONSOLE,
        )
        # Cleanly exit current process
        sys.exit(0)
    except Exception as e:
        sys.stderr.write(f"Failed to launch external updater: {e}\n")
        return False
