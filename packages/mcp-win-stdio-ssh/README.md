# mcp-win-stdio-ssh

> Advanced Multi-SSH Connection & Remote Management Model Context Protocol (MCP) Server for Windows & Claude Desktop / Claude Code CLI.

Part of the **[mcp-win-stdio](https://github.com/indala/mcp-win-stdio)** suite.

---

## 🌟 Key Features

- **Multi-Host Connection Pooling & Persistence**: Connect to unlimited remote servers. Automatically parses `~/.ssh/config` (aliases, identity files, JumpHosts) and persists active host preferences.
- **Sticky Active Host**: Run commands against an active default host or specify `host="server_name"` per tool call.
- **Remote Execution & Elevated Commands**: Non-interactive command execution (`ssh_exec`), `sudo` password automation (`ssh_exec_sudo`), multi-line script execution (`ssh_exec_script`), and detached background jobs (`ssh_exec_background`).
- **Interactive PTY Shell Sessions**: Start stateful pseudo-terminals (`ssh_pty_start`, `ssh_pty_send`, `ssh_pty_read`) for interactive REPLs, prompts, and long-running interactive tools.
- **Remote Diagnostics & Services**: System health stats (`ssh_system_overview`), process monitoring (`ssh_list_processes`), systemd / docker / pm2 services (`ssh_list_services`, `ssh_service_action`), and live log tailing (`ssh_tail_logs`).
- **High-Performance SFTP**: Explore remote file systems (`sftp_list_dir`), read/write files (`sftp_read_file`, `sftp_write_file`), inspect metadata (`sftp_stat`), and sync local/remote folders (`sftp_upload`, `sftp_download`).
- **Port Forwarding & Tunnels**: Create background local-to-remote SSH port forwarding tunnels (`ssh_tunnel_open`, `ssh_tunnel_list`, `ssh_tunnel_close`) to securely access remote databases or web services.

---

## 📦 Installation

```bash
# Standalone package installation:
pip install mcp-win-stdio-ssh

# Or with full mcp-win-stdio suite:
pip install "mcp-win-stdio[all]"
```

---

## 🚀 Quick Start & Claude Configuration

### Claude Desktop (`%APPDATA%\Claude\claude_desktop_config.json`)

```json
{
  "mcpServers": {
    "ssh": {
      "command": "mws-ssh",
      "args": ["run"]
    }
  }
}
```

### Claude Code CLI

```bash
claude mcp add ssh mws-ssh run
```

---

## 🛠️ CLI Utilities

```bash
# Open interactive diagnostic CLI & host manager
mws-ssh

# List configured SSH hosts and test latency
mws-ssh test

# Launch MCP stdio server
mws-ssh run

# View comprehensive prompt recipes & tool documentation
mws-ssh guide
```
