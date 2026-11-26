# `Remote SSH Host Tools (`systemctl`, `docker`, `pm2`, `journalctl`, package managers)`

> Remote system, container, service, log, and package inspection commands executed over Paramiko SSH channels.

## Tool Metadata

| Property | Details |
| :--- | :--- |
| **Category** | Remote Host CLIs (over SSH) |
| **Install / Prerequisite** | Installed on target Linux/Unix/Windows remote SSH hosts |
| **Used By (`mcp-win-stdio`)** | `packages/mcp-win-stdio-ssh/src/mcp_win_stdio/ssh/server.py` |

## Subcommands, Flags & Environment Variables

| Function Name / Variable | Attributes & Description |
| :--- | :--- |
| `systemctl list-units` / `status` / `start` / `stop` / `restart` / `reload` | `systemd` · Lists running systemd services and controls unit lifecycle (`ssh_list_services`, `ssh_service_action`). |
| `docker ps` / `docker <action> <container>` | `Docker CLI` · Lists running containers and manages container lifecycle (`ssh_list_services`, `ssh_service_action`). |
| `pm2 jlist` / `pm2 list` / `pm2 <action> <app>` | `PM2 CLI` · Inspects and controls Node.js PM2 processes (`ssh_list_services`, `ssh_service_action`). |
| `sudo journalctl -u <unit> -n <lines> --no-pager` | `systemd journal` · Tails unit logs when `is_journal=True` (`ssh_tail_logs`). |
| `sudo tail -n <lines> <path>` | `coreutils` · Tails remote log files (`ssh_tail_logs`). |
| `ps -eo pid,user,%cpu,%mem,stat,time,command --sort=-%cpu\|-mem` | `procps` · Lists top processes sorted by CPU or memory (`ssh_list_processes`). |
| `dpkg-query` / `rpm` / `pacman` / `apk` / `brew` / `winget` / `npm` / `pip` | `package managers` · Auto-detected and queried by `ssh_list_packages`. |
