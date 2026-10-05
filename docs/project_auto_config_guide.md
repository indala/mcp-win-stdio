# 🌐 Zero-Config Project & Repo Guide for AI Agents

> **Purpose:** How to configure your repositories so that **Antigravity**, **GitHub Copilot**, **Claude Code CLI**, **Cursor**, and **Cline** automatically detect and load your `mws` MCP servers without manual setup.

---

## 🤖 Does Antigravity Pick Up Configurations Automatically?

**YES!** When you open any workspace/folder in Antigravity:
1. **MCP Auto-Discovery:** Antigravity automatically detects and attaches MCP servers configured in `.vscode/mcp.json` and `.mcp.json`.
2. **Context & Rules Auto-Loading:** It automatically loads workspace instruction files (`CLAUDE.md`, `AGENTS.md`, and `.gemini/`).
3. **Zero Configuration:** Any developer or teammate who clones your repository immediately gets access to all MCP tools without re-running setup scripts.

---

## 📂 The Universal Repo Configuration Structure

Place these **2 files** at the root of any repository or project to make all AI agents auto-detect `mws`:

```
your-repo/
├── .vscode/
│   └── mcp.json            <-- Auto-detected by Antigravity, VS Code & GitHub Copilot
├── .mcp.json               <-- Auto-detected by Claude Code CLI & Cursor
└── AGENTS.md (or CLAUDE.md)<-- Read by all AI agents for project context
```

---

### 1️⃣ `.vscode/mcp.json` (For Antigravity, VS Code & GitHub Copilot)

Create `.vscode/mcp.json` in your project root:

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

---

### 2️⃣ `.mcp.json` (For Claude Code CLI & Cursor)

Create `.mcp.json` in your project root (identical format):

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
    }
  }
}
```

---

### 3️⃣ `AGENTS.md` (Self-Describing AI Instruction Playbook)

Create `AGENTS.md` or `CLAUDE.md` in your project root so agents know which tools to use:

```markdown
# Repository Agent Guidelines

This repository is equipped with the **mcp-win-stdio (`mws`)** tool suite:

- **Database Queries:** Use `db` MCP (`read_query`, `describe_table`) or `excel-db` (`db_to_excel_stream`).
- **Spreadsheets:** Use `excel` MCP or `excel-db` power tools for direct data streaming.
- **Documentation & Research:** Use `rag` MCP (`query_knowledge_base`, `get_knowledge_tree`).
- **Code & Tree Exploration:** Use `explorer` MCP (`get_directory_tree`, `fuzzy_find`).
- **Git Operations:** Use `git` MCP for commits, diffs, and GitHub PR checks.
```

---

## ⚡ Matrix: Which Agent Auto-Detects Which File?

| AI Agent / Tool | Auto-Detects File | Auto-Loads on Open? |
| :--- | :--- | :--- |
| **Google Antigravity** | `.vscode/mcp.json`, `.mcp.json`, `.gemini/`, `AGENTS.md` | ✅ **Yes (Zero Config)** |
| **GitHub Copilot (VS Code)** | `.vscode/mcp.json`, `~/.copilot/mcp-config.json` | ✅ **Yes** |
| **Claude Code CLI** | `.mcp.json`, `CLAUDE.md` | ✅ **Yes** |
| **Cursor IDE** | `.cursor/mcp.json`, `.mcp.json` | ✅ **Yes** |
| **Roo Code / Cline** | `.vscode/mcp.json`, `.cline/mcp.json` | ✅ **Yes** |
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
*(Creates `.vscode/mcp.json`, `.mcp.json`, and tailored `AGENTS.md`).*

### 2. Add / Setup Specific Server in Current Project
```powershell
# Add one or more servers without overwriting existing ones:
mws setup-project excel
mws add-project db excel-db
```

### 3. Remove Server from Current Project
```powershell
# Remove a server from .vscode/mcp.json and .mcp.json:
mws remove-project ssh word
```
