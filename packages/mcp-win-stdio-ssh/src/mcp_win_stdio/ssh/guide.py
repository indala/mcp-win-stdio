"""
Comprehensive guide, tool reference, and Claude prompt recipes for mcp-win-stdio-ssh.
"""

def print_ssh_guide() -> None:
    """Print complete SSH MCP tool reference and workflow recipes."""
    guide_text = """
================================================================================
 🚀 mcp-win-stdio-ssh — Advanced Multi-SSH Connection & Remote Management
================================================================================

The SSH MCP server connects AI models directly to remote Linux, macOS, and Windows
servers over standard SSH, SFTP, and interactive PTY channels.

--------------------------------------------------------------------------------
 🌟 Key Architecture & Capabilities
--------------------------------------------------------------------------------
 • Multi-Host Pooling: Connect to multiple servers concurrently with connection reuse.
 • Auto-Discovery: Automatically reads ~/.ssh/config aliases, identity files & proxy jumps.
 • Sticky Context: 'use_host' sets the default target host across subsequent tool calls.
 • Interactive PTY: Stateful terminal sessions for long-running processes, REPLs & prompts.
 • Service & Health: Fast system metrics, systemd/docker/pm2 inspection, and log tailing.
 • Full SFTP: Remote file reading/writing with token protection, directory recursion.
 • Local Tunnels: Port forwarding to expose remote MySQL/Postgres/Web services locally.

--------------------------------------------------------------------------------
 🛠️ Complete Tool Reference (27 Tools)
--------------------------------------------------------------------------------

 1. Host & Connection Management
    • list_hosts()                      -> List all discovered/saved SSH hosts & status
    • use_host(host)                    -> Switch active sticky host context
    • add_host(name, hostname, ...)     -> Save new host to ~/.mcp-win-stdio/ssh_hosts.json
    • remove_host(name)                 -> Delete saved host configuration
    • test_host(host=None)              -> Test SSH handshake, auth, latency, and remote OS
    • list_active_connections()         -> Show live connections in the connection pool
    • disconnect_host(host=None)        -> Close connection for specific or active host

 2. Command Execution & Background Jobs
    • ssh_exec(command, cwd, env, ...)  -> Execute non-interactive command & return exit code
    • ssh_exec_sudo(command, password)  -> Run command with sudo handling password prompt
    • ssh_exec_script(script_content)   -> Upload and execute bash/python/sh script
    • ssh_exec_background(command)      -> Run detached background job (nohup) & get PID
    • ssh_check_job(job_id_or_pid)      -> Inspect status and logs of background job
    • ssh_kill_job(pid, signal)         -> Terminate remote process by PID

 3. Interactive PTY / Shell
    • ssh_pty_start(session_name)       -> Spawn interactive terminal session
    • ssh_pty_send(session_name, text)  -> Send command/keystroke and read buffer
    • ssh_pty_read(session_name)        -> Read output buffer from PTY session
    • ssh_list_pty_sessions()           -> List open interactive PTY sessions
    • ssh_pty_close(session_name)       -> Terminate PTY session

 4. Diagnostics & Remote Services
    • ssh_system_overview()             -> CPU/RAM/Disk stats, OS distro, kernel, uptime
    • ssh_list_services(type, filter)   -> List systemd units, docker containers, or pm2 apps
    • ssh_service_action(name, action)  -> Manage service (status/start/stop/restart/reload)
    • ssh_tail_logs(target, lines)      -> Tail log files (/var/log/...) or journalctl
    • ssh_list_processes(sort_by)       -> Top processes by CPU or Memory
    • ssh_list_packages(manager, ...)   -> Paginated installed packages (apt, dnf, pacman, pip, npm)

 5. SFTP File Management
    • sftp_list_dir(remote_path)        -> List directory with permissions & sizes
    • sftp_read_file(remote_path)       -> Read remote text file with line offset
    • sftp_write_file(remote_path, ...) -> Write or append remote file
    • sftp_stat(remote_path)            -> Get file/folder permissions & metadata
    • sftp_mkdir(remote_path)           -> Create remote directory
    • sftp_remove(remote_path)          -> Delete remote file or directory
    • sftp_upload(local_path, remote)   -> Upload file or folder recursively
    • sftp_download(remote, local_path) -> Download file or folder recursively

 6. Port Forwarding & Tunnels
    • ssh_tunnel_open(local, remote)    -> Forward remote port to 127.0.0.1:<local_port>
    • ssh_tunnel_list()                 -> List active local tunnels
    • ssh_tunnel_close(tunnel_id)       -> Terminate active tunnel

--------------------------------------------------------------------------------
 💡 Example Claude Workflows & Prompts
--------------------------------------------------------------------------------

 1. Remote Diagnostics:
    "Check the health and disk usage of production-server, then list any failed systemd services."

 2. Deploy Application & Check Logs:
    "Upload ./dist to /var/www/my-app on web-01, restart the nginx service, and tail the error log."

 3. Database Tunneling:
    "Open a local tunnel from port 15432 to remote Postgres port 5432 on db-cluster, then check table counts."

 4. Interactive Configuration:
    "Start an interactive PTY session on staging-server and run the configuration script."
================================================================================
"""
    print(guide_text)
