"""
Windows Environment and PATH management utilities for mcp-win-stdio.
Ensures Python Scripts and binary directories are registered in Windows User PATH.
"""

import ctypes
import os
from pathlib import Path
import site
import sys
import sysconfig
from typing import List, Optional, Tuple

if sys.platform == "win32":
    import winreg


def get_candidate_script_dirs() -> List[Path]:
    """Return all directories where Python CLI scripts (mws.exe) might be installed."""
    dirs = []

    # 1. Standard sysconfig scripts directory
    try:
        s_dir = sysconfig.get_path("scripts")
        if s_dir:
            dirs.append(Path(s_dir).resolve())
    except Exception:
        pass

    # 2. Python executable parent Scripts directory
    try:
        py_scripts = Path(sys.executable).parent / "Scripts"
        if py_scripts.exists():
            resolved = py_scripts.resolve()
            if resolved not in dirs:
                dirs.append(resolved)
    except Exception:
        pass

    # 3. Python 3.14+ Windows launcher / AppData local bin directory
    try:
        local_bin = Path.home() / "AppData" / "Local" / "Python" / "bin"
        if local_bin.exists():
            resolved = local_bin.resolve()
            if resolved not in dirs:
                dirs.append(resolved)
    except Exception:
        pass

    # 4. User base scripts directory (e.g. %APPDATA%\Python\Python31x\Scripts)
    try:
        user_base = site.getuserbase()
        if user_base:
            user_scripts = Path(user_base) / "Scripts"
            if user_scripts.exists():
                resolved = user_scripts.resolve()
                if resolved not in dirs:
                    dirs.append(resolved)
    except Exception:
        pass

    return dirs


def get_user_registry_path() -> str:
    """Get current User PATH from HKCU\\Environment."""
    if sys.platform != "win32":
        return os.environ.get("PATH", "")

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Environment", 0, winreg.KEY_READ) as key:
            val, _ = winreg.QueryValueEx(key, "Path")
            return val or ""
    except FileNotFoundError:
        return ""
    except Exception:
        return ""


def is_in_path(directory: Path) -> bool:
    """Check if directory is present in current process PATH or Windows User Registry PATH."""
    norm_target = os.path.normcase(os.path.normpath(str(directory)))

    # Check process PATH
    env_path = os.environ.get("PATH", "")
    for p in env_path.split(os.pathsep):
        if p.strip() and os.path.normcase(os.path.normpath(p.strip())) == norm_target:
            return True

    # Check Windows Registry User PATH
    reg_path = get_user_registry_path()
    for p in reg_path.split(";"):
        if p.strip() and os.path.normcase(os.path.normpath(p.strip())) == norm_target:
            return True

    return False


def add_dir_to_user_path(directory: Path) -> Tuple[bool, str]:
    """Safely append a directory to HKCU\\Environment\\Path and broadcast change."""
    if sys.platform != "win32":
        return False, "PATH modification is only supported on Windows."

    norm_dir = os.path.normpath(str(directory))

    if is_in_path(directory):
        return True, f"'{norm_dir}' is already present in PATH."

    try:
        current_user_path = get_user_registry_path().strip(";")
        new_user_path = f"{current_user_path};{norm_dir}" if current_user_path else norm_dir

        # Write to User Environment registry
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Environment", 0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, "Path", 0, winreg.REG_EXPAND_SZ, new_user_path)

        # Update current process PATH
        os.environ["PATH"] = f"{os.environ.get('PATH', '')}{os.pathsep}{norm_dir}"

        # Broadcast WM_SETTINGCHANGE so other running/new apps and shells get the new PATH immediately
        HWND_BROADCAST = 0xFFFF
        WM_SETTINGCHANGE = 0x001A
        SMTO_ABORTIFHUNG = 0x0002
        result = ctypes.c_ulong()
        ctypes.windll.user32.SendMessageTimeoutW(
            HWND_BROADCAST,
            WM_SETTINGCHANGE,
            0,
            "Environment",
            SMTO_ABORTIFHUNG,
            1000,
            ctypes.byref(result),
        )

        return True, f"Successfully added '{norm_dir}' to Windows User PATH."
    except Exception as e:
        return False, f"Failed to update Windows User PATH: {str(e)}"


def check_and_prompt_path_setup(auto_accept: bool = False) -> List[Path]:
    """
    Check if Python Scripts / bin directories are in PATH.
    If missing, prompts the user for permission to add them.
    Returns list of newly added paths.
    """
    candidate_dirs = get_candidate_script_dirs()
    missing_dirs = [d for d in candidate_dirs if not is_in_path(d) and d.exists()]

    if not missing_dirs:
        return []

    added = []
    print("\n" + "-" * 72)
    print("⚠️  [PATH Check] Python Scripts / bin directory is not in your Windows PATH:")
    for d in missing_dirs:
        print(f"   • {d}")
    print("   Without this, 'mws' command cannot be run directly in new terminals.")
    print("-" * 72)

    do_add = False
    if auto_accept:
        do_add = True
    elif sys.stdin.isatty():
        choice = input("\n👉 Would you like mws to automatically add it to your Windows User PATH? [Y/n]: ").strip().lower()
        if choice not in ("n", "no"):
            do_add = True

    if do_add:
        for d in missing_dirs:
            ok, msg = add_dir_to_user_path(d)
            if ok:
                print(f"  [OK] {msg}")
                added.append(d)
            else:
                print(f"  [WARN] {msg}")
        print("  💡 Tip: Open a new terminal window for changes to take full effect.\n")
    else:
        print("  [INFO] Skipped PATH modification. You can run 'mws fix-path' anytime.\n")

    return added
