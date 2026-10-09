"""
CLI entry point for mcp-win-stdio-ssh.
"""

import argparse
import shutil
import sys
import time
from pathlib import Path

# Ensure Windows console uses UTF-8 without crashing on cp1252
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from mcp_win_stdio.ssh import __version__
from mcp_win_stdio.ssh.connection import (
    SYSTEM_SSH_CONFIG,
    get_active_host_name,
    get_all_registered_hosts,
    get_cached_or_connect,
    resolve_host_info,
)
from mcp_win_stdio.ssh.guide import print_ssh_guide
from mcp_win_stdio.ssh.server import mcp


def cmd_run(args: argparse.Namespace) -> None:
    """Run SSH MCP server over stdio."""
    mcp.run()


def cmd_doctor(args: argparse.Namespace) -> None:
    """Run diagnostic checks on SSH drivers, Windows OpenSSH service, keys, and configs."""
    print(f"\n=== mcp-win-stdio-ssh Doctor Diagnostic (v{__version__}) ===\n")
    print(f"[OK] Python Runtime: {sys.version.split()[0]} ({sys.executable})")

    # 1. Driver Checks
    for dep in ("mcp", "paramiko", "cryptography"):
        try:
            mod = __import__(dep)
            ver = getattr(mod, "__version__", "installed")
            print(f"[OK] Python Module: {dep:<14} (v{ver})")
        except ImportError:
            print(f"[FAIL] Python Module: {dep:<14} (MISSING - run `pip install {dep}`)")

    # 2. OpenSSH Windows client check
    ssh_bin = shutil.which("ssh")
    if ssh_bin:
        print(f"[OK] System SSH CLI: {ssh_bin}")
    else:
        print("[INFO] System SSH CLI: Not on PATH (Optional: Paramiko native SSH client active)")

    # 3. SSH Config & Keys
    ssh_dir = Path.home() / ".ssh"
    if ssh_dir.is_dir():
        print(f"[OK] SSH Directory: {ssh_dir}")
        if SYSTEM_SSH_CONFIG.exists():
            print(f"[OK] SSH Config:    {SYSTEM_SSH_CONFIG}")
        else:
            print("[INFO] SSH Config:   No ~/.ssh/config found (can use add_host or create config)")

        keys = [f.name for f in ssh_dir.iterdir() if f.is_file() and not f.name.endswith(".pub") and "id_" in f.name]
        if keys:
            print(f"[OK] Found Keys:     {', '.join(keys)}")
        else:
            print("[INFO] Found Keys:    No default id_* keys found in ~/.ssh/")
    else:
        print(f"[INFO] SSH Directory: {ssh_dir} not created yet.")

    # 4. Registered Hosts
    hosts = get_all_registered_hosts()
    active = get_active_host_name()
    print(f"\n--- Registered Hosts ({len(hosts)}) ---")
    for name, h in hosts.items():
        is_act = " (ACTIVE DEFAULT)" if name == active else ""
        print(f" • {name:<16} -> {h.get('user')}@{h.get('hostname')}:{h.get('port')} [{h.get('source')}]{is_act}")

    print("\nDiagnostic complete.\n")


def cmd_test(args: argparse.Namespace) -> None:
    """Test SSH connectivity and latency to configured hosts."""
    target = args.host
    hosts = get_all_registered_hosts()

    if not hosts and not target:
        print("\n[!] No SSH hosts configured. Use 'add_host' tool or configure ~/.ssh/config.\n")
        return

    targets = [target] if target else list(hosts.keys())

    print(f"\n=== Testing SSH Connectivity ({len(targets)} host{'s' if len(targets) > 1 else ''}) ===\n")

    for h_name in targets:
        try:
            h_info = resolve_host_info(h_name)
            t_start = time.time()
            client = get_cached_or_connect(h_info["name"], timeout=10)
            lat_ms = round((time.time() - t_start) * 1000, 2)

            stdin, stdout, stderr = client.exec_command("uname -srmo 2>/dev/null || ver", timeout=5)
            os_info = stdout.read().decode("utf-8", errors="replace").strip()

            print(
                f" [OK] {h_name:<16} -> {h_info.get('user')}@{h_info.get('hostname')}:{h_info.get('port')} ({lat_ms}ms) | {os_info}"
            )
        except Exception as e:
            print(f" [FAIL] {h_name:<14} -> Error: {e}")

    print("\nTest complete.\n")


def cmd_guide(args: argparse.Namespace) -> None:
    """Print guide and prompt recipes."""
    print_ssh_guide()


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="mcp-win-stdio-ssh",
        description="Unified Multi-SSH Connection & Remote Management MCP Server CLI",
    )
    parser.add_argument("--version", "-v", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    sub_guide = subparsers.add_parser("guide", help="View usage guide and recipes")
    sub_guide.set_defaults(func=cmd_guide)

    sub_doctor = subparsers.add_parser("doctor", help="Check SSH configuration and drivers")
    sub_doctor.set_defaults(func=cmd_doctor)

    sub_test = subparsers.add_parser("test", help="Test connectivity to configured hosts")
    sub_test.add_argument("host", nargs="?", help="Specific host name to test")
    sub_test.set_defaults(func=cmd_test)

    sub_run = subparsers.add_parser("run", help="Run SSH MCP server over stdio")
    sub_run.set_defaults(func=cmd_run)

    args = parser.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        # Default action is run
        cmd_run(args)


if __name__ == "__main__":
    main()
