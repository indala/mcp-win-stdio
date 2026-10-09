#!/usr/bin/env python3
"""
Unified Multi-SSH Connection & Remote System Management MCP Server for mcp-win-stdio.
Provides sticky multi-host pooling, command execution, PTY sessions, SFTP operations,
service/process management, and local port forwarding tunnels.
"""

import json
import os
import re
import shlex
import time
from typing import Any, Dict, Literal, Optional, Union

try:
    from mcp.server.mcpserver import MCPServer as FastMCP
except (ImportError, ModuleNotFoundError):
    from mcp.server.fastmcp import FastMCP

import paramiko
from mcp_win_stdio.ssh.connection import (
    close_connection,
    get_active_host_name,
    get_all_registered_hosts,
    get_cached_or_connect,
    get_pool_status,
    load_ssh_hosts,
    resolve_host_info,
    save_ssh_hosts,
    set_active_host_name,
)
from mcp_win_stdio.ssh.pty_session import (
    close_pty_session,
    list_pty_sessions,
    read_pty_buffer,
    send_to_pty,
    start_pty_session,
    strip_ansi,
)
from mcp_win_stdio.ssh.sftp_ops import (
    download_path,
    list_remote_directory,
    read_remote_text_file,
    remove_remote_path,
    stat_remote_path,
    upload_path,
    write_remote_text_file,
)
from mcp_win_stdio.ssh.tunnels import (
    close_tunnel,
    list_active_tunnels,
    open_local_tunnel,
)

mcp = FastMCP("ssh-mcp")


# ==============================================================================
# Helper Functions
# ==============================================================================


def _format_ssh_error(e: Exception, host: Optional[str] = None, command: Optional[str] = None) -> Dict[str, Any]:
    """Format SSH exception into clean, structured diagnostics with helpful advice."""
    error_payload = {
        "error": True,
        "error_type": type(e).__name__,
        "message": str(e).strip(),
        "host": host or get_active_host_name() or "unknown",
    }
    if command:
        error_payload["command_snippet"] = command[:150] + ("..." if len(command) > 150 else "")

    msg = str(e).lower()
    if "authentication failed" in msg or "permission denied (publickey)" in msg:
        error_payload["suggestion"] = (
            "Authentication failed: Check if the SSH private key path is correct, "
            "the key is added to ssh-agent, or provide password/passphrase in add_host."
        )
    elif "connection refused" in msg:
        error_payload["suggestion"] = (
            "Connection refused: Ensure SSH server (sshd) is running on the target port and firewall allows traffic."
        )
    elif "timed out" in msg or "timeout" in msg:
        error_payload["suggestion"] = (
            "Connection timed out: Check if the remote host IP/hostname is reachable and not blocked by a security group."
        )
    elif "not in known_hosts" in msg:
        error_payload["suggestion"] = "Host key verification failed. The host key might have changed."

    return error_payload


def _truncate_output(
    text: str,
    max_lines: int = 250,
    max_chars: int = 20000,
    notice_context: str = "output",
) -> Dict[str, Any]:
    """Token-safe truncation helper for command output and text streams."""
    lines = text.splitlines()
    total_lines = len(lines)
    total_chars = len(text)
    truncated = False

    if total_lines > max_lines:
        lines = lines[:max_lines]
        truncated = True

    result_text = "\n".join(lines)
    if len(result_text) > max_chars:
        result_text = result_text[:max_chars]
        truncated = True

    res = {
        "content": result_text,
        "total_lines": total_lines,
        "returned_lines": len(lines),
        "total_chars": total_chars,
        "returned_chars": len(result_text),
        "truncated": truncated,
    }
    if truncated:
        res["notice"] = (
            f"... [TRUNCATED: Showing {len(lines)} of {total_lines} lines ({len(result_text)} of {total_chars} chars) "
            f"to protect agent context window. Narrow your command, use grep, or view logs via ssh_tail_logs / sftp_read_file] ..."
        )
    return res


def _run_exec_channel(
    client: paramiko.SSHClient,
    command: str,
    cwd: Optional[str] = None,
    env: Optional[Dict[str, str]] = None,
    timeout: int = 60,
    max_lines: int = 250,
    max_chars: int = 20000,
) -> Dict[str, Any]:
    """Execute command over SSH channel with timeout, cwd, environment variables, and token-safe output truncation."""
    cmd = command
    if cwd:
        cmd = f"cd {shlex.quote(cwd)} && {cmd}"

    if env:
        exports = " ".join([f"{k}={shlex.quote(str(v))}" for k, v in env.items()])
        cmd = f"export {exports} && {cmd}"

    start_t = time.time()
    stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout, get_pty=False)

    # Read output
    out_str = stdout.read().decode("utf-8", errors="replace")
    err_str = stderr.read().decode("utf-8", errors="replace")
    exit_code = stdout.channel.recv_exit_status()
    duration_ms = round((time.time() - start_t) * 1000, 2)

    capped_out = _truncate_output(out_str.strip(), max_lines=max_lines, max_chars=max_chars, notice_context="stdout")
    capped_err = _truncate_output(err_str.strip(), max_lines=100, max_chars=8000, notice_context="stderr")

    res = {
        "command": command,
        "exit_code": exit_code,
        "duration_ms": duration_ms,
        "stdout": capped_out["content"],
        "stderr": capped_err["content"],
        "is_success": exit_code == 0,
        "truncated": capped_out["truncated"] or capped_err["truncated"],
    }
    if capped_out.get("notice"):
        res["notice"] = capped_out["notice"]
    return res


