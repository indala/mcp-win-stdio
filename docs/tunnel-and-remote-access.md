# Remote Access & Secure Tunneling

`mcp-win-stdio` includes a production-grade, zero-exposure remote bridge (`mws tunnel`) designed to securely expose your local Windows MCP tool suite to web-based AI clients (such as **Claude Web / Artifacts**, **ChatGPT Custom GPTs / Web**, **Cursor**, **Gemini**, and **MCP Inspector**) using **Cloudflare Tunnel**, **ngrok**, or **Direct HTTPS/HTTP** binding.

---

## 🌟 Key Architecture & Security Highlights

* **Three Tunnel Types (`--type cloudflare | ngrok | direct`)**:
  * **`cloudflare` (Default)**: Creates an encrypted outbound-only tunnel via `cloudflared` to Cloudflare's edge network—no public IP or port-forwarding required.
  * **`ngrok`**: Provisions an ngrok HTTPS tunnel (with optional static `--domain`) and automatically redirects first-time users to ngrok's authtoken dashboard for one-step inline setup.
  * **`direct`**: Binds directly on your host/VM (`0.0.0.0` by default) with automatic TLS certificate management in `~/.mcp-win-stdio/certs/`.
* **OAuth 2.0 with PKCE (Default Authentication)**:
  * Fully compliant with **RFC 8414** (Authorization Server Metadata), **RFC 9728** (Protected Resource Metadata), **RFC 7591** (Dynamic Client Registration), **RFC 7636** (PKCE with mandatory `S256` transform), **RFC 7009** (Token Revocation), and **RFC 8252** (OAuth 2.0 for Native Apps).
  * Requires a **Host-Owner Terminal Approval PIN** (a one-time 6-digit cryptographic PIN displayed in your Windows terminal) to authorize remote client connections, preventing rogue approval attacks across loopback tunnel proxies.
* **Granular Permission Ceilings**:
  * `--mode read_only` (default): Strictly forbids any filesystem writes, command execution, database mutations, Git commits/pushes, and remote SSH modifications.
  * Clamps effective scopes such that client tokens can never exceed the host server's permission ceiling ($\text{effective\_mode} = \min(\text{server\_mode}, \text{token\_scope})$).
* **Multi-Layer Defensive Hardening**:
  * Token-bucket rate limiting (60 requests/minute per client).
  * CORS preflight support (`OPTIONS` $\to$ `204 No Content`) with `Access-Control-Allow-Origin: *` for browser-based MCP clients.
  * In-memory HMAC-SHA256 signature verification for issued tokens and revocation requests.

---

## 🚀 Quick Start

### 1. Launch a Tunnel with OAuth 2.0 (Recommended)

To start the tunnel with OAuth 2.0 PKCE authentication in read-only mode:

```powershell
mws tunnel
```

When launched:
1. `mws` runs an interactive pre-flight review displaying active safety limits.
2. It provisions your selected endpoint (`cloudflare`, `ngrok`, or `direct` HTTPS) and displays your public URL:
   ```text
   ╭────────────────────────────────────────────────────────────────────────╮
   │ 🌐 PUBLIC MCP TUNNEL ONLINE                                            │
   │ Endpoint:  https://<your-tunnel-url>/mcp                               │
   │ Auth Mode: OAuth 2.0 (PKCE + DCR)                                      │
   │ Access:    READ ONLY (Protected by lexical & engine transaction limits)│
   ╰────────────────────────────────────────────────────────────────────────╯
   ```
3. When a remote client (e.g. Claude Web or MCP Inspector) initiates an authorization request, `mws tunnel` prints a 6-digit PIN in your terminal:
   ```text
   [OAuth] 🔑 HOST OWNER APPROVAL PIN: 849201
   [OAuth] Enter this PIN in the browser to authorize client: MCP Inspector
   ```
4. Enter the PIN in the web consent UI to authorize the client.

### 2. Launch with a Static Cryptographic Bearer Token

