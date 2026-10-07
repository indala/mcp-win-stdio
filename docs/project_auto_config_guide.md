# 🌐 Zero-Config Project & Repo Guide for AI Agents

> **Purpose:** How to configure your repositories so that **VS Code (1.106+)**, **Google Antigravity**, **GitHub Copilot**, **Claude Code CLI**, **Cursor**, and **Windsurf** automatically detect and load your `mws` MCP servers without manual setup.

---

## ⚠️ Important Note: VS Code 1.106+ `.mcp.json` Migration

> [!NOTE]
> **`.vscode/mcp.json` is deprecated as of VS Code version 1.106.**
> VS Code has unified MCP configuration to the workspace root **`.mcp.json`** file format.
> The `mws` CLI automatically detects legacy `.vscode/mcp.json` files, seamlessly migrates existing server definitions into `.mcp.json`, and cleans up `.vscode/mcp.json` to avoid deprecation warnings.

---

## 🤖 Does Antigravity & VS Code Pick Up Configurations Automatically?

**YES!** When you open any workspace/folder:
1. **Unified Root `.mcp.json` Auto-Discovery:** VS Code (1.106+), Google Antigravity, GitHub Copilot, Claude Code CLI, and Cursor natively detect and attach MCP servers defined in root `.mcp.json`.
2. **Context & Rules Auto-Loading:** Antigravity and Claude Code automatically load workspace instruction files (`CLAUDE.md`, `AGENTS.md`, and `.gemini/`).
3. **Zero Configuration for Teams:** Any developer or teammate who clones your repository immediately gets access to all MCP tools without re-running setup scripts.

---

## 📂 The Universal Repo Configuration Structure

Place these **2 files** at the root of any repository or project to make all AI agents auto-detect `mws`:

```
your-repo/
├── .mcp.json               <-- Unified standard (VS Code 1.106+, Antigravity, Copilot, Claude Code, Cursor)
└── AGENTS.md (or CLAUDE.md)<-- Read by all AI agents for project context & tool guidance
```

---

### 1️⃣ `.mcp.json` (Unified Workspace MCP Configuration)

Create `.mcp.json` in your project root (or generate it automatically using `mws init-project`):

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
> **Workspace Variables:** Root `.mcp.json` supports `${workspaceFolder}` variable expansion in environment variables or arguments (e.g. `"EXPLORER_ROOT": "${workspaceFolder}"`).

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

## ⚡ Matrix: Which Agent Auto-Detects Which File?

| AI Agent / IDE / Tool | Auto-Detects File | Supported Standard |
| :--- | :--- | :--- |
| **VS Code (1.106+)** | `.mcp.json` | ✅ **Yes (Official Standard)** |
| **Google Antigravity** | `.mcp.json`, `.gemini/`, `AGENTS.md` | ✅ **Yes (Zero Config)** |
| **GitHub Copilot (VS Code 1.106+)** | `.mcp.json` | ✅ **Yes** |
| **Claude Code CLI** | `.mcp.json`, `CLAUDE.md` | ✅ **Yes** |
| **Cursor IDE** | `.mcp.json`, `.cursor/mcp.json` | ✅ **Yes** |
| **Windsurf** | `.mcp.json`, `~/.codeium/windsurf/mcp_config.json` | ✅ **Yes** |
| **Claude Desktop** | `%APPDATA%\Claude\claude_desktop_config.json` | ✅ **Yes (Global Config)** |

---

## 🛠️ CLI Project Configuration Commands

You can configure project-level MCP files using the `mws` CLI directly:

### 1. Initialize Project (All or Specific Servers)
```powershell
# Configure all servers:
mws init-project

# Or configure only specific servers:
mws init-project excel db tsc
```
*(Creates `.mcp.json`, migrates and cleans legacy `.vscode/mcp.json` if found, and generates tailored `AGENTS.md`).*

### 2. Add / Setup Specific Server in Current Project
```powershell
# Add one or more servers without overwriting existing ones:
mws setup-project excel
mws add-project db excel-db
```

### 3. Remove Server from Current Project
```powershell
# Remove a server from .mcp.json:
mws remove-project ssh word
```

### 4. Automatic Legacy Migration
When running `mws init-project` or `mws setup-project` in any repo that previously had `.vscode/mcp.json`:
- All existing custom servers configured in `.vscode/mcp.json` are preserved and merged into `.mcp.json`.
- The deprecated `.vscode/mcp.json` file is deleted to keep your workspace clean and prevent VS Code 1.106+ deprecation notices.