# ==============================================================================
# 1. Host & Connection Management Tools
# ==============================================================================


@mcp.tool()
def list_hosts() -> Dict[str, Any]:
    """
    List all configured and discovered SSH hosts (from ~/.ssh/config, persistent storage, and environment),
    indicating the active sticky host, user, hostname, port, and connection status.
    """
    all_hosts = get_all_registered_hosts()
    active_name = get_active_host_name()

    pool_status = {item["name"]: item for item in get_pool_status()}

    results = []
    for name, info in all_hosts.items():
        is_active = name == active_name
        in_pool = pool_status.get(name, {})

        results.append(
            {
                "name": name,
                "hostname": info.get("hostname", "localhost"),
                "user": info.get("user", "root"),
                "port": info.get("port", 22),
                "keyPath": info.get("key_path"),
                "hasPassword": bool(info.get("password")),
                "jumpHost": info.get("jump_host") or info.get("proxyjump"),
                "source": info.get("source", "config"),
                "isActiveDefault": is_active,
                "poolConnection": "connected" if in_pool.get("isActive") else "idle",
            }
        )

    return {
        "activeHost": active_name,
        "totalHosts": len(results),
        "hosts": results,
    }


@mcp.tool()
def use_host(host: str) -> Dict[str, Any]:
    """
    Switch the active default SSH host context. All subsequent SSH, SFTP, and diagnostic tool calls
    will target this host automatically when host is not specified.

    Args:
        host: Host alias, hostname, or user@hostname:port to switch to.
    """
    try:
        info = resolve_host_info(host)
        target_name = info["name"]
        set_active_host_name(target_name)
        return {
            "success": True,
            "message": f"Active SSH host switched to '{target_name}' ({info.get('user')}@{info.get('hostname')}:{info.get('port')}).",
            "activeHost": target_name,
            "hostInfo": {
                "hostname": info.get("hostname"),
                "user": info.get("user"),
                "port": info.get("port"),
                "source": info.get("source"),
            },
        }
    except Exception as e:
        return _format_ssh_error(e, host=host)