For automated webhooks, headless agents, or clients that only support Bearer header authentication:

```powershell
# Auto-generate a secure 32-byte cryptographic token
mws tunnel --auth bearer

# Or supply your own pre-shared token
mws tunnel --auth bearer --token "my-secure-pre-shared-token-secret"
```

Configure your remote client with the HTTP Header:
```http
Authorization: Bearer my-secure-pre-shared-token-secret
```

### 3. Read-Write Access (Interactive Review Required)

If you need the remote client to execute mutations (e.g., editing files, running SQL `INSERT`/`UPDATE`, or staging Git commits):

```powershell
mws tunnel --mode read_write
```

> [!WARNING]
> In `read_write` mode, the client is granted write capabilities according to your configured tool permissions. Always ensure you are connecting trusted clients and using OAuth 2.0 or strong Bearer tokens.

---

## 🌐 Tunnel Types (`--type`)

### 1. Cloudflare Tunnel (Default)
```powershell
mws tunnel
# Equivalent to:
mws tunnel --type cloudflare
```
If `cloudflared` is not in your `PATH`, `mws tunnel` offers to install it on demand via `winget` (Windows) or `brew` (macOS).

### 2. ngrok Tunnel (with Automatic First-Time Login Redirect)
```powershell
mws tunnel --type ngrok
# Or with a static ngrok domain:
mws tunnel --type ngrok --domain your-name.ngrok-free.app
```
* **On-demand install**: If `ngrok` is missing, `mws tunnel` offers to install it via `winget` (`Ngrok.Ngrok`) or `brew`.
* **Automatic first-time setup**: If no ngrok authtoken is found in `NGROK_AUTHTOKEN` or your ngrok config file (`%LOCALAPPDATA%\ngrok\ngrok.yml`, `~/.config/ngrok/ngrok.yml`, etc.), `mws tunnel` automatically opens `https://dashboard.ngrok.com/get-started/your-authtoken` in your browser, prompts you to paste the token inline, saves it with `ngrok config add-authtoken`, and launches the tunnel in the same run.

### 3. Direct HTTPS / HTTP (with `~/.mcp-win-stdio/certs/` Setup)
```powershell
mws tunnel --type direct
```
* **Certificate Discovery & Interactive Wizard**: `mws tunnel` checks `~/.mcp-win-stdio/certs/` (`direct_cert.pem` & `direct_key.pem`) or explicit `--ssl-certfile` / `--ssl-keyfile` overrides. In interactive runs, if no certificates exist yet in `~/.mcp-win-stdio/certs/`, `mws tunnel` offers the **Direct HTTPS Setup** wizard to:
  1. **Generate a 90-day self-signed certificate** (`direct_cert.pem` & `direct_key.pem`) into `~/.mcp-win-stdio/certs/` using `openssl` CLI (with a pure-Python `cryptography` fallback).
  2. **Import your existing 90-day ZeroSSL / Let's Encrypt cert & key** into `~/.mcp-win-stdio/certs/`.
  3. **Use plain HTTP** (for local LAN or reverse-proxy setups).
  In non-interactive runs (`--yes`), `mws tunnel` automatically uses stored/explicit certificates if present, or falls back to plain HTTP if none are configured.
* **Saved Preferences**: `mws tunnel` saves your chosen tunnel type, port, `public_url`, and certificate paths to `~/.mcp-win-stdio/config.json`, so subsequent `mws tunnel` runs need no extra flags.
* You can also manage certificates anytime from the interactive menu via **`[7] Setup / Manage Direct HTTPS Certificates`**, or pass explicit overrides (`--host`, `--port`, `--public-url`, `--ssl-certfile`, `--ssl-keyfile`).

---

## ⚙️ CLI Flags & Options

