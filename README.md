# mcp-win-stdio

Windows-optimized **Model Context Protocol (MCP)** suite and non-invasive CLI hub (`mws`) for local `stdio` execution and secure remote tunneling across all major AI IDEs, CLI agents, and desktop apps (Gemini, Antigravity, Claude, ChatGPT, Cursor, Kiro, OpenCode, Windsurf, Copilot, Codex).

[![PyPI Version](https://img.shields.io/pypi/v/mcp-win-stdio.svg)](https://pypi.org/project/mcp-win-stdio/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python: 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)

---

## 🌟 Highlights (233+ Audited Tools Across 10 Modular Servers)

* **Unified On-Demand Gateway & Workflow Engine (`mws server`)**: Configure just `mws server` (or `python -m mcp_win_stdio.server`) in Claude Desktop, Cursor, Gemini, or Antigravity. Dynamic discovery, routing, workflows, and lazy child-server startup avoid loading all 200+ tools into the agent context upfront.
* **Secure Remote Tunneling & OAuth 2.0 PKCE (`mws tunnel`)**: Expose local Windows tools to remote and web-based agents (Claude Web, ChatGPT Custom GPTs, Cursor, MCP Inspector) over encrypted Cloudflare Tunnels with terminal-generated 6-digit Host-Owner Approval PINs, PKCE (`S256`), and strict permission ceilings.
* **MCP Resources & Prompts Gateway**: Discover and read child-server resources, resource templates, and rendered prompts through `mws`, with cursor-based pagination and large-result artifact handling.
* **Agent-Synthesized Workflows (`.mws/workflows/`)**: AI agents and developers can chain multiple MCP tools into named composite pipelines with argument templating and error halting.
* **100% Dynamic & Zero-Env Architecture**: All configurations (databases, TypeScript projects, SSH hosts, Git repositories) are managed interactively and stored in `~/.mcp-win-stdio/`. No environment variables required in client configs!
* **Universal Multi-Agent Guide (`mws guide`)**: Generates tailored copy-paste configuration snippets and exact configuration file paths for 10 major AI agents without mutating user files.
* **Cascading Clean Uninstallation (`mws uninstall self`)**: Dynamically discovers and purges all installed `mcp-win-stdio-*` distributions in one atomic batch.
* **Git & GitHub MCP (46 Tools)**: Unified local Git management (init, remotes, restore, bookmarks, branches, commits, diffs) and remote GitHub CLI (`gh`) operations (PR checks, releases, issues, Actions).
* **Excel MCP (44 Tools)**: High-speed Pandas queries, multi-column reconciliation with RapidFuzz, native Excel Tables, row/col mutations, formulas, cell merging, workbook diffing, and Office COM automation.
* **Polyglot Database MCP (36 Tools)**: PostgreSQL & MySQL manager with dynamic connection hub, AST-validated safe read queries, transaction boundaries, schema diffing with migration SQL, Mermaid ERD, slow queries, and lock trees.
* **Multi-SSH MCP (34 Tools)**: Multi-host connection pooling, auto-discovery of `~/.ssh/config`, interactive PTY terminal sessions, detached background jobs, systemd/docker services, SFTP file management, and port forwarding.
* **Word MCP (20 Tools)**: Multi-unit geometry (in, cm, mm, pt), multi-column layout, typography, document authoring, template placeholder filling, and native Word COM PDF export.
* **Workspace Explorer MCP (14 Tools)**: Token-safe directory exploration, collapsible heavy folders, `.gitignore` resolution, in-file regex grep, RapidFuzz fuzzy search, and Python/TypeScript AST outlines.
* **TypeScript Diagnostic Watcher MCP (12 Tools)**: Persistent background `tsc` compiler watchers maintaining an in-memory cache for instantaneous (0ms latency) error inspection and actionable fixes.
* **RAG MCP (11 Tools)**: Multi-collection web crawling, incremental local and remote repository indexing, hybrid BM25 + TF-IDF search, and knowledge trees.
* **Excel & DB Power Engine MCP (9 Tools)**: Zero-context streaming from database to Excel, chunked upserting, in-memory cross-source SQL joins, automated reconciliation diffs, and migration planning.
* **Architecture Knowledge Graph MCP (5 Tools)**: Full-stack vertical blueprint flowcharts, execution trace down to storage entities, ERD diagrams, and blast-radius impact analysis.
* **Extensible User Plugins**: Drop any standalone Python MCP script into `~/.mcp-win-stdio/plugins/` and it is immediately discovered and proxied.

---

## 📦 Modular Architecture & Installation

Each server is published as an independent, lightweight PyPI package. Installing any standalone package automatically installs the `mws` CLI orchestrator.

| Server | Standalone Package | Tools | Primary Capabilities |
| :--- | :--- | :---: | :--- |
| **mws Server / Hub** | `pip install mcp-win-stdio` | Gateway | Unified On-Demand Gateway, Composite Workflow Engine, & Remote Tunnel Bridge |
| **Git & GitHub** | `pip install mcp-win-stdio-git` | 46 | Local Git init/remotes/restore/bookmarks/branches, commits, diffs + GitHub PR checks, releases, issues, Actions |
| **Excel** | `pip install mcp-win-stdio-excel` | 44 | Native Excel Tables, row/col mutations, formulas, Pandas queries, RapidFuzz reconciliation, Office COM automation |
| **Database** | `pip install mcp-win-stdio-db` | 36 | PostgreSQL & MySQL dynamic pooling, AST query defense, cross-schema resolution, index audits, schema diffs, Mermaid ERD |
| **SSH** | `pip install mcp-win-stdio-ssh` | 34 | Multi-host pooling, ~/.ssh/config discovery, PTY shells, background jobs, systemd/docker, package management, SFTP, tunnels |
| **Word** | `pip install mcp-win-stdio-word` | 20 | Margins (in, cm, mm, pt), multi-column layout, typography, document authoring, template filling, Office COM PDF export |
| **Explorer** | `pip install mcp-win-stdio-explorer` | 14 | Token-safe collapsible tree, .gitignore resolution, in-file grep, AST outlines, fuzzy search |
| **TypeScript** | `pip install mcp-win-stdio-tsc` | 12 | 0ms in-memory compilation error cache, dynamic multi-project config (add_project/use_project), multi-tsconfig watchers |
| **RAG** | `pip install mcp-win-stdio-rag` | 11 | Web crawling, local/remote repo indexing, hybrid BM25 + TF-IDF search, context and collection lifecycle |
| **Excel & DB** | `pip install mcp-win-stdio-excel-db` | 9 | Zero-context streaming, cross-joins, master reconciliation with tolerance, transactional migration plan, dry-run sync |
| **Arch** | `pip install mcp-win-stdio-arch` | 5 | Vertical full-stack blueprint flowcharts, execution trace down to storage entities, ERD, blast-radius analysis |

### Install Individual Servers:
```powershell
pip install mcp-win-stdio-git
pip install mcp-win-stdio-excel
pip install mcp-win-stdio-db
pip install mcp-win-stdio-ssh
pip install mcp-win-stdio-word
pip install mcp-win-stdio-explorer
pip install mcp-win-stdio-tsc
pip install mcp-win-stdio-rag
pip install mcp-win-stdio-excel-db
pip install mcp-win-stdio-arch
```

### Or Install the Complete Suite:
```powershell
pip install "mcp-win-stdio[all]"
```

### For Local Development:
```powershell
git clone https://github.com/indala/mcp-win-stdio.git
cd mcp-win-stdio
pip install -e .
```

---

## 🚀 Quick Start

### 1. Launch the Interactive Dashboard
```powershell
mws
```
Output:
```text
============================================================================
   🚀  mcp-win-stdio — Windows Model Context Protocol Suite (v0.4.7)
============================================================================

 Single-Source Hub:      C:\Users\admin\.mcp-win-stdio
 Claude Desktop Config:  C:\Users\admin\AppData\Roaming\Claude\claude_desktop_config.json
 Claude Code CLI Config: C:\Users\admin\.claude.json
----------------------------------------------------------------------------
SERVER       STATUS           TOOLS    DESCRIPTION
----------------------------------------------------------------------------
git          [Installed]      46       46 tools: Local Git branching, commits, GitHub PRs...
excel        [Installed]      44       44 tools: Pandas queries, RapidFuzz reconciliation...
db           [Installed]      36       36 tools: Polyglot multi-server pooling, AST defense...
ssh          [Installed]      34       34 tools: Multi-host SSH pooling, PTY, SFTP...
word         [Installed]      20       20 tools: Multi-unit margins, tables, typography...
explorer     [Installed]      14       14 tools: Token-safe collapsible tree, AST grep...
tsc          [Installed]      12       12 tools: Background tsc compiler watchers...
rag          [Installed]      11       11 tools: Web crawling, local & remote repo indexing...
excel-db     [Installed]      9        9 tools: Zero-context streaming, cross-joins...
arch         [Installed]      5        5 tools: Full-stack blueprints, execution tracing...
----------------------------------------------------------------------------
 💡 Quick Commands:
   mws guide             -> Universal setup instructions & config snippets
   mws server            -> Run Unified On-Demand Gateway (anti-bloat)
   mws tunnel            -> Expose tools securely to Claude/ChatGPT Web
   mws doctor            -> Run diagnostic health checks (COM, Python, DB, Git)
============================================================================
```

### 2. Configure Your AI Client
Use `mws guide` to inspect tailored configuration snippets without modifying any files:
```powershell
# Global overview across all agents:
mws guide

# Tailored for a specific client:
mws guide gemini
mws guide claude
mws guide cursor
```

Simply copy and paste the snippet provided into your AI IDE or desktop agent configuration.

---

## 🌐 Remote Access & Cloudflare Tunnels (`mws tunnel`)

Expose local Windows tools safely to web-based AI platforms like **Claude Web**, **ChatGPT Custom GPTs**, **Cursor**, and **MCP Inspector** without opening router ports or exposing static IP addresses.

### 1. Launch with OAuth 2.0 PKCE (Default & Recommended)
```powershell
mws tunnel
```
* **Host-Owner Proof**: When an authorized web client connects, `mws` displays a one-time 6-digit approval PIN in your terminal. Enter the PIN in the web browser consent window to approve access.
* **Permission Clamping**: Defaults to `--mode read_only`. Mutating actions (file writes, database updates, Git commits) are blocked automatically.

### 2. Launch with a Bearer Token
```powershell
# Auto-generate a secure 32-byte cryptographic token:
mws tunnel --auth bearer

# Or pass a pre-shared secret:
mws tunnel --auth bearer --token "my-secure-token"
```

### 3. Allow Read-Write Access
```powershell
mws tunnel --mode read_write
```

For complete documentation on OAuth 2.0 flows, PKCE verification, and connecting web clients, see:
👉 [Remote Access & Secure Cloudflare Tunneling Guide](docs/tunnel-and-remote-access.md)
👉 [Security Architecture & Defense-in-Depth](docs/security-architecture.md)

---

## 📖 CLI Commands Reference

`mws` follows a **zero-mutation, non-invasive philosophy**: it never automatically modifies your agent's configuration files behind your back.

| Command | Usage | Description |
| :--- | :--- | :--- |
| `mws` | — | Home dashboard showing suite health, supported agents, server statuses, and quick commands. |
| `mws server` | `mws server` | Runs the Unified On-Demand Gateway MCP server (loads 233+ tools dynamically, anti-bloat). |
| `mws tunnel` | `mws tunnel [--auth oauth\|bearer\|none] [--mode read_only\|read_write]` | Exposes local MWS tools to web agents via secure Cloudflare Tunnel with OAuth 2.0 PKCE. |
| `mws guide` | `mws guide [server] [client]` | **Universal Multi-Agent Guide**: copy-paste snippets, tool specs, and Windows config file paths. |
| `mws workflow` | `mws workflow [list\|run\|view\|delete]` | **Composite Workflows**: execute multi-step tool pipelines in zero LLM turns. |
| `mws run <server>` | `mws run tsc` | Launches an individual MCP server directly over stdio. |
| `mws config [domain]` | `mws config db` | Interactive terminal wizard to configure databases, SSH hosts, and TypeScript projects. |
| `mws doctor` | `mws doctor [--fix-path]` | Diagnostic health checks (Python, COM, DB, Git CLI, SSH, PATH). Pass `--fix-path` to auto-repair PATH. |
| `mws list` | — | Focused inventory of built-in servers and custom plugins with tool counts. |
| `mws status` | — | Reports server environment readiness without modifying any files. |
| `mws update [server]` | `mws update all` | Checks PyPI for new versions and upgrades the suite or specific server package. |
| `mws install <server>` | `mws install excel` | Installs standalone server packages from PyPI into your Python environment. |
| `mws uninstall <server>` | `mws uninstall self` | Uninstalls packages (use `self` to atomically purge all `mcp-win-stdio*` packages). |

---

## 🛠️ Complete Server Inventory

For full parameter details, schemas, and usage examples for all 233+ tools, refer to:
👉 [Complete MCP Servers & Tools Reference](docs/tools-reference.md)

* **Git & GitHub (46 tools)**: Comprehensive local git state machine, commits, branches, stashes, diffs, blame, and full GitHub CLI actions (PRs, releases, issues).
* **Excel (44 tools)**: Pandas dataframe queries, RapidFuzz 3-tab reconciliation, openpyxl styling, charts, and native Excel COM PDF export.
* **Polyglot Database (36 tools)**: PostgreSQL & MySQL pools, AST-guarded `read_query`, transaction isolation, index audits, schema diffs with migration scripts.
* **Multi-SSH (34 tools)**: Connection pooling, `~/.ssh/config` parsing, interactive PTY terminal emulation, background jobs, SFTP file transfer.
* **Word (20 tools)**: Physical margin geometry (in, cm, mm, pt), typography, tables, template placeholder substitution, and COM PDF export.
* **Workspace Explorer (14 tools)**: Collapsible heavy trees (`node_modules`), in-file regex grep, RapidFuzz filename search, and AST code outline.
* **TypeScript (12 tools)**: Instant 0ms cached error queries, multi-tsconfig compilation watchers, and suggested diagnostic fixes.
* **RAG (11 tools)**: Documentation web crawling, local/remote codebase chunking, and hybrid BM25 + TF-IDF knowledge base querying.
* **Excel & DB Power Engine (9 tools)**: Zero-context streaming from SQL to Excel, cross-source joins, master reconciliation, and migration plans.
* **Architecture Knowledge Graph (5 tools)**: Full-stack blueprint flowcharts, execution trace down to storage entities, and blast-radius impact analysis.

---

## 🔌 Custom Plugins

Drop any custom standalone Python MCP script into:
```text
%USERPROFILE%\.mcp-win-stdio\plugins\my_custom_mcp.py
```
`mcp-win-stdio` automatically discovers it:
* View it in `mws list` (or use `mws` for the full dashboard)
* Run it directly via `mws run my_custom_mcp`
* Access it on-demand through the Gateway (`mws server`)

---

## 📚 Detailed Documentation Index

* 🌐 [Remote Access & Secure Cloudflare Tunneling](docs/tunnel-and-remote-access.md)
* 🛡️ [Security Architecture & Defense-in-Depth](docs/security-architecture.md)
* 📖 [Complete MCP Servers & Tools Reference](docs/tools-reference.md)
* 🤖 [Repository Agent Guidelines (AGENTS.md)](AGENTS.md)
* 🤝 [Contributing Guide](CONTRIBUTING.md)
* 🔒 [Security Vulnerability Reporting Policy](SECURITY.md)

---

## 📜 License
MIT License. Copyright (c) 2026 Mohan Kumar Indala.