@mcp.tool()
def add_host(
    name: str,
    hostname: str,
    user: Optional[str] = None,
    port: int = 22,
    key_path: Optional[str] = None,
    password: Optional[str] = None,
    passphrase: Optional[str] = None,
    jump_host: Optional[str] = None,
    description: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Register and persist a new SSH host configuration to ~/.mcp-win-stdio/ssh_hosts.json.

    Args:
        name: Unique alias name for the host (e.g. 'prod-web-01', 'db-cluster', 'staging').
        hostname: IP address or domain name of the remote server.
        user: SSH login username (defaults to current Windows username or root).
        port: SSH port (default: 22).
        key_path: Path to private key file (e.g. ~/.ssh/id_rsa, C:/Users/.../.ssh/id_ed25519).
        password: Plaintext password (optional, key-based auth preferred).
        passphrase: Key passphrase if private key is encrypted.
        jump_host: Optional bastion/jump host alias to route connection through.
        description: Friendly description of the server role.
    """
    clean_name = name.strip()
    clean_host = hostname.strip()
    clean_user = user.strip() if user else os.environ.get("USERNAME", "root")

    saved = load_ssh_hosts()
    hosts_dict = saved.get("hosts", {})

    host_entry = {
        "hostname": clean_host,
        "user": clean_user,
        "port": port,
        "key_path": key_path.strip() if key_path else None,
        "password": password if password else None,
        "passphrase": passphrase if passphrase else None,
        "jump_host": jump_host.strip() if jump_host else None,
        "description": description.strip() if description else None,
    }

    hosts_dict[clean_name] = host_entry
    saved["hosts"] = hosts_dict

    if not saved.get("active_host"):
        saved["active_host"] = clean_name

    save_ssh_hosts(saved)

    return {
        "success": True,
        "message": f"Host '{clean_name}' ({clean_user}@{clean_host}:{port}) registered successfully.",
        "host": clean_name,
        "details": host_entry,
    }


@mcp.tool()
def remove_host(name: str) -> Dict[str, Any]:
    """
    Remove a saved SSH host configuration from ~/.mcp-win-stdio/ssh_hosts.json.

    Args:
        name: Name of the host to delete.
    """
    clean_name = name.strip()
    saved = load_ssh_hosts()
    hosts_dict = saved.get("hosts", {})

    if clean_name not in hosts_dict:
        return {
            "error": True,
            "message": f"Host '{clean_name}' not found in saved hosts. (Note: Hosts defined in ~/.ssh/config cannot be deleted via MCP).",
        }

    del hosts_dict[clean_name]
    saved["hosts"] = hosts_dict
    new_active = saved.get("active_host")
    if new_active == clean_name:
        new_active = next(iter(hosts_dict.keys())) if hosts_dict else None
        saved["active_host"] = new_active

    save_ssh_hosts(saved)
    set_active_host_name(new_active)
    close_connection(clean_name)

    return {
        "success": True,
        "message": f"Host '{clean_name}' removed successfully.",
        "newActiveHost": new_active,
    }


@mcp.tool()
def test_host(host: Optional[str] = None) -> Dict[str, Any]:
    """
    Test SSH connectivity, authentication, latency, and retrieve remote OS info.

    Args:
        host: Host alias, hostname, or user@hostname:port (defaults to active host).
    """
    try:
        host_info = resolve_host_info(host)
        start_t = time.time()
        client = get_cached_or_connect(host_info["name"])
        latency_ms = round((time.time() - start_t) * 1000, 2)

        # Quick uname / os check
        stdin, stdout, stderr = client.exec_command("uname -srmo 2>/dev/null || ver", timeout=5)
        os_info = stdout.read().decode("utf-8", errors="replace").strip()

        return {
            "success": True,
            "status": "connected",
            "host": host_info["name"],
            "remoteTarget": f"{host_info.get('user')}@{host_info.get('hostname')}:{host_info.get('port')}",
            "latency_ms": latency_ms,
            "remoteOS": os_info or "Unknown OS",
            "message": f"Successfully connected to '{host_info['name']}' in {latency_ms}ms.",
        }
    except Exception as e:
        return _format_ssh_error(e, host=host)


@mcp.tool()
def list_active_connections() -> Dict[str, Any]:
    """List all currently active, live SSH sessions in the connection pool."""
    active_conns = get_pool_status()
    return {
        "activeCount": len(active_conns),
        "connections": active_conns,
    }


@mcp.tool()
def disconnect_host(host: Optional[str] = None) -> Dict[str, Any]:
    """
    Close and disconnect the SSH connection for a specific host from the connection pool.

    Args:
        host: Host name to disconnect (or active host if omitted).
    """
    closed = close_connection(host)
    name = host or get_active_host_name() or "active host"
    return {
        "success": closed,
        "message": f"Disconnected connection for '{name}'." if closed else f"No active connection found for '{name}'.",
    }


# ==============================================================================
# 2. Remote Command & Script Execution Tools
# ==============================================================================


@mcp.tool()
def ssh_exec(
    command: str,
    host: Optional[str] = None,
    cwd: Optional[str] = None,
    timeout: int = 60,
    env: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """
    Execute a non-interactive shell command on the remote SSH host.
    Returns exit code, stdout, stderr, execution duration, and structured results.

    Args:
        command: The shell command line string to run.
        host: Target SSH host (defaults to active host).
        cwd: Remote working directory to cd into before executing.
        timeout: Execution timeout in seconds (default: 60).
        env: Optional environment variables dictionary to export.
    """
    try:
        host_info = resolve_host_info(host)
        client = get_cached_or_connect(host_info["name"])
        res = _run_exec_channel(client, command, cwd=cwd, env=env, timeout=timeout)
        res["host"] = host_info["name"]
        return res
    except Exception as e:
        return _format_ssh_error(e, host=host, command=command)


@mcp.tool()
def ssh_exec_sudo(
    command: str,
    sudo_password: Optional[str] = None,
    host: Optional[str] = None,
    timeout: int = 60,
) -> Dict[str, Any]:
    """
    Execute a command with elevated sudo privileges, automatically handling the sudo password prompt if needed.

    Args:
        command: Command to execute with sudo (e.g. 'systemctl restart nginx', 'apt update').
        sudo_password: Password for sudo prompt (if omitted, uses host password or passwordless sudo).
        host: Target SSH host (defaults to active host).
        timeout: Execution timeout in seconds (default: 60).
    """
    try:
        host_info = resolve_host_info(host)
        client = get_cached_or_connect(host_info["name"])

        clean_cmd = command.strip()
        if clean_cmd.startswith("sudo "):
            clean_cmd = clean_cmd[5:].strip()

        pwd = sudo_password or host_info.get("password")

        start_t = time.time()
        # Request PTY for sudo prompt handling
        stdin, stdout, stderr = client.exec_command(
            f"sudo -S -p '[SUDO_PROMPT]' {clean_cmd}", get_pty=True, timeout=timeout
        )

        if pwd:
            # Send password when prompt requested
            time.sleep(0.3)
            stdin.write(f"{pwd}\n")
            stdin.flush()

        out_str = stdout.read().decode("utf-8", errors="replace")
        # Clean out sudo prompt artifacts
        clean_out = re.sub(r"\[SUDO_PROMPT\]", "", out_str).strip()
        clean_out = strip_ansi(clean_out)
        exit_code = stdout.channel.recv_exit_status()
        duration_ms = round((time.time() - start_t) * 1000, 2)

        return {
            "command": f"sudo {clean_cmd}",
            "exit_code": exit_code,
            "duration_ms": duration_ms,
            "stdout": clean_out,
            "is_success": exit_code == 0,
            "host": host_info["name"],
        }
    except Exception as e:
        return _format_ssh_error(e, host=host, command=command)


@mcp.tool()
def ssh_exec_script(
    script_content: str,
    interpreter: str = "bash",
    host: Optional[str] = None,
    timeout: int = 120,
) -> Dict[str, Any]:
    """
    Upload and execute a multi-line script (bash, sh, python, node) on the remote server, returning execution results.

    Args:
        script_content: Full multi-line script code.
        interpreter: Interpreter to run script with ('bash', 'sh', 'python3', 'node', 'pwsh').
        host: Target SSH host (defaults to active host).
        timeout: Execution timeout in seconds (default: 120).
    """
    try:
        host_info = resolve_host_info(host)
        client = get_cached_or_connect(host_info["name"])
        sftp = client.open_sftp()

        # Write to remote temp file
        remote_tmp = f"/tmp/mcp_script_{int(time.time())}_{os.getpid()}.sh"
        try:
            with sftp.open(remote_tmp, "w") as f:
                f.write(script_content)
            sftp.chmod(remote_tmp, 0o755)
        except Exception:
            # Fallback to local /tmp equivalent if /tmp doesn't exist
            remote_tmp = f"mcp_script_{int(time.time())}.sh"
            with sftp.open(remote_tmp, "w") as f:
                f.write(script_content)

        sftp.close()

        # Execute
        run_cmd = f"{interpreter} {shlex.quote(remote_tmp)}"
        res = _run_exec_channel(client, run_cmd, timeout=timeout)

        # Cleanup
        try:
            client.exec_command(f"rm -f {shlex.quote(remote_tmp)}")
        except Exception:
            pass

        res["host"] = host_info["name"]
        res["scriptLength"] = len(script_content)
        return res
    except Exception as e:
        return _format_ssh_error(e, host=host)


@mcp.tool()
def ssh_exec_background(
    command: str,
    job_name: Optional[str] = None,
    host: Optional[str] = None,
    log_file: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Launch a long-running process in the detached background (using nohup) and track its Process ID (PID).

    Args:
        command: Long-running command (e.g. 'npm run start', 'python train.py', 'backup.sh').
        job_name: Optional label for the job.
        host: Target SSH host (defaults to active host).
        log_file: Path to redirect output logs (defaults to /tmp/mcp_bg_<job_name>.log).
    """
    try:
        host_info = resolve_host_info(host)
        client = get_cached_or_connect(host_info["name"])

        name = job_name or f"job_{int(time.time())}"
        log_path = log_file or f"/tmp/mcp_bg_{name}.log"

        # Nohup execution
        bg_cmd = f"nohup {command} > {shlex.quote(log_path)} 2>&1 & echo $!"
        stdin, stdout, stderr = client.exec_command(bg_cmd, timeout=10)
        pid_str = stdout.read().decode("utf-8", errors="replace").strip()

        try:
            pid = int(pid_str)
        except ValueError:
            pid = None

        return {
            "success": bool(pid),
            "host": host_info["name"],
            "jobName": name,
            "pid": pid,
            "logFile": log_path,
            "command": command,
            "message": f"Background job '{name}' spawned with PID {pid}. Inspect output via ssh_check_job or ssh_tail_logs.",
        }
    except Exception as e:
        return _format_ssh_error(e, host=host, command=command)


@mcp.tool()
def ssh_check_job(job_id_or_pid: Union[int, str], host: Optional[str] = None) -> Dict[str, Any]:
    """
    Check if a detached background job/PID is still running and read the latest log output.

    Args:
        job_id_or_pid: The PID or job name to check.
        host: Target SSH host (defaults to active host).
    """
    try:
        host_info = resolve_host_info(host)
        client = get_cached_or_connect(host_info["name"])

        pid_val = str(job_id_or_pid)
        # Check process status
        ps_cmd = f"ps -p {shlex.quote(pid_val)} -o pid,user,%cpu,%mem,stat,time,command --no-headers 2>/dev/null"
        stdin, stdout, stderr = client.exec_command(ps_cmd, timeout=5)
        ps_out = stdout.read().decode("utf-8", errors="replace").strip()
        is_running = bool(ps_out)

        # Try to read default log file if exists
        log_candidate = f"/tmp/mcp_bg_{pid_val}.log"
        log_cmd = f"tail -n 30 {shlex.quote(log_candidate)} 2>/dev/null"
        stdin, stdout, stderr = client.exec_command(log_cmd, timeout=5)
        recent_logs = stdout.read().decode("utf-8", errors="replace").strip()

        return {
            "host": host_info["name"],
            "pid": pid_val,
            "isRunning": is_running,
            "processDetails": ps_out if is_running else "Process has terminated or PID not found.",
            "recentLogs": recent_logs or "No log file found at default path.",
        }
    except Exception as e:
        return _format_ssh_error(e, host=host)


@mcp.tool()
def ssh_kill_job(pid: int, signal: str = "SIGTERM", host: Optional[str] = None) -> Dict[str, Any]:
    """
    Terminate a remote process by PID.

    Args:
        pid: Remote process ID.
        signal: Signal name ('SIGTERM', 'SIGKILL', 'SIGHUP', 'SIGINT').
        host: Target SSH host (defaults to active host).
    """
    try:
        host_info = resolve_host_info(host)
        client = get_cached_or_connect(host_info["name"])

        sig_flag = "-9" if signal == "SIGKILL" else ("-15" if signal == "SIGTERM" else "-1")
        kill_cmd = f"kill {sig_flag} {pid}"
        res = _run_exec_channel(client, kill_cmd, timeout=10)
        return {
            "success": res["is_success"],
            "host": host_info["name"],
            "pid": pid,
            "signal": signal,
            "message": f"Sent {signal} to PID {pid}."
            if res["is_success"]
            else f"Failed to kill PID {pid}: {res['stderr']}",
        }
    except Exception as e:
        return _format_ssh_error(e, host=host)


# ==============================================================================
# 3. Interactive PTY / Pseudo-Terminal Tools
# ==============================================================================


@mcp.tool()
def ssh_pty_start(
    session_name: str,
    host: Optional[str] = None,
    term: str = "xterm-256color",
) -> Dict[str, Any]:
    """
    Start an interactive pseudo-terminal (PTY) session for stateful interactions, REPLs, and prompts.

    Args:
        session_name: Unique identifier for this terminal session (e.g. 'wizard', 'python-repl').
        host: Target SSH host (defaults to active host).
        term: Terminal type emulation (default: 'xterm-256color').
    """
    try:
        return start_pty_session(session_name, host=host, term=term)
    except Exception as e:
        return _format_ssh_error(e, host=host)


@mcp.tool()
def ssh_pty_send(
    session_name: str,
    input_text: str,
    wait_ms: int = 500,
) -> Dict[str, Any]:
    """
    Send keystrokes, answers, or commands into an active interactive PTY session and collect output.

    Args:
        session_name: Name of active PTY session.
        input_text: Text/command to send.
        wait_ms: Milliseconds to wait before capturing terminal output (default: 500).
    """
    try:
        return send_to_pty(session_name, input_text, wait_ms=wait_ms)
    except Exception as e:
        return _format_ssh_error(e)


@mcp.tool()
def ssh_pty_read(session_name: str, max_chars: int = 4000) -> Dict[str, Any]:
    """
    Read the output buffer of an active interactive PTY session.

    Args:
        session_name: Name of active PTY session.
        max_chars: Maximum character limit for output.
    """
    try:
        return read_pty_buffer(session_name, max_chars=max_chars)
    except Exception as e:
        return _format_ssh_error(e)


@mcp.tool()
def ssh_list_pty_sessions() -> Dict[str, Any]:
    """List all currently active interactive PTY sessions."""
    sessions = list_pty_sessions()
    return {
        "activePtyCount": len(sessions),
        "sessions": sessions,
    }


@mcp.tool()
def ssh_pty_close(session_name: str) -> Dict[str, Any]:
    """
    Close and terminate an interactive PTY session.

    Args:
        session_name: Name of the session to terminate.
    """
    return close_pty_session(session_name)


# ==============================================================================
# 4. Diagnostics & Remote Services Management
# ==============================================================================


@mcp.tool()
def ssh_system_overview(host: Optional[str] = None) -> Dict[str, Any]:
    """
    Retrieve comprehensive system diagnostics: OS version, kernel, CPU count, RAM utilization,
    load averages, uptime, and disk usage (df -h).

    Args:
        host: Target SSH host (defaults to active host).
    """
    try:
        host_info = resolve_host_info(host)
        client = get_cached_or_connect(host_info["name"])

        diag_script = """
echo "=== UNAME ==="
uname -a 2>/dev/null || ver
echo "=== UPTIME ==="
uptime 2>/dev/null
echo "=== CPU_INFO ==="
nproc 2>/dev/null || echo "1"
echo "=== MEMORY ==="
free -m 2>/dev/null || echo "N/A"
echo "=== DISK ==="
df -h 2>/dev/null || echo "N/A"
echo "=== OS_RELEASE ==="
cat /etc/os-release 2>/dev/null || echo "N/A"
"""
        res = _run_exec_channel(client, diag_script, timeout=15)
        raw = res["stdout"]

        # Parse sections
        sections = {}
        cur_sec = "header"
        cur_lines = []
        for line in raw.splitlines():
            if line.startswith("=== ") and line.endswith(" ==="):
                sections[cur_sec] = "\n".join(cur_lines).strip()
                cur_sec = line.strip("= ").lower()
                cur_lines = []
            else:
                cur_lines.append(line)
        sections[cur_sec] = "\n".join(cur_lines).strip()

        return {
            "host": host_info["name"],
            "remoteTarget": f"{host_info.get('user')}@{host_info.get('hostname')}",
            "osRelease": sections.get("os_release", ""),
            "uname": sections.get("uname", ""),
            "uptime": sections.get("uptime", ""),
            "cpuCores": sections.get("cpu_info", ""),
            "memoryUsage": sections.get("memory", ""),
            "diskUsage": sections.get("disk", ""),
        }
    except Exception as e:
        return _format_ssh_error(e, host=host)


@mcp.tool()
def ssh_list_packages(
    package_manager: Optional[
        Literal["apt", "dpkg", "rpm", "dnf", "yum", "pip", "npm", "brew", "pacman", "apk", "winget"]
    ] = None,
    filter: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    host: Optional[str] = None,
) -> Dict[str, Any]:
    """
    List installed software packages on the remote server across Linux/macOS/Windows package managers.
    Features automatic package manager detection, token-safe pagination, and filtering to prevent context bloat.

    Args:
        package_manager: Package manager to query (auto-detected if None: 'dpkg'/'apt', 'rpm'/'dnf'/'yum', 'pip', 'npm', 'brew', 'pacman', 'apk', 'winget').
        filter: Optional keyword or pattern filter on package name or description.
        limit: Maximum number of packages to return in this batch (default 50, max 200).
        offset: Starting offset for pagination (default 0).
        host: Target SSH host (defaults to active host).
    """
    try:
        host_info = resolve_host_info(host)
        client = get_cached_or_connect(host_info["name"])

        # Detection script if not provided
        pm = package_manager
        if not pm:
            detect_script = """
if command -v dpkg-query >/dev/null 2>&1; then
    echo "dpkg"
elif command -v rpm >/dev/null 2>&1; then
    echo "rpm"
elif command -v pacman >/dev/null 2>&1; then
    echo "pacman"
elif command -v apk >/dev/null 2>&1; then
    echo "apk"
elif command -v brew >/dev/null 2>&1; then
    echo "brew"
elif command -v winget >/dev/null 2>&1; then
    echo "winget"
elif command -v pip3 >/dev/null 2>&1 || command -v pip >/dev/null 2>&1; then
    echo "pip"
else
    echo "unknown"
fi
"""
            stdin, stdout, stderr = client.exec_command(detect_script, timeout=5)
            detected = stdout.read().decode("utf-8", errors="replace").strip().lower()
            pm = detected if detected and detected != "unknown" else "pip"

        # Query command per package manager
        if pm in ("dpkg", "apt"):
            query_cmd = "dpkg-query -W -f='${binary:Package}\t${Version}\t${Section}\n' 2>/dev/null || dpkg -l"
        elif pm in ("rpm", "dnf", "yum"):
            query_cmd = "rpm -qa --qf '%{NAME}\t%{VERSION}-%{RELEASE}\t%{SUMMARY}\n' 2>/dev/null"
        elif pm == "pacman":
            query_cmd = "pacman -Q 2>/dev/null"
        elif pm == "apk":
            query_cmd = "apk info -v 2>/dev/null"
        elif pm == "brew":
            query_cmd = "brew list --versions 2>/dev/null"
        elif pm == "winget":
            query_cmd = "winget list 2>/dev/null"
        elif pm == "npm":
            query_cmd = "npm list -g --depth=0 --json 2>/dev/null || npm list -g --depth=0"
        else:  # pip
            query_cmd = "pip list --format=json 2>/dev/null || pip list"

        stdin, stdout, stderr = client.exec_command(query_cmd, timeout=20)
        raw_out = stdout.read().decode("utf-8", errors="replace").strip()

        # Parse into package objects
        packages = []
        clean_filter = filter.strip().lower() if filter else None

        if raw_out.startswith("[") and raw_out.endswith("]"):
            try:
                parsed_json = json.loads(raw_out)
                for item in parsed_json:
                    name = str(item.get("name", ""))
                    ver = str(item.get("version", ""))
                    if clean_filter and (clean_filter not in name.lower() and clean_filter not in ver.lower()):
                        continue
                    packages.append({"name": name, "version": ver})
            except Exception:
                pass

        if not packages and raw_out:
            for line in raw_out.splitlines():
                line_str = line.strip()
                if (
                    not line_str
                    or line_str.startswith("Desired=")
                    or line_str.startswith("|")
                    or line_str.startswith("Name ")
                    or line_str.startswith("---")
                ):
                    continue

                parts = re.split(r"\t+|\s{2,}", line_str)
                if len(parts) >= 2:
                    pkg_name = parts[0].strip()
                    pkg_ver = parts[1].strip()
                    pkg_summary = parts[2].strip() if len(parts) > 2 else ""
                elif " " in line_str:
                    subparts = line_str.split(None, 1)
                    pkg_name = subparts[0].strip()
                    pkg_ver = subparts[1].strip() if len(subparts) > 1 else ""
                    pkg_summary = ""
                else:
                    pkg_name = line_str
                    pkg_ver = ""
                    pkg_summary = ""

                if clean_filter and (
                    clean_filter not in pkg_name.lower()
                    and clean_filter not in pkg_summary.lower()
                    and clean_filter not in pkg_ver.lower()
                ):
                    continue

                entry = {"name": pkg_name, "version": pkg_ver}
                if pkg_summary:
                    entry["summary"] = pkg_summary
                packages.append(entry)

        safe_limit = min(max(1, limit), 200)
        safe_offset = max(0, offset)
        total_packages = len(packages)
        display_packages = packages[safe_offset : safe_offset + safe_limit]
        has_more = total_packages > (safe_offset + len(display_packages))

        res: Dict[str, Any] = {
            "host": host_info["name"],
            "packageManager": pm,
            "filter": filter,
            "totalPackages": total_packages,
            "returnedPackages": len(display_packages),
            "offset": safe_offset,
            "limit": safe_limit,
            "hasMore": has_more,
            "truncated": has_more,
            "packages": display_packages,
        }

        if has_more:
            next_offset = safe_offset + len(display_packages)
            res["notice"] = (
                f"... [TRUNCATED: Showing packages {safe_offset + 1}-{next_offset} of {total_packages}. "
                f"Use offset={next_offset} to view next batch, or pass 'filter' to search by name] ..."
            )

        return res
    except Exception as e:
        return _format_ssh_error(e, host=host)


@mcp.tool()
def ssh_list_services(
    service_type: Literal["systemd", "docker", "pm2"] = "systemd",
    filter: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    host: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Inspect running remote services across systemd units, Docker containers, or PM2 node processes with pagination.

    Args:
        service_type: Service framework ('systemd', 'docker', 'pm2').
        filter: Optional keyword or pattern filter.
        limit: Max services to return per batch (default 50, max 150).
        offset: Starting offset for pagination (default 0).
        host: Target SSH host (defaults to active host).
    """
    try:
        host_info = resolve_host_info(host)
        client = get_cached_or_connect(host_info["name"])

        if service_type == "systemd":
            cmd = "systemctl list-units --type=service --state=running --no-pager --no-legend"
            if filter:
                cmd += f" | grep -i {shlex.quote(filter)}"
        elif service_type == "docker":
            cmd = "docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}'"
            if filter:
                cmd += f" | grep -i {shlex.quote(filter)}"
        else:
            cmd = "pm2 jlist 2>/dev/null || pm2 list"

        stdin, stdout, stderr = client.exec_command(cmd, timeout=15)
        raw_out = stdout.read().decode("utf-8", errors="replace").strip()

        lines = [ln.strip() for ln in raw_out.splitlines() if ln.strip()]
        total_services = len(lines)
        safe_limit = min(max(1, limit), 150)
        safe_offset = max(0, offset)
        display_lines = lines[safe_offset : safe_offset + safe_limit]
        has_more = total_services > (safe_offset + len(display_lines))

        res: Dict[str, Any] = {
            "host": host_info["name"],
            "serviceType": service_type,
            "filter": filter,
            "totalServices": total_services,
            "returnedServices": len(display_lines),
            "offset": safe_offset,
            "limit": safe_limit,
            "hasMore": has_more,
            "truncated": has_more,
            "services": display_lines,
        }

        if has_more:
            next_offset = safe_offset + len(display_lines)
            res["notice"] = (
                f"... [TRUNCATED: Showing services {safe_offset + 1}-{next_offset} of {total_services}. "
                f"Use offset={next_offset} or provide 'filter' to narrow query] ..."
            )

        return res
    except Exception as e:
        return _format_ssh_error(e, host=host)


@mcp.tool()
def ssh_service_action(
    service_name: str,
    action: Literal["status", "start", "stop", "restart", "reload", "enable", "disable"] = "status",
    service_type: Literal["systemd", "docker", "pm2"] = "systemd",
    host: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Manage a remote daemon or container (status, start, stop, restart, reload).

    Args:
        service_name: Name of the service unit (e.g. 'nginx', 'postgresql', 'my-container').
        action: Lifecycle action to take.
        service_type: Service framework ('systemd', 'docker', 'pm2').
        host: Target SSH host (defaults to active host).
    """
    try:
        host_info = resolve_host_info(host)
        client = get_cached_or_connect(host_info["name"])

        s_name = shlex.quote(service_name)
        if service_type == "systemd":
            cmd = (
                f"sudo systemctl {action} {s_name} --no-pager"
                if action != "status"
                else f"systemctl status {s_name} --no-pager"
            )
        elif service_type == "docker":
            cmd = f"docker {action} {s_name}"
        else:
            cmd = f"pm2 {action} {s_name}"

        res = _run_exec_channel(client, cmd, timeout=20)
        return {
            "host": host_info["name"],
            "service": service_name,
            "action": action,
            "success": res["is_success"],
            "output": res["stdout"],
            "error": res["stderr"] if not res["is_success"] else None,
        }
    except Exception as e:
        return _format_ssh_error(e, host=host)


@mcp.tool()
def ssh_tail_logs(
    target: str,
    lines: int = 50,
    is_journal: bool = False,
    host: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Tail remote log files (e.g. /var/log/syslog, /var/log/nginx/error.log) or systemd journal logs.
    Features safety caps on line count and character length to prevent context bloat.

    Args:
        target: Log file path (e.g. '/var/log/syslog') or systemd service unit name if is_journal=True.
        lines: Number of trailing lines to return (default: 50, max: 200).
        is_journal: If True, uses 'journalctl -u <target> -n <lines> --no-pager'.
        host: Target SSH host (defaults to active host).
    """
    try:
        host_info = resolve_host_info(host)
        client = get_cached_or_connect(host_info["name"])

        safe_lines = min(max(1, lines), 200)
        if is_journal:
            cmd = f"sudo journalctl -u {shlex.quote(target)} -n {safe_lines} --no-pager"
        else:
            cmd = f"sudo tail -n {safe_lines} {shlex.quote(target)}"

        res = _run_exec_channel(client, cmd, timeout=15, max_lines=safe_lines, max_chars=15000)
        return {
            "host": host_info["name"],
            "target": target,
            "lines": safe_lines,
            "isJournal": is_journal,
            "logs": res["stdout"],
            "truncated": res.get("truncated", False),
            "notice": res.get("notice"),
            "error": res["stderr"] if not res["is_success"] else None,
        }
    except Exception as e:
        return _format_ssh_error(e, host=host)


@mcp.tool()
def ssh_list_processes(
    filter: Optional[str] = None,
    sort_by: Literal["cpu", "mem"] = "cpu",
    limit: int = 30,
    offset: int = 0,
    host: Optional[str] = None,
) -> Dict[str, Any]:
    """
    List top remote processes sorted by CPU or Memory usage with token-safe limits.

    Args:
        filter: Optional process name or command filter.
        sort_by: Sort metric ('cpu' or 'mem').
        limit: Max number of processes to return (default: 30, max: 100).
        offset: Starting offset for pagination (default 0).
        host: Target SSH host (defaults to active host).
    """
    try:
        host_info = resolve_host_info(host)
        client = get_cached_or_connect(host_info["name"])

        safe_limit = min(max(1, limit), 100)
        safe_offset = max(0, offset)
        sort_col = "%cpu" if sort_by == "cpu" else "%mem"
        cmd = f"ps -eo pid,user,%cpu,%mem,stat,time,command --sort=-{sort_col}"
        if filter:
            cmd += f" | grep -E 'PID|{shlex.quote(filter)}'"

        stdin, stdout, stderr = client.exec_command(cmd, timeout=10)
        raw_out = stdout.read().decode("utf-8", errors="replace").strip()

        all_lines = raw_out.splitlines()
        header = all_lines[0] if all_lines else "PID USER %CPU %MEM STAT TIME COMMAND"
        data_lines = all_lines[1:] if len(all_lines) > 1 else []

        total_procs = len(data_lines)
        display_lines = data_lines[safe_offset : safe_offset + safe_limit]
        has_more = total_procs > (safe_offset + len(display_lines))

        result_text = header + "\n" + "\n".join(display_lines)

        res: Dict[str, Any] = {
            "host": host_info["name"],
            "sortBy": sort_by,
            "filter": filter,
            "totalProcesses": total_procs,
            "returnedProcesses": len(display_lines),
            "offset": safe_offset,
            "limit": safe_limit,
            "hasMore": has_more,
            "truncated": has_more,
            "processes": result_text,
        }

        if has_more:
            next_offset = safe_offset + len(display_lines)
            res["notice"] = (
                f"... [TRUNCATED: Showing processes {safe_offset + 1}-{next_offset} of {total_procs}. "
                f"Use offset={next_offset} or provide 'filter' to locate specific processes] ..."
            )

        return res
    except Exception as e:
        return _format_ssh_error(e, host=host)


# ==============================================================================
# 5. SFTP Remote File Operations Tools
# ==============================================================================


@mcp.tool()
def sftp_list_dir(
    remote_path: str = ".",
    limit: int = 100,
    offset: int = 0,
    filter: Optional[str] = None,
    host: Optional[str] = None,
) -> Dict[str, Any]:
    """
    List contents of a remote directory with file types, sizes, permissions, timestamps, and context window protection.

    Args:
        remote_path: Remote directory path (default: current directory '.').
        limit: Max items to return per batch (default 100, max 250).
        offset: Starting offset for pagination (default 0).
        filter: Optional filename substring filter.
        host: Target SSH host (defaults to active host).
    """
    try:
        return list_remote_directory(remote_path=remote_path, limit=limit, offset=offset, filter=filter, host=host)
    except Exception as e:
        return _format_ssh_error(e, host=host)


@mcp.tool()
def sftp_read_file(
    remote_path: str,
    max_chars: int = 15000,
    offset_lines: int = 0,
    host: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Read text/source code from a remote file with line offset support and token safety.

    Args:
        remote_path: Remote file path.
        max_chars: Maximum characters to return (default: 15,000).
        offset_lines: Starting line offset (0-indexed).
        host: Target SSH host (defaults to active host).
    """
    try:
        return read_remote_text_file(
            remote_path=remote_path,
            max_chars=max_chars,
            offset_lines=offset_lines,
            host=host,
        )
    except Exception as e:
        return _format_ssh_error(e, host=host)


@mcp.tool()
def sftp_write_file(
    remote_path: str,
    content: str,
    mode: Literal["write", "append"] = "write",
    host: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Write or append text content to a remote file via SFTP.

    Args:
        remote_path: Remote destination path.
        content: Text content to write.
        mode: 'write' (overwrite) or 'append'.
        host: Target SSH host (defaults to active host).
    """
    try:
        return write_remote_text_file(
            remote_path=remote_path,
            content=content,
            mode=mode,
            host=host,
        )
    except Exception as e:
        return _format_ssh_error(e, host=host)


@mcp.tool()
def sftp_stat(
    remote_path: str,
    host: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Inspect detailed file/directory metadata, size, permissions, uid/gid, and timestamps.

    Args:
        remote_path: Remote file or directory path.
        host: Target SSH host (defaults to active host).
    """
    try:
        return stat_remote_path(remote_path=remote_path, host=host)
    except Exception as e:
        return _format_ssh_error(e, host=host)


@mcp.tool()
def sftp_upload(
    local_path: str,
    remote_path: str,
    host: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Upload a local file or entire folder to the remote host.

    Args:
        local_path: Local path on machine (file or folder).
        remote_path: Remote destination path.
        host: Target SSH host (defaults to active host).
    """
    try:
        return upload_path(local_path=local_path, remote_path=remote_path, host=host)
    except Exception as e:
        return _format_ssh_error(e, host=host)


@mcp.tool()
def sftp_download(
    remote_path: str,
    local_path: str,
    host: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Download a remote file or folder to the local machine.

    Args:
        remote_path: Remote source path.
        local_path: Local destination path.
        host: Target SSH host (defaults to active host).
    """
    try:
        return download_path(remote_path=remote_path, local_path=local_path, host=host)
    except Exception as e:
        return _format_ssh_error(e, host=host)


@mcp.tool()
def sftp_remove(
    remote_path: str,
    recursive: bool = False,
    host: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Delete a remote file or directory.

    Args:
        remote_path: Remote path to remove.
        recursive: If True, recursively deletes non-empty directories.
        host: Target SSH host (defaults to active host).
    """
    try:
        return remove_remote_path(remote_path=remote_path, recursive=recursive, host=host)
    except Exception as e:
        return _format_ssh_error(e, host=host)


# ==============================================================================
# 6. Port Forwarding & Tunnels Tools
# ==============================================================================


@mcp.tool()
def ssh_tunnel_open(
    local_port: int,
    remote_port: int,
    remote_host: str = "localhost",
    tunnel_name: Optional[str] = None,
    host: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Establish a local-to-remote SSH port forwarding tunnel in the background.
    Allows accessing remote databases, APIs, or services via 127.0.0.1:<local_port>.

    Args:
        local_port: Local port to bind on machine (e.g. 15432, 13306, 8080).
        remote_port: Remote target port on the server (e.g. 5432, 3306, 80).
        remote_host: Remote host to bind to from SSH server perspective (default: 'localhost').
        tunnel_name: Optional custom name for the tunnel.
        host: Target SSH host (defaults to active host).
    """
    try:
        return open_local_tunnel(
            local_port=local_port,
            remote_port=remote_port,
            remote_host=remote_host,
            tunnel_name=tunnel_name,
            host=host,
        )
    except Exception as e:
        return _format_ssh_error(e, host=host)


@mcp.tool()
def ssh_tunnel_list() -> Dict[str, Any]:
    """List all currently active local-to-remote SSH port forwarding tunnels."""
    tunnels = list_active_tunnels()
    return {
        "activeTunnelsCount": len(tunnels),
        "tunnels": tunnels,
    }


@mcp.tool()
def ssh_tunnel_close(tunnel_id_or_name: str) -> Dict[str, Any]:
    """
    Close and terminate an active SSH port forwarding tunnel.

    Args:
        tunnel_id_or_name: Tunnel name or local port number.
    """
    return close_tunnel(tunnel_id_or_name)


# ==============================================================================
# Server Entrypoint
# ==============================================================================

if __name__ == "__main__":
    mcp.run(transport="stdio")
