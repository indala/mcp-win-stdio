# `Package & System Runners (`uv`, `pip`, `winget`, `brew`, `openssl`, `taskkill`)`

> Package installation, self-updates, OS tool installation, and Windows process management.

## Tool Metadata

| Property | Details |
| :--- | :--- |
| **Category** | External CLI & Binary |
| **Install / Prerequisite** | OS / Python toolchain binaries |
| **Used By (`mcp-win-stdio`)** | `src/mcp_win_stdio/core/installer.py`, `external_updater.py`, `tunnel.py`, `cli.py`, `process_pool.py` |

## Subcommands, Flags & Environment Variables

| Function Name / Variable | Attributes & Description |
| :--- | :--- |
| `uv pip install --python <py> [--upgrade] <pkgs>` | `binary` · Preferred package installer/updater used by `mws install` and `mws update`. |
| `uv pip uninstall --python <py> -y <pkgs>` | `binary` · Package removal used by `mws uninstall`. |
| `uvx <tool>` | `binary` · Supported runner for ephemeral Python MCP sub-servers in `process_pool.py`. |
| `python -m pip install / uninstall` | `fallback` · Used automatically when `uv` is not on `PATH`. |
| `winget install --id <ID> -e` | `Windows binary` · Auto-installs `Git.Git`, `GitHub.cli`, `Cloudflare.cloudflared`, `Ngrok.Ngrok`. |
| `brew install <formula>` | `macOS binary` · Auto-installs `cloudflared` or `ngrok/ngrok/ngrok` when running on macOS. |
| `taskkill /F /T /PID <pid>` | `Windows binary` · Force-terminates child process trees in `process_pool.py` and `cli.py`. |
| `cmd.exe /c <cmd>` | `Windows binary` · Launches detached background self-update batch commands in `installer.py` / `external_updater.py`. |
