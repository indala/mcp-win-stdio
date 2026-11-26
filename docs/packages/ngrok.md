# `ngrok`

> Alternative HTTPS tunnel provider (`--provider ngrok`) with optional custom `--domain` support.

## Tool Metadata

| Property | Details |
| :--- | :--- |
| **Category** | External CLI & Binary |
| **Install / Prerequisite** | `winget install --id Ngrok.Ngrok` (or `brew install ngrok/ngrok/ngrok`) |
| **Used By (`mcp-win-stdio`)** | `src/mcp_win_stdio/core/tunnel.py`, `src/mcp_win_stdio/cli.py`, `src/mcp_win_stdio/core/config.py` |

## Subcommands, Flags & Environment Variables

| Function Name / Variable | Attributes & Description |
| :--- | :--- |
| `ngrok http <port> [--domain <domain>]` | `subcommand` · Starts an HTTP/HTTPS tunnel forwarding public traffic to local port (`start_ngrok_tunnel()`). |
| `ngrok --version` (`-v`) | `flag` · Prints installed ngrok CLI version. |
| `ngrok config add-authtoken <token>` | `subcommand` · Saves ngrok authtoken required for tunnel creation. |
| `ngrok tcp <port>` / `ngrok tls` / `ngrok start` | `subcommand` · TCP/TLS tunnels or named tunnels from config. |
| `--config <paths>` | `flag` · Path(s) to ngrok YAML config files. |
| `http://localhost:4040` | `local web UI` · ngrok local inspection & tunnel status interface. |
