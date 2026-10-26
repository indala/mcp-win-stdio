"""
Installer and transparent configuration engine for Claude Desktop and Claude Code CLI.
"""

import importlib.metadata
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from mcp_win_stdio.core.discovery import get_server_info


def get_installed_mws_packages() -> List[str]:
    """
    Find all installed packages in the active Python environment that belong to mcp-win-stdio.
    Matches 'mcp-win-stdio' and any 'mcp-win-stdio-*' subpackages.
    """
    installed = set()
    try:
        for dist in importlib.metadata.distributions():
            raw_name = dist.metadata.get("Name")
            if not raw_name:
                continue
            name = raw_name.lower().replace("_", "-")
            if name == "mcp-win-stdio" or name.startswith("mcp-win-stdio-"):
                installed.add(name)
    except Exception:
        pass
    return sorted(installed)


def get_package_manager_cmd(action: str) -> Optional[List[str]]:
    """
    Determine the best available package manager command (uv pip or python -m pip)
    for installing, upgrading, or uninstalling packages in the current environment.
    action: 'install', 'install --upgrade', or 'uninstall'
    """
    python_exe = str(Path(sys.executable).resolve())

    # 1. Prefer uv if installed on system
    uv_bin = shutil.which("uv")
    if uv_bin:
        if action == "uninstall":
            return [uv_bin, "pip", "uninstall", "--python", python_exe, "-y"]
        elif "upgrade" in action:
            return [uv_bin, "pip", "install", "--python", python_exe, "--upgrade"]
        else:
            return [uv_bin, "pip", "install", "--python", python_exe]

    # 2. Fallback to python -m pip if pip module exists
    try:
        check = subprocess.run(
            [sys.executable, "-m", "pip", "--version"],
            capture_output=True,
            text=True,
            check=False,
        )
        if check.returncode == 0:
            if action == "uninstall":
                return [sys.executable, "-m", "pip", "uninstall", "-y"]
            elif "upgrade" in action:
                return [sys.executable, "-m", "pip", "install", "--upgrade"]
            else:
                return [sys.executable, "-m", "pip", "install"]
    except Exception:
        pass

    return None


def get_claude_desktop_config_path() -> Optional[Path]:
    """Find claude_desktop_config.json on Windows."""
    appdata = os.environ.get("APPDATA")
    if appdata:
        p = Path(appdata) / "Claude" / "claude_desktop_config.json"
        if p.exists():
            return p
    # Fallback to standard Windows location
    default_p = Path.home() / "AppData" / "Roaming" / "Claude" / "claude_desktop_config.json"
    return default_p if default_p.exists() else None


def get_claude_cli_config_path() -> Optional[Path]:
    """Find .claude.json on Windows."""
    p = Path.home() / ".claude.json"
    return p if p.exists() else None


def get_server_exec_args(server_name: str) -> Tuple[str, List[str]]:
    """Return guaranteed absolute executable path and arguments for a given server."""
    srv = get_server_info(server_name)
    if not srv:
        raise ValueError(f"Server '{server_name}' not found.")

    # 1. Prefer absolute path to mws executable if present on PATH
    mws_bin = shutil.which("mws")
    if mws_bin and Path(mws_bin).is_file():
        if server_name in ("server", "mws"):
            return str(Path(mws_bin).resolve()).replace("\\", "/"), ["server"]
        return str(Path(mws_bin).resolve()).replace("\\", "/"), ["run", server_name]

    # 2. Fallback to absolute Python interpreter executable
    python_exe = str(Path(sys.executable).resolve()).replace("\\", "/")
    if srv["is_builtin"]:
        if server_name in ("server", "mws"):
            args = ["-m", "mcp_win_stdio.server"]
        else:
            args = ["-m", "mcp_win_stdio.cli", "run", server_name]
    else:
        args = [srv["path"].replace("\\", "/")]

    return python_exe, args


