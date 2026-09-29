# mcp-win-stdio

Windows-optimized **Model Context Protocol (MCP)** suite and interactive CLI hub (`mws`) for local `stdio` execution with transparent Claude Desktop & Claude Code CLI configuration.

[![PyPI Version](https://img.shields.io/pypi/v/mcp-win-stdio.svg)](https://pypi.org/project/mcp-win-stdio/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python: 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)

---

## 🌟 Highlights (130 Tools Across 7 Modular Servers)

* **Interactive CLI Hub (`mws`)**: Run `mws` alone to view all servers, live installation status (`[Installed]` vs `[Not Installed]`), and quick commands.
* **Safe, Transparent Setup (`mws setup <server>` / `mws add <server>`)**: Installs missing dependencies on-demand, generates exact copy-pasteable JSON configuration for Claude Desktop and Claude Code CLI, and asks confirmation before making any automated edits (always creating `.bak` backups).
* **Dynamic Guide Merging (`mws guide [server]`)**: View comprehensive tool schemas, prompt recipes, and diagnostic checks for individual servers (`mws ssh guide`, `mws git guide`, `mws db guide`) or all installed servers merged (`mws guide all`).
* **Multi-SSH & Remote Management MCP (27 Tools)**: Advanced multi-host connection pooling, auto-discovery of `~/.ssh/config` aliases/identity files/ProxyJump, sticky active host routing, command execution, elevated `sudo` automation, interactive PTY terminal sessions, detached background jobs, systemd/docker/pm2 service inspection, package listing, log tailing, comprehensive SFTP file management, and background local port forwarding tunnels.
* **Git & GitHub MCP (33 Tools)**: Unified local Git repository management (init, remotes, restore, bookmarks, branching, commits, paginated diffs, conflicts) and remote GitHub CLI (`gh`) operations (PR checks, releases, issues, Actions) with hybrid synergy workflows.
* **Polyglot Database MCP (23 Tools)**: Unified PostgreSQL & MySQL database manager with cross-database switching, cross-schema auto-resolution, fast JSON queries, DBA administrative operations (safety-guarded DROP, CREATE, CLONE), active connection monitoring, index health audits, schema diffing, and native dump/restore utilities.
* **Excel MCP (20 Tools)**: High-speed Pandas data queries, multi-column reconciliation with RapidFuzz, cell & formula editing, and native Windows Excel COM automation (PDF exports, recalculation, pivot refreshes, VBA macros).
* **Word MCP (10 Tools)**: Multi-unit page layout geometry (margins in inches, cm, mm, pt), multi-column layout analysis, paragraph spacing/indentation, typography (fonts, sizes, hex colors), and floating/inline header image extraction.
* **Workspace Explorer MCP (11 Tools)**: Token-safe directory exploration, collapsible heavy folders (`node_modules`, `.next`, `.git`), dynamic `.gitignore` parsing, in-file regex grep, RapidFuzz fuzzy search, and Python/TypeScript AST outline extraction.
* **TypeScript Diagnostic Watcher MCP (6 Tools)**: Persistent background `tsc` compiler watchers maintaining an in-memory cache for instantaneous (0ms latency) error inspection across multi-tsconfig projects.
* **Extensible User Plugins**: Drop any standalone Python MCP script into `~/.mcp-win-stdio/plugins/` and it is immediately discovered, runnable, and configurable.

---

## 📦 Modular Architecture & Installation

Each server is published as an independent, lightweight PyPI package. Installing any standalone package automatically installs the `mws` CLI orchestrator.

| Server | Standalone Package | Tools | Primary Capabilities |
| :--- | :--- | :---: | :--- |
| **SSH** | `pip install mcp-win-stdio-ssh` | 27 | Multi-host pooling, ~/.ssh/config discovery, PTY shells, background jobs, systemd/docker, package management, SFTP, port forwarding |
| **Git & GitHub** | `pip install mcp-win-stdio-git` | 33 | Local Git init/remotes/restore/bookmarks/branches, commits, diffs + GitHub PR checks, releases, issues, Actions |
| **Database** | `pip install mcp-win-stdio-db` | 23 | PostgreSQL & MySQL pooling, cross-schema resolution, index audits, schema diffs, DBA management, dump/restore |
| **Excel** | `pip install mcp-win-stdio-excel` | 20 | Pandas queries, RapidFuzz reconciliation, OpenPyXL, native Excel COM automation |
| **Word** | `pip install mcp-win-stdio-word` | 10 | Margins (in, cm, mm, pt), multi-column IEEE layout, typography, image extraction |
| **Explorer** | `pip install mcp-win-stdio-explorer` | 11 | Token-safe tree, .gitignore resolution, in-file grep, AST outlines |
| **TypeScript** | `pip install mcp-win-stdio-tsc` | 6 | 0ms in-memory compilation error cache, multi-tsconfig watchers |

### Install Individual Servers:
```powershell
pip install mcp-win-stdio-ssh
pip install mcp-win-stdio-git
pip install mcp-win-stdio-db
pip install mcp-win-stdio-excel
pip install mcp-win-stdio-word
pip install mcp-win-stdio-explorer
pip install mcp-win-stdio-tsc
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
   🚀  mcp-win-stdio — Windows Model Context Protocol Suite (v0.2.4)
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
   mws list              -> List all servers and custom plugins
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

| Command | Shorthand / Alternate Syntax | Description |
| :--- | :--- | :--- |
| `mws` | `mws list` | Displays interactive terminal home dashboard with live server status, PyPI update alerts, and tips. |
| `mws install <server\|all>` | `mws <server> install` | Installs standalone server packages from PyPI. |
| `mws update <server\|all>` | `mws <server> update` | Checks PyPI for new versions and upgrades the suite or specific server. |
| `mws setup <server>` | `mws add <server>` / `mws <server> setup` | Guides setup, verifies dependencies, and generates Claude config snippets. |
| `mws remove <server>` | `mws <server> remove` | Safely removes server(s) from Claude Desktop and CLI configs. |
| `mws uninstall <server\|all>` | `mws <server> uninstall` | Cleanly uninstalls packages and removes Claude registrations while preserving your single-source hub (`~/.mcp-win-stdio`). |
| `mws guide [server]` | `mws <server> guide` | Prints tool reference, parameter schemas, and prompt recipes for Claude. |
| `mws doctor` | `mws <server> doctor` | Runs diagnostic health checks (Python, Git CLI, GitHub CLI, COM, DB drivers, PyPI updates). |
| `mws fix-path` | `mws path` | Checks and configures Python Scripts/bin directories in Windows User PATH. |
| `mws run <server>` | `mws <server> run` | Launches the MCP server over stdio. |


> [!TIP]
> If `mws` is not yet in Windows `PATH`, all commands can be executed using Python's module runner:
> ```powershell
> python -m mcp_win_stdio run git
> python -m mcp_win_stdio update all
> python -m mcp_win_stdio doctor
> ```


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

### ⚡ 6. TypeScript Diagnostic Watcher MCP (`mcp_win_stdio.tsc`) — 6 Tools
* **Instant Diagnostic Query**: `get_tsc_errors` (0ms in-memory cache), `get_file_errors`, `get_error_summary`.
* **Dynamic Watchers**: `list_watched_projects`, `watch_project(path)`, `restart_tsc_watcher`.

---

## 🔌 Custom Plugins from Other PCs

Have custom Python MCP scripts?
Simply place your script into:
```text
%USERPROFILE%\.mcp-win-stdio\plugins\my_custom_mcp.py
```
`mcp-win-stdio` automatically discovers it:
* View it in `mws list`
* Run it via `mws run my_custom_mcp`
* Add it to Claude via `mws setup my_custom_mcp`

---

## 📜 License
MIT License. Copyright (c) 2026 Mohan Kumar Indala.