| Option | Flag | Description | Default |
| :--- | :--- | :--- | :--- |
| **Tunnel Type** | `--type, --provider, -P {cloudflare,ngrok,direct}` | Tunnel provider or direct host/port bind. | `cloudflare` |
| **Local Host** | `--host <HOST>` | Local bind host (`127.0.0.1` for tunnels, `0.0.0.0` for `direct`). | `127.0.0.1` / `0.0.0.0` |
| **ngrok Domain** | `--domain <DOMAIN>` | Optional custom static domain for `ngrok`. | `None` |
| **Public URL** | `--public-url <URL>` | Explicit public URL (e.g. `https://123.45.67.89:3000`) for `direct` mode. | Auto-detected |
| **SSL Cert** | `--ssl-certfile <PATH>` | Path to TLS certificate (`.pem`/`.crt`) for `direct` HTTPS mode. | `~/.mcp-win-stdio/certs/direct_cert.pem` |
| **SSL Key** | `--ssl-keyfile <PATH>` | Path to TLS private key (`.pem`/`.key`) for `direct` HTTPS mode. | `~/.mcp-win-stdio/certs/direct_key.pem` |
| **Auth Mode** | `--auth, -a {oauth,bearer,none}` | Authentication mechanism required by the tunnel bridge. | `oauth` |
| **Access Mode** | `--mode, -m {read_only,read_write}` | Global permission ceiling for tool execution. | `read_only` |
| **Port** | `--port, -p <PORT>` | Local bridge port for the internal HTTP/SSE server. | `8080` |
| **Token** | `--token, -t <TOKEN>` | Custom Bearer token (when `--auth bearer` is active). | Auto-generated |
| **Bypass Preflight**| `--yes, -y` | Bypass interactive terminal confirmation and launch immediately. | `False` |
| **Sensitive Reads** | `--allow-sensitive-reads` | In `--auth none` mode, allow sensitive content reads across restricted domains (`db`, `excel`, `excel_db`, `explorer`, `git`, `rag`, `ssh`, `word`, including `resources/read` and `prompts/get`). | `False` |
| **Server Scope** | `--allow-servers` / `--disallow-servers` | Comma-separated server allowlist or denylist (e.g. `excel,git` / `ssh,db`). | All servers |
| **Tool Scope** | `--allow-tools` / `--disallow-tools` | Comma-separated tool allowlist or denylist. | All tools |

---

## 🔗 Connecting Major Clients

### 1. Claude Web & Claude Desktop (Remote)
1. In Claude settings, add a Custom MCP Server over SSE/HTTP.
2. Enter the URL: `https://<your-tunnel-url>/sse` (or `/mcp`).
3. Claude will open the OAuth consent window.
4. Check your Windows terminal running `mws tunnel`, copy the 6-digit **Host-Owner Approval PIN**, paste it into the prompt, and approve.

### 2. MCP Inspector
To test your tunnel interactively using the official MCP Inspector:
```bash
npx @modelcontextprotocol/inspector
```
1. Set Transport to `SSE`.
2. Enter URL: `https://<your-tunnel-url>/sse`.
3. If using Bearer mode, add custom header: `Authorization: Bearer <your-token>`.
4. If using OAuth mode, the Inspector will navigate the PKCE handshake and prompt for authorization.

### 3. ChatGPT Custom GPTs / Web Actions
1. In ChatGPT GPT Builder, configure an Action pointing to the OpenAPI schema or MCP endpoint.
2. Choose Authentication Type:
   - **OAuth**: Point to `https://<your-tunnel-url>/.well-known/oauth-authorization-server`
   - **API Key**: Choose `Bearer` and supply the token printed by `mws tunnel --auth bearer`.

---

## 🔒 Security Architecture of the OAuth Engine