def generate_claude_desktop_snippet(server_name: str, env_vars: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """Generate the JSON dictionary block for Claude Desktop."""
    python_exe, args = get_server_exec_args(server_name)
    block: Dict[str, Any] = {
        "command": python_exe,
        "args": args,
    }
    if env_vars:
        block["env"] = env_vars
    return block


def generate_claude_cli_command(server_name: str, env_vars: Optional[Dict[str, str]] = None) -> str:
    """Generate the exact `claude mcp add` terminal command."""
    python_exe, args = get_server_exec_args(server_name)
    env_flags = ""
    if env_vars:
        env_flags = " ".join([f'-e {k}="{v}"' for k, v in env_vars.items()]) + " "
    return f'claude mcp add -s user {env_flags}{server_name} -- "{python_exe}" {" ".join(args)}'


def unlock_running_executable() -> Optional[Path]:
    """
    On Windows, running executables (.exe) are locked by the OS kernel against deletion/overwriting.
    However, Windows NTFS allows a running executable to be RENAMED within the same directory.
    This helper safely renames mws.exe to mws.exe.deleteme_<pid> so that pip/uv can
    install or uninstall the new executable without hitting 'Access is denied (os error 5)'.
    """
    if sys.platform != "win32":
        return None

    candidates: List[Path] = []
    # 1. which mws
    w = shutil.which("mws")
    if w:
        candidates.append(Path(w).resolve())
    # 2. Python Scripts directory
    py_dir = Path(sys.executable).resolve().parent
    candidates.append(py_dir / "Scripts" / "mws.exe")
    candidates.append(py_dir / "mws.exe")
    # 3. sys.argv[0]
    if sys.argv and sys.argv[0].lower().endswith(".exe"):
        candidates.append(Path(sys.argv[0]).resolve())

    for exe_path in candidates:
        if exe_path.exists() and exe_path.is_file():
            try:
                old_path = exe_path.with_name(f"{exe_path.name}.deleteme_{os.getpid()}")
                if old_path.exists():
                    try:
                        old_path.unlink()
                    except Exception:
                        pass
                exe_path.rename(old_path)
                return old_path
            except Exception:
                pass
    return None


def cleanup_old_executables() -> None:
    """Clean up any leftover .deleteme_* or .old files from previous updates."""
    if sys.platform != "win32":
        return
    py_dir = Path(sys.executable).resolve().parent
    search_dirs = [py_dir / "Scripts", py_dir]
    for d in search_dirs:
        if d.exists():
            for p in d.glob("mws.exe.deleteme_*"):
                try:
                    p.unlink()
                except Exception:
                    pass
            old_p = d / "mws.exe.old"
            if old_p.exists():
                try:
                    old_p.unlink()
                except Exception:
                    pass


def schedule_detached_deletion(target_file: Path) -> None:
    """Schedule a file to be deleted 2 seconds after process termination on Windows."""
    if sys.platform != "win32" or not target_file.exists():
        return
    cmd = f'timeout /t 2 /nobreak >nul & if exist "{target_file}" del /f /q "{target_file}"'
    try:
        flags = 0x00000008 | 0x08000000  # DETACHED_PROCESS | CREATE_NO_WINDOW
        subprocess.Popen(["cmd.exe", "/c", cmd], creationflags=flags, close_fds=True)
    except Exception:
        pass


def install_pip_dependencies(packages: List[str], upgrade: bool = False) -> Tuple[bool, str]:
    """Install required Python packages using the best available package manager (uv or pip)."""
    if not packages:
        return True, "No extra packages required."

    action = "install --upgrade" if upgrade else "install"
    cmd_base = get_package_manager_cmd(action)
    if not cmd_base:
        return (
            False,
            f"Neither 'uv' nor 'pip' could be found to install: {', '.join(packages)}\n"
            f"Please run manually:\n    pip install {' '.join(packages)}",
        )

    mgr_name = Path(cmd_base[0]).stem
    print(f"\n==> 📦 Installing packages via {mgr_name}: {', '.join(packages)}...")
    cmd = cmd_base + packages

    # On Windows, if updating mcp-win-stdio or mws, unlock the running executable first
    renamed_exe: Optional[Path] = None
    if upgrade and any("mcp-win-stdio" in p for p in packages):
        renamed_exe = unlock_running_executable()

    try:
        res = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if res.returncode == 0:
            if renamed_exe:
                schedule_detached_deletion(renamed_exe)
            cleanup_old_executables()
            return True, "Dependencies installed successfully."
        else:
            # If install failed and original exe wasn't replaced, restore backup
            if renamed_exe and renamed_exe.exists():
                orig_exe = renamed_exe.with_name("mws.exe")
                if not orig_exe.exists():
                    try:
                        renamed_exe.rename(orig_exe)
                    except Exception:
                        pass
            err_msg = res.stderr or res.stdout
            if "os error 5" in err_msg or "Access is denied" in err_msg:
                err_msg += (
                    "\n\n💡 Tip: To bypass Windows executable file locking, run using python directly:\n"
                    f"    python -m mcp_win_stdio update\n"
                    f"    # or\n"
                    f'    uv pip install --upgrade "{packages[0]}"'
                )
            return False, f"Package manager error:\n{err_msg}"
    except Exception as e:
        return False, f"Failed to run installer: {str(e)}"


def safe_apply_to_desktop(server_name: str, env_vars: Optional[Dict[str, str]] = None) -> Tuple[bool, str]:
    """Safely write configuration into Claude Desktop config with backup."""
    config_path = get_claude_desktop_config_path()
    if not config_path:
        # Create directory if missing
        appdata = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        target_dir = Path(appdata) / "Claude"
        target_dir.mkdir(parents=True, exist_ok=True)
        config_path = target_dir / "claude_desktop_config.json"
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump({"mcpServers": {}}, f, indent=2)

    # Backup existing configuration
    try:
        shutil.copy2(config_path, config_path.with_suffix(".json.bak"))
    except Exception:
        pass

    try:
        data = {}
        if config_path.exists():
            with open(config_path, "r", encoding="utf-8") as f:
                try:
                    data = json.load(f)
                except Exception:
                    data = {}

        if "mcpServers" not in data or not isinstance(data["mcpServers"], dict):
            data["mcpServers"] = {}

        data["mcpServers"][server_name] = generate_claude_desktop_snippet(server_name, env_vars)

        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

        return True, f"Successfully written to Claude Desktop config ({config_path})"
    except Exception as e:
        return False, f"Failed to update Claude Desktop config: {str(e)}"


def safe_apply_to_cli(server_name: str, env_vars: Optional[Dict[str, str]] = None) -> Tuple[bool, str]:
    """Safely register into Claude Code CLI using the official `claude mcp add` command."""
    python_exe, args = get_server_exec_args(server_name)
    cmd_str = generate_claude_cli_command(server_name, env_vars)

    cmd = ["claude", "mcp", "add", "-s", "user"]
    if env_vars:
        for k, v in env_vars.items():
            cmd.extend(["-e", f"{k}={v}"])
    cmd.extend([server_name, "--", python_exe] + args)

    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if res.returncode == 0:
            return True, f"Successfully registered '{server_name}' in Claude Code CLI via `claude mcp add`"
        else:
            err = res.stderr or res.stdout
            return False, f"`claude mcp add` exited with error: {err.strip()}\nPlease run manually:\n    {cmd_str}"
    except FileNotFoundError:
        return False, f"Claude Code CLI (`claude`) not found on PATH. Please run manually:\n    {cmd_str}"
    except Exception as e:
        return False, f"Failed to execute `claude mcp add`: {str(e)}\nPlease run manually:\n    {cmd_str}"


def remove_server_from_desktop(server_name: str) -> Tuple[bool, str]:
    """Remove server from Claude Desktop config."""
    config_path = get_claude_desktop_config_path()
    if not config_path or not config_path.exists():
        return False, "Claude Desktop config not found."
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if "mcpServers" in data and server_name in data["mcpServers"]:
            del data["mcpServers"][server_name]
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            return True, f"Removed '{server_name}' from Claude Desktop config."
        return True, f"'{server_name}' was not present in Claude Desktop config."
    except Exception as e:
        return False, f"Error removing server: {str(e)}"


def remove_server_from_cli(server_name: str) -> Tuple[bool, str]:
    """Remove server from Claude CLI using the official `claude mcp remove` command."""
    try:
        res = subprocess.run(
            ["claude", "mcp", "remove", "-s", "user", server_name],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if res.returncode == 0:
            return True, f"Removed '{server_name}' from Claude Code CLI."
        else:
            return False, f"Could not remove '{server_name}': {res.stderr or res.stdout}"
    except FileNotFoundError:
        return False, "Claude Code CLI (`claude`) not found on PATH."
    except Exception as e:
        return False, f"Failed to remove from Claude CLI: {str(e)}"


def uninstall_pip_packages(packages: List[str]) -> Tuple[bool, str]:
    """Uninstall Python packages using the best available package manager (uv or pip)."""
    if not packages:
        return True, "No packages specified to uninstall."

    cmd_base = get_package_manager_cmd("uninstall")
    if not cmd_base:
        return (
            False,
            f"Neither 'uv' nor 'pip' could be found to uninstall: {', '.join(packages)}\n"
            f"Please run manually:\n    pip uninstall -y {' '.join(packages)}",
        )

    mgr_name = Path(cmd_base[0]).stem
    print(f"\n==> 🧹 Removing packages via {mgr_name}: {', '.join(packages)}...")
    cmd = cmd_base + packages

    # On Windows, if uninstalling mcp-win-stdio (self), unlock running executable first
    renamed_exe: Optional[Path] = None
    if any(p == "mcp-win-stdio" for p in packages):
        renamed_exe = unlock_running_executable()

    try:
        res = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if res.returncode == 0:
            if renamed_exe:
                schedule_detached_deletion(renamed_exe)
            return True, "Packages uninstalled successfully."
        else:
            if renamed_exe and renamed_exe.exists():
                orig_exe = renamed_exe.with_name("mws.exe")
                if not orig_exe.exists():
                    try:
                        renamed_exe.rename(orig_exe)
                    except Exception:
                        pass
            err_msg = res.stderr or res.stdout
            if "os error 5" in err_msg or "Access is denied" in err_msg:
                err_msg += (
                    "\n\n💡 Tip: To bypass Windows executable file locking during uninstallation, run:\n"
                    f"    python -m mcp_win_stdio uninstall self\n"
                    f"    # or\n"
                    f"    uv pip uninstall {' '.join(packages)} -y"
                )
            return False, f"Package manager uninstall error:\n{err_msg}"
    except Exception as e:
        return False, f"Failed to run package uninstall: {str(e)}"
