# mcp-win-stdio

Windows-optimized **Model Context Protocol (MCP)** suite and non-invasive CLI hub (`mws`) for local `stdio` execution across all major AI IDEs, CLI agents, and desktop apps (Gemini, Antigravity, Claude, ChatGPT, Cursor, Kiro, OpenCode, Windsurf, Copilot, Codex).

[![PyPI Version](https://img.shields.io/pypi/v/mcp-win-stdio.svg)](https://pypi.org/project/mcp-win-stdio/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python: 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)

---

## 🌟 Highlights (230+ Tools Across 10 Modular Servers)

* **Unified On-Demand Gateway & Workflow Engine (`mws server`)**: Configure just `mws server` (or `python -m mcp_win_stdio.server`) in Claude Desktop, Cursor, Gemini, or Antigravity. Instead of dumping 200+ tools (35,000+ tokens) into the context window, it exposes 10 lightweight meta-tools (~500 tokens) that lazily spawn child servers and execute agent-synthesized multi-step workflows in 0 LLM turns!
* **Agent-Synthesized Workflows (`.mws/workflows/`)**: AI agents and developers can chain multiple MCP tools into named composite pipelines with argument templating and error halting.
* **100% Dynamic & Zero-Env Architecture**: All configurations (databases, TypeScript projects, SSH hosts, Git repositories) are managed interactively and stored in `~/.mcp-win-stdio/`. No environment variables required in client configs!
* **Universal Multi-Agent Guide (`mws guide`)**: Generates tailored copy-paste configuration snippets and exact configuration file paths for 10 major AI agents without mutating user files.
* **Cascading Clean Uninstallation (`mws uninstall self`)**: Dynamically discovers and purges all installed `mcp-win-stdio-*` distributions in one atomic batch.
* **Excel MCP (44 Tools)**: High-speed Pandas queries, multi-column reconciliation with RapidFuzz, native Excel Tables, row/col mutations, formulas, cell merging, workbook diffing, and Office COM automation.
* **Git & GitHub MCP (46 Tools)**: Unified local Git management (init, remotes, restore, bookmarks, branches, commits, diffs) and remote GitHub CLI (`gh`) operations (PR checks, releases, issues, Actions).
* **Multi-SSH MCP (34 Tools)**: Multi-host connection pooling, auto-discovery of `~/.ssh/config`, interactive PTY terminal sessions, detached background jobs, systemd/docker services, SFTP file management, and port forwarding.
* **Polyglot Database MCP (34 Tools)**: PostgreSQL & MySQL manager with dynamic connection hub, cross-schema resolution, index health audits, schema diffing with migration SQL, Mermaid ERD, slow queries, lock trees, and streaming export/import.
* **Word MCP (20 Tools)**: Multi-unit geometry (in, cm, mm, pt), multi-column layout, typography, document authoring, template placeholder filling, and native Word COM PDF export.
* **Workspace Explorer MCP (14 Tools)**: Token-safe directory exploration, collapsible heavy folders, `.gitignore` resolution, in-file regex grep, RapidFuzz fuzzy search, and Python/TypeScript AST outlines.
* **Excel & DB Power Engine MCP (9 Tools)**: Zero-context streaming from database to Excel, chunked upserting, in-memory cross-source SQL joins, automated reconciliation diffs, and migration planning.
* **TypeScript Diagnostic Watcher MCP (12 Tools)**: Persistent background `tsc` compiler watchers maintaining an in-memory cache for instantaneous (0ms latency) error inspection and actionable fixes.
* **RAG MCP (10 Tools)**: Multi-collection web crawling, incremental local and remote repository indexing, hybrid BM25 + TF-IDF search, and knowledge trees.
* **Architecture Knowledge Graph MCP (5 Tools)**: Full-stack vertical blueprint flowcharts, execution trace down to storage entities, ERD diagrams, and blast-radius impact analysis.
* **Extensible User Plugins**: Drop any standalone Python MCP script into `~/.mcp-win-stdio/plugins/` and it is immediately discovered and proxied.

---

## 📦 Modular Architecture & Installation

Each server is published as an independent, lightweight PyPI package. Installing any standalone package automatically installs the `mws` CLI orchestrator.

| Server | Standalone Package | Tools | Primary Capabilities |
| :--- | :--- | :---: | :--- |
| **mws Server** | `pip install mcp-win-stdio` | 10 | Unified On-Demand Gateway, Composite Workflow Engine, & Dynamic Process Orchestrator |
| **Excel** | `pip install mcp-win-stdio-excel` | 44 | Native Excel Tables, row/col mutations, formulas, Pandas queries, RapidFuzz reconciliation, Office COM automation |
| **Git & GitHub** | `pip install mcp-win-stdio-git` | 46 | Local Git init/remotes/restore/bookmarks/branches, commits, diffs + GitHub PR checks, releases, issues, Actions |
| **SSH** | `pip install mcp-win-stdio-ssh` | 34 | Multi-host pooling, ~/.ssh/config discovery, PTY shells, background jobs, systemd/docker, package management, SFTP, tunnels |
| **Database** | `pip install mcp-win-stdio-db` | 34 | PostgreSQL & MySQL dynamic pooling, ~/.mcp-win-stdio config, cross-schema resolution, index audits, schema diffs, Mermaid ERD |
| **Word** | `pip install mcp-win-stdio-word` | 20 | Margins (in, cm, mm, pt), multi-column layout, typography, document authoring, template filling, Office COM PDF export |
| **Explorer** | `pip install mcp-win-stdio-explorer` | 14 | Token-safe collapsible tree, .gitignore resolution, in-file grep, AST outlines, fuzzy search |
| **Excel & DB** | `pip install mcp-win-stdio-excel-db` | 9 | Zero-context streaming, cross-joins, master reconciliation with tolerance, transactional migration plan, dry-run sync |
| **TypeScript** | `pip install mcp-win-stdio-tsc` | 12 | 0ms in-memory compilation error cache, dynamic multi-project config (add_project/use_project), multi-tsconfig watchers |
| **RAG** | `pip install mcp-win-stdio-rag` | 10 | Web crawling, local/remote repo indexing, hybrid BM25 + TF-IDF search, context and collection lifecycle |
| **Arch** | `pip install mcp-win-stdio-arch` | 5 | Vertical full-stack blueprint flowcharts, execution trace down to storage entities, ERD, blast-radius analysis |

### Install Individual Servers:
```powershell
pip install mcp-win-stdio-excel
pip install mcp-win-stdio-git
pip install mcp-win-stdio-ssh
pip install mcp-win-stdio-db
pip install mcp-win-stdio-word
pip install mcp-win-stdio-explorer
pip install mcp-win-stdio-excel-db
pip install mcp-win-stdio-tsc
pip install mcp-win-stdio-rag
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
   🚀  mcp-win-stdio — Windows Model Context Protocol Suite (v0.4.3)
============================================================================

 Single-Source Hub:      C:\Users\admin\.mcp-win-stdio
 Claude Desktop Config:  C:\Users\admin\AppData\Roaming\Claude\claude_desktop_config.json
 Claude Code CLI Config: C:\Users\admin\.claude.json
----------------------------------------------------------------------------
SERVER       STATUS           TOOLS    DESCRIPTION
----------------------------------------------------------------------------
excel        [Installed]      20       20 tools: Pandas queries, RapidFuzz...
word         [Installed]      10       10 tools: multi-unit margins (in, cm...
explorer     [Installed]      11       11 tools: token-safe collapsible tree...
tsc          [Installed]      6        6 tools: background tsc compiler...
db           [Installed]      20       20 tools: polyglot multi-server p...
git          [Installed]      26       26 tools: Local Git branching, co...
----------------------------------------------------------------------------
 💡 Quick Commands:
   mws setup <server>    -> Configure Claude Desktop & Claude Code CLI
   mws guide <server>    -> View complete tool reference & Claude prompts
   mws doctor            -> Run health checks (COM, Python, DB, Git)
   mws run <server>      -> Launch MCP server over stdio
   mws list              -> Show concise server inventory
============================================================================
```

### 2. Configure a Server for Claude
```powershell
mws setup git
# or:
mws add db
```
`mws` verifies dependencies, generates absolute-path configurations (preventing Windows PATH lookup failures), and optionally writes directly to your Claude Desktop config with automatic backup.

---

## 📖 CLI Commands

mws follows a **zero-mutation, non-invasive philosophy**: it never automatically modifies your agent's configuration files. Use `mws guide` to inspect copy-paste configuration snippets and exact file paths for your AI client.

| Command | Usage | Description |
| :--- | :--- | :--- |
| `mws` | — | Home dashboard showing suite health, supported agents, server statuses, and quick commands. |
| `mws guide` | `mws guide [server] [client]` | **Universal Multi-Agent Guide**: copy-paste snippets, tool references, and Windows config file paths. |
| `mws server` | `mws server run` | Runs the Unified On-Demand Gateway MCP server (loads all 230+ tools dynamically, anti-bloat). |
| `mws workflow` | `mws workflow [list|run|view|delete]` | **Composite Workflows**: execute multi-step tool pipelines in zero LLM turns. |
| `mws run <server>` | `mws run tsc` | Launches an individual MCP server directly over stdio. |
| `mws config [domain]` | `mws config db` | Interactive terminal wizard to configure databases, SSH hosts, and TypeScript projects. |
| `mws doctor` | `mws doctor [--fix-path]` | Diagnostic health checks (Python, COM, DB, Git CLI, SSH, PATH). Pass `--fix-path` to auto-repair PATH. |
| `mws list` | — | Focused inventory of built-in servers and custom plugins with tool counts. |
| `mws status` | — | Reports server environment readiness without modifying any files. |
| `mws update [server]` | `mws update all` | Checks PyPI for new versions and upgrades the suite or specific server package. |
| `mws install <server>` | `mws install excel` | Installs standalone server packages from PyPI into your Python environment. |
| `mws uninstall <server>` | `mws uninstall self` | Uninstalls packages (use `self` to atomically purge all `mcp-win-stdio*` packages). |


### 🧭 Universal Guide Examples (`mws guide`)

| Scenario | Command | What It Shows |
| :--- | :--- | :--- |
| **All Agents & Servers** | `mws guide` | Global overview with Unified Gateway snippet and config paths for all 10 supported AI clients. |
| **Client Setup** | `mws guide gemini` | Recommended Unified Gateway snippet, instructions, and Windows paths for Gemini / Antigravity. |
| **Server Reference** | `mws guide tsc` | Standalone server snippet for `mcpServers`, Windows config paths, and full tool specifications. |
| **Client-Tailored Server** | `mws guide tsc gemini` | Ready-to-copy snippet and step-by-step instructions specifically for `tsc` on Gemini / Antigravity. |
| **ChatGPT Desktop** | `mws guide chatgpt` | Ready-to-copy snippet and developer config file path for ChatGPT Desktop. |
| **Cursor AI** | `mws guide cursor` | Ready-to-copy snippet and settings path for Cursor IDE. |
| **Kiro IDE** | `mws guide kiro` | Ready-to-copy snippet and config file path for Kiro IDE. |
| **OpenCode** | `mws guide opencode` | Ready-to-copy snippet and configuration path for OpenCode. |
| **OpenAI Codex** | `mws guide codex` | TOML-formatted configuration snippet for `~/.codex/config.toml`. |

> [!NOTE]
> The legacy auto-setup commands (`setup`, `init`, `remove`) have been retired. `mws` does not modify your IDE configuration files behind your back; simply copy and paste the snippet provided by `mws guide`!


---

## 🛠️ The 6 MCP Servers (103 Tools)

### 🐙 1. Git & GitHub MCP (`mcp_win_stdio.git`) — 33 Tools
* **Local Git Suite (20 Tools)**: `git_init`, `git_remote`, `git_restore`, `use_repo`, `list_repos`, `add_repo`, `remove_repo`, `rename_alias`, `git_status`, `git_diff` (with offset pagination), `git_log`, `git_commit` (with untracked safeguards), `git_branch`, `git_stash`, `git_sync`, `git_blame`, `git_reset`, `git_tag`, `git_grep`, `git_worktree`, `git_config`, `git_conflict_resolve`, `git_cherry_pick`, `git_clean_untracked`.
* **Remote GitHub CLI Suite (10 Tools)**: `gh_auth_status`, `gh_switch_account`, `gh_pr_list`, `gh_pr_view`, `gh_pr_diff`, `gh_pr_checkout`, `gh_pr_action`, `gh_pr_checks`, `gh_pr_review_comments`, `gh_release_list`, `gh_release_create`, `gh_issue_list`, `gh_issue_view`, `gh_issue_create`, `gh_issue_comment`, `gh_run_status`, `gh_gist_create`, `gh_search`, `gh_api`.
* **Hybrid Synergy Workflows (3 Tools)**:
  * `repo_overview`: 360-degree status combining local branch, dirty status, ahead/behind tracking, active open PR, and latest GitHub Actions workflow run.
  * `pr_quickstart`: Stage $\rightarrow$ Commit $\rightarrow$ Push $\rightarrow$ Create PR via `gh pr create` in one turn.
  * `issue_start_work`: Fetches issue from GitHub and creates a linked local branch `feature/<id>-<slug>`.

### 🗄️ 2. Polyglot Database MCP (`mcp_win_stdio.db`) — 23 Tools
* **Inspection & Resolution**: `list_connections`, `use_database`, `list_databases`, `list_schemas`, `describe_table` (auto cross-schema lookup), `get_table_ddl`, `schema_overview`, `compact_schema_overview`, `get_table_sample`, `search_schema`.
* **Execution & Diagnostics**: `read_query` (safe SELECT with row counts), `execute_query` (DML/DDL transactions), `explain_query` (EXPLAIN plans), `get_database_stats`, `analyze_table_indexes`, `compare_schemas` (structural diff with migration SQL), `audit_database_health` (unindexed FKs, bloated tables).
* **DBA Management**: `add_connection`, `create_database`, `drop_database` (safety confirmation required), `clone_database` (instant PostgreSQL TEMPLATE clone), `terminate_connections`, `list_active_queries`.
* **Native Utilities**: `dump_database` (`pg_dump`/`mysqldump`), `restore_database` (`psql`/`mysql`).

### 📊 3. Excel MCP (`mcp_win_stdio.excel`) — 20 Tools
* **Pandas Querying**: `query_rows`, `read_range`, `get_column_values`, `compare_column_values`, `summarize_column`, `search_text`.
* **Reconciliation**: `analyze_reconciliation_keys`, `reconcile_and_merge` (RapidFuzz fuzzy joins + 3-tab audit workbook).
* **OpenPyXL Editing**: `create_workbook`, `append_rows`, `add_sheet`, `rename_sheet`, `delete_sheet`, `update_cells`, `export_to_csv`, `export_to_json`.
* **Native Windows Excel COM**: `recalculate_and_save`, `export_to_pdf`, `refresh_data_and_pivots`, `run_vba_macro`, `get_active_excel_window`.

### 📝 4. Word MCP (`mcp_win_stdio.word`) — 10 Tools
* **Layout Geometry**: `get_document_layout` (margins in inches, cm, mm, pt, paper format, multi-column layout, section breaks).
* **Typography & Spacing**: `get_paragraph_spacing_and_indentation`, `get_document_typography` (fonts, sizes in pt, hex colors).
* **Visuals & Tables**: `get_document_images` (inline vs floating anchor images, placement offsets, dimensions), `get_document_tables`, `get_headers_and_footers`.
* **Content & Search**: `read_word_document`, `search_word_document`, `get_document_outline`, `get_document_metadata`.

### 📁 5. Workspace Explorer MCP (`mcp_win_stdio.explorer`) — 11 Tools
* **Token-Safe Navigation**: `list_dir`, `get_directory_tree` (collapses `node_modules`, `.next`, `dist`, `.git`).
* **Search**: `find_files` (glob matching), `fuzzy_find` (RapidFuzz typo-tolerant search), `grep_search` (in-file regex grep with context lines).
* **Code Intelligence**: `get_code_outline` (AST extractor for Python classes/methods and JS/TS signatures), `get_file_info`, `workspace_summary`, `export_tree_to_file`.
* **Safe Reading**: `read_file` (windowed line slicing, binary safeguard), `read_head_tail`.

### ⚡ 6. TypeScript Diagnostic Watcher MCP (`mcp_win_stdio.tsc`) — 12 Tools
* **Dynamic Multi-Project Config**: `list_projects`, `use_project(alias_or_path)`, `add_project(path, alias)`, `remove_project(alias_or_path)`.
* **Instant Diagnostic Query**: `get_tsc_errors` (0ms in-memory cache), `get_file_errors`, `get_error_summary`, `get_error_category_breakdown`, `suggest_error_fixes`.
* **Dynamic Watchers**: `list_watched_projects`, `watch_project(path)`, `restart_tsc_watcher`.

---

## 🔌 Custom Plugins from Other PCs

Have custom Python MCP scripts?
Simply place your script into:
```text
%USERPROFILE%\.mcp-win-stdio\plugins\my_custom_mcp.py
```
`mcp-win-stdio` automatically discovers it:
* View it in `mws list` (or use `mws` for the full dashboard)
* Run it via `mws run my_custom_mcp`
* Add it to Claude via `mws setup my_custom_mcp`

---

## 📜 License
MIT License. Copyright (c) 2026 Mohan Kumar Indala.
