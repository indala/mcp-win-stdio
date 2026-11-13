# Remote Access & Secure Cloudflare Tunneling

`mcp-win-stdio` includes a production-grade, zero-exposure remote bridge (`mws tunnel`) designed to securely expose your local Windows MCP tool suite to web-based AI clients (such as **Claude Web / Artifacts**, **ChatGPT Custom GPTs / Web**, **Cursor**, **Gemini**, and **MCP Inspector**) without opening inbound firewall ports or configuring router NAT.

---

## 🌟 Key Architecture & Security Highlights

* **Cloudflare Tunnel (`cloudflared`) Integration**: Creates an encrypted outbound-only tunnel to Cloudflare's edge network. No public IP address or port-forwarding required.
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
2. It provisions an ephemeral Cloudflare Tunnel and displays your public HTTPS endpoint:
   ```text
   ╭────────────────────────────────────────────────────────────────────────╮
   │ 🌐 PUBLIC MCP TUNNEL ONLINE                                            │
   │ Endpoint:  https://random-subdomain.trycloudflare.com/mcp               │
   │ Auth Mode: OAuth 2.0 (PKCE + DCR)                                      │
   │ Access:    READ ONLY (Protected by AST & engine transaction limits)    │
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

## ⚙️ CLI Flags & Options

| Option | Flag | Description | Default |
| :--- | :--- | :--- | :--- |
| **Auth Mode** | `--auth {oauth,bearer,none}` | Authentication mechanism required by the tunnel bridge. | `oauth` |
| **Access Mode** | `--mode, -m {read_only,read_write}` | Global permission ceiling for tool execution. | `read_only` |
| **Port** | `--port, -p <PORT>` | Local bridge port for the internal HTTP/SSE server. | `8080` |
| **Token** | `--token, -t <TOKEN>` | Custom Bearer token (only valid when `--auth bearer` is active). | Auto-generated |
| **Bypass Preflight**| `--yes, -y` | Bypass interactive terminal confirmation and launch immediately. | `False` |

---

## 🔗 Connecting Major Clients

### 1. Claude Web & Claude Desktop (Remote)
1. In Claude settings, add a Custom MCP Server over SSE/HTTP.
2. Enter the URL: `https://<your-subdomain>.trycloudflare.com/sse` (or `/mcp`).
3. Claude will open the OAuth consent window.
4. Check your Windows terminal running `mws tunnel`, copy the 6-digit **Host-Owner Approval PIN**, paste it into the prompt, and approve.

### 2. MCP Inspector
To test your tunnel interactively using the official MCP Inspector:
```bash
npx @modelcontextprotocol/inspector
```
1. Set Transport to `SSE`.
2. Enter URL: `https://<your-subdomain>.trycloudflare.com/sse`.
3. If using Bearer mode, add custom header: `Authorization: Bearer <your-token>`.
4. If using OAuth mode, the Inspector will navigate the PKCE handshake and prompt for authorization.

### 3. ChatGPT Custom GPTs / Web Actions
1. In ChatGPT GPT Builder, configure an Action pointing to the OpenAPI schema or MCP endpoint.
2. Choose Authentication Type:
   - **OAuth**: Point to `https://<your-subdomain>.trycloudflare.com/.well-known/oauth-authorization-server`
   - **API Key**: Choose `Bearer` and supply the token printed by `mws tunnel --auth bearer`.

---

## 🔒 Security Architecture of the OAuth Engine

```mermaid
sequenceDiagram
    autonumber
    actor User as Machine Owner (Terminal)
    actor Remote as Remote Agent (Web Client)
    participant Edge as Cloudflare Edge Proxy
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

### 2. Automatic `cloudflared` Installation via `winget`
`mws tunnel` relies on the official Cloudflare Tunnel CLI (`cloudflared`) to establish an encrypted outbound-only tunnel to Cloudflare's edge network:
* If `cloudflared` is not found on your system PATH, `mws tunnel` prompts to install it automatically via `winget`:
  ```powershell
  winget install --id Cloudflare.cloudflared -e --accept-source-agreements --accept-package-agreements
  ```
* This installs Cloudflare's officially signed Windows binary and registers it in your system PATH.
* After installation, if prompted, restart your PowerShell/terminal session so the updated PATH is loaded.

### 3. Invalid Approval PIN (403 Forbidden)
If an approval submission fails, ensure you entered the exact 6-digit PIN displayed in the terminal where `mws tunnel` is running. PINs expire after 5 minutes or upon failed attempts.

### 4. Permission Denied on Tool Call
In `--mode read_only`, mutating operations (e.g., `execute_query` with DDL/DML, `git_commit`, `update_cells`, `write_file`) are blocked by the security middleware before the tool is invoked. To allow write actions, restart the tunnel with `--mode read_write`.