```mermaid
sequenceDiagram
    autonumber
    actor User as Machine Owner (Terminal)
    actor Remote as Remote Agent (Web Client)
    participant Edge as Tunnel / HTTPS Edge
    participant Tunnel as MWS Tunnel Server
    
    Remote->>Edge: POST /oauth/register (RFC 7591)
    Edge->>Tunnel: Forward DCR Request
    Tunnel-->>Remote: client_id, client_secret (if confidential)
    
    Remote->>Tunnel: GET /oauth/authorize?response_type=code&code_challenge=...&state=...
    Tunnel->>User: 🔑 Print 6-Digit Host-Owner Approval PIN in Terminal
    Tunnel-->>Remote: HTML Consent Form (CSRF Token Bound)
    
    Remote->>Tunnel: POST /oauth/approve (PIN + CSRF + decision=approve)
    Note over Tunnel: Verify CSRF Token & Terminal PIN
    Tunnel-->>Remote: 302 Redirect to redirect_uri?code=...&state=...
    
    Remote->>Tunnel: POST /oauth/token (code + code_verifier + client_id)
    Note over Tunnel: Constant-time S256 PKCE & Single-Use Code Burn
    Tunnel-->>Remote: 200 OK: access_token (HMAC-SHA256 signed)
    
    Remote->>Tunnel: POST /mcp (Authorization: Bearer <token>)
    Note over Tunnel: Clamp token scope: min(server_mode, token_scope)
    Tunnel-->>Remote: MCP Tool Execution Result
```

### RFC Compliance Endpoints

The tunnel server automatically serves all standard discovery and token endpoints:

* `GET /.well-known/oauth-authorization-server`: RFC 8414 metadata announcing PKCE `S256` support, code response types, and registration/authorization/token/revocation URIs.
* `GET /.well-known/oauth-protected-resource`: RFC 9728 resource metadata linking to the authorization server.
* `POST /oauth/register`: Dynamic Client Registration (RFC 7591) with loopback redirect URI validation (RFC 8252).
* `GET /oauth/authorize`: Interactive consent page with reflected XSS escaping (`html.escape`), CSRF tokens, and PIN challenge.
* `POST /oauth/approve`: Validates host-owner proof PIN and issues short-lived single-use authorization codes.
* `POST /oauth/token`: PKCE `code_verifier` validation, single-use code burning, and minting signed access tokens.
* `POST /oauth/revoke`: Token revocation endpoint (RFC 7009) with HMAC validation to protect against denial-of-service cache eviction.

---

## 🛑 Prerequisites & Troubleshooting

### 1. Modern Windows Environment Requirement
`mcp-win-stdio` targets modern Windows environments (Windows 10 Build 19041+ / Windows 11) where Windows Package Manager (`winget`) is natively supported. Legacy Windows builds without `winget` are not supported.

### 2. On-Demand Tunnel Binary Installation (`cloudflared` / `ngrok`)
`mws install` only installs the Python MCP server packages. Tunnel binaries are installed on demand by `mws tunnel` for whichever provider you choose:
* **`cloudflare`**: If `cloudflared` is missing, `mws tunnel` offers to install it via `winget install --id Cloudflare.cloudflared -e --accept-source-agreements --accept-package-agreements` (or `brew install cloudflared` on macOS).
* **`ngrok`**: If `ngrok` is missing, `mws tunnel` offers to install it via `winget install --id Ngrok.Ngrok -e --accept-source-agreements --accept-package-agreements` (or `brew install ngrok/ngrok/ngrok` on macOS).
* **`direct`**: No external tunnel binary is required; certificates are managed in `~/.mcp-win-stdio/certs/`.
* After installing a new CLI binary, restart your PowerShell/terminal session if prompted so the updated `PATH` is loaded.

### 3. Invalid Approval PIN (403 Forbidden)
If an approval submission fails, ensure you entered the exact 6-digit PIN displayed in the terminal where `mws tunnel` is running. PINs expire after 5 minutes or upon failed attempts.

### 4. Permission Denied on Tool Call
In `--mode read_only`, mutating operations (e.g., `execute_query` with DDL/DML, `git_commit`, `update_cells`, `write_file`) are blocked by the security middleware before the tool is invoked. To allow write actions, restart the tunnel with `--mode read_write`.
