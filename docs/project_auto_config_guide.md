# 🌐 Project & Repository Configuration Guide for AI Agents

> **Purpose:** How to configure your repositories with project-level MCP configuration and agent guidance files for **ChatGPT Desktop / OpenAI Codex**, **Claude Code CLI**, **Cursor**, **Google Antigravity**, **VS Code / GitHub Copilot**, and **Windsurf**.

---

## ⚠️ Note on Client Configuration Files

> [!NOTE]
> MCP workspace configuration paths vary by client and version:
> - **`.mcp.json`** (repository root) is supported by **Claude Code CLI**, **Cursor** (alongside `.cursor/mcp.json`), and workspace tools that adopt the root `.mcp.json` convention (including recent **VS Code** releases under workspace discovery settings, alongside **`.vscode/mcp.json`**).
> - **Google Antigravity** loads global and workspace MCP settings (such as `.gemini/` / Antigravity's IDE MCP config) and reads workspace instruction files (`AGENTS.md`, `GEMINI.md`).
> - **ChatGPT Desktop and OpenAI Codex** share MCP configuration on the same Codex host. The global configuration is `%USERPROFILE%\.codex\config.toml`; ChatGPT Desktop also provides Settings → MCP servers to add a server, then restart the app. Codex CLI and the IDE extension use the same MCP configuration. A trusted workspace may use `.codex/config.toml`.
> - `mws` follows a **non-invasive, zero-mutation design**: the CLI never automatically modifies or deletes `.mcp.json`, `.vscode/mcp.json`, or global agent configuration files. Instead, use **`mws guide`** to generate copy-pasteable JSON/TOML snippets for your target client.

---

## 🤖 How Team Discovery & Setup Works

When another developer clones a repository that includes `.mcp.json` or agent instruction files (`AGENTS.md`, `CLAUDE.md`, `GEMINI.md`):
1. **Configuration Discovery:** Clients that support those files discover the configured server entries and usage guidelines from the repository.
2. **Prerequisites Required:** Cloning shares configuration, **not the runtime binaries**. Each developer must still install `mcp-win-stdio` (`pip install "mcp-win-stdio[all]"` or `pip install mcp-win-stdio` + `mws install <server>`) on their machine and configure local credentials/targets (`mws config db`, `mws config ssh`, `mws config tsc`).

---

## 📂 Recommended Repository Files

Place these files in your repository manually using snippets from `mws guide`:

```
your-repo/
├── .mcp.json                 <-- Project MCP config (Claude Code, Cursor, etc.)
├── .vscode/mcp.json          <-- Optional VS Code workspace MCP config
└── AGENTS.md (or CLAUDE.md)  <-- Project guidance read by AI agents
```

---

### 1️⃣ `.mcp.json` / Workspace MCP Configuration

You can configure individual servers or simply use the **Unified On-Demand Gateway** (`server`) which dynamically proxies all 233 modular tools across all 10 servers (plus 18 gateway tools) with minimal token overhead:

```json
{
  "mcpServers": {
    "mws": {
      "command": "python",
      "args": ["-m", "mcp_win_stdio.server"]
    }
  }
}
```

Or configure individual standalone servers if preferred:

```json
{
  "mcpServers": {
    "db": {
      "command": "mws",
      "args": ["run", "db"]
    },
    "excel": {
      "command": "mws",
      "args": ["run", "excel"]
    },
    "excel-db": {
      "command": "mws",
      "args": ["run", "excel-db"]
    },
    "rag": {
      "command": "mws",
      "args": ["run", "rag"]
    },
    "explorer": {
      "command": "mws",
      "args": ["run", "explorer"]
    },
    "git": {
      "command": "mws",
      "args": ["run", "git"]
    },
    "ssh": {
      "command": "mws",
      "args": ["run", "ssh"]
    },
    "tsc": {
      "command": "mws",
      "args": ["run", "tsc"]
    }
  }
}
```

> [!TIP]
> **Workspace Variables:** Client workspace configs such as `.mcp.json` / `.vscode/mcp.json` support `${workspaceFolder}` variable expansion in arguments or environment variables (e.g. `"EXPLORER_ROOT": "${workspaceFolder}"`).

---

### 2️⃣ `AGENTS.md` (Self-Describing AI Instruction Playbook)

Create `AGENTS.md` (or `CLAUDE.md`) in your project root so agents know which tools to use:

```markdown
# Repository Agent Guidelines

This repository is equipped with the **mcp-win-stdio (`mws`)** tool suite:

- **Database Queries:** Use `db` MCP (`read_query`, `describe_table`) or `excel-db` (`db_to_excel_stream`).
- **Spreadsheets:** Use `excel` MCP or `excel-db` power tools for direct data streaming.
- **Documentation & Research:** Use `rag` MCP (`query_knowledge_base`, `get_knowledge_tree`).
- **Code & Tree Exploration:** Use `explorer` MCP (`get_directory_tree`, `fuzzy_find`).
- **Git Operations:** Use `git` MCP for commits, diffs, and GitHub PR checks.
- **TypeScript Typechecking:** Use `tsc` MCP for real-time diagnostics.
```

---

## ⚡ Matrix: Which Agent Reads Which File?

| AI Agent / IDE / Tool | Workspace / Global Config Paths | Notes |
| :--- | :--- | :--- |
| **Claude Code CLI** | `.mcp.json`, `CLAUDE.md`, `~/.claude.json` | Native `.mcp.json` discovery |
| **Cursor IDE** | `.cursor/mcp.json`, `.mcp.json` | Supports workspace `.cursor/mcp.json` and root `.mcp.json` |
| **VS Code / GitHub Copilot** | `.vscode/mcp.json`, `.mcp.json` | Supports workspace `.vscode/mcp.json` (and `.mcp.json` when enabled) |
| **Google Antigravity** | Global Antigravity MCP config, `.gemini/`, `AGENTS.md` | Reads workspace rules/skills (`AGENTS.md`, `GEMINI.md`, `.gemini/`) |
| **Windsurf** | `~/.codeium/windsurf/mcp_config.json` | Global MCP config |
| **Claude Desktop** | `%APPDATA%\Claude\claude_desktop_config.json` | Global MCP config |

---

## 🛠️ Supported CLI Commands (`mws`)

Because `mws` uses a **non-invasive architecture**, the legacy file-mutating commands (`mws init`, `mws init-project`, `mws setup`, `mws setup-project`, `mws add`, `mws add-project`, `mws remove`, `mws remove-project`) are **retired** — running any of them prints a notice and directs you to `mws guide` without touching client or workspace config files.

### 1. Generate Client Snippets (`mws guide`)
```powershell
# Universal multi-agent snippet & paths:
mws guide

# Snippet for a specific client (e.g. gemini, claude, cursor, vscode):
mws guide gemini

# ChatGPT Desktop and Codex use the same TOML configuration:
mws guide openai  # aliases: mws guide chatgpt, mws guide codex

# Standalone server snippet for a specific client:
mws guide db claude
```

### 2. Configure Targets & Credentials (`mws config`)
```powershell
# Interactive wizards for database connections, SSH hosts, and TypeScript projects:
mws config db
mws config ssh
mws config tsc
```

### 3. Inspect Installation & Environment Readiness (`mws status` & `mws doctor`)
```powershell
# Read-only readiness report across all servers:
mws status

# Run diagnostic health checks (Python, COM, DB drivers, Git/gh CLI, SSH, PATH):
mws doctor
```
