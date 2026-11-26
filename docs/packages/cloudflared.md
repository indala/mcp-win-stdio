# `cloudflared (Cloudflare Tunnel CLI)`

> Default HTTPS tunnel provider for `mws tunnel`, exposing the local Streamable HTTP MCP endpoint over `*.trycloudflare.com`.

## Tool Metadata

| Property | Details |
| :--- | :--- |
| **Category** | External CLI & Binary |
| **Install / Prerequisite** | `winget install --id Cloudflare.cloudflared` (or `brew install cloudflared`) |
| **Used By (`mcp-win-stdio`)** | `src/mcp_win_stdio/core/tunnel.py`, `src/mcp_win_stdio/cli.py`, `src/mcp_win_stdio/core/config.py` |

## Subcommands, Flags & Environment Variables

| Function Name / Variable | Attributes & Description |
| :--- | :--- |
| `cloudflared tunnel --url <local_target>` | `subcommand` · Starts a quick tunnel to `http://<host>:<port>` and prints a `https://<id>.trycloudflare.com` URL. |
| `cloudflared --version` (`-v`, `-V`) | `flag` · Prints installed `cloudflared` version (checked by `MwsTunnelManager.get_cloudflared_version()` and `mws doctor`). |
| `cloudflared update` / `service` / `tail` | `subcommand` · Self-update agent, manage Windows service, or stream remote tunnel logs. |
| `--credentials-file` (`%TUNNEL_CRED_FILE%`) | `global flag` · Filepath for named tunnel credentials JSON. |
| `--region` (`%TUNNEL_REGION%`) | `global flag` · Cloudflare Edge region to connect to. |
| `--edge-ip-version` (`%TUNNEL_EDGE_IP_VERSION%`) | `global flag` · IP version (`4`, `6`, `auto`) for Edge connections. |
| `--post-quantum` / `--pq` (`%TUNNEL_POST_QUANTUM%`) | `global flag` · Enable post-quantum secure tunnel transport. |
| `--output` (`%TUNNEL_LOG_OUTPUT%`) | `global flag` · Log output format (`default`, `json`). |
| `api.trycloudflare.com` | `service endpoint` · Cloudflare quick-tunnel control endpoint contacted during `start_cloudflare_tunnel()`. |
