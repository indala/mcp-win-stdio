# Complete MCP Servers & Tools Reference

The `mcp-win-stdio` (`mws`) suite provides **233 audited tools** organized across 10 modular, independently published PyPI packages, accessible standalone or orchestrated on-demand via the Unified Gateway (`mws server`).

---

## 📦 Package Summary

| Package | Standalone PyPI Distribution | Tools | Domain |
| :--- | :--- | :---: | :--- |
| **mws Server / Hub** | `mcp-win-stdio` | Gateway | Anti-bloat dynamic tool router, workflow engine, and tunnel bridge |
| **Git & GitHub** | `mcp-win-stdio-git` | 46 | Local repository operations, bookmarks, diffs, and GitHub CLI workflows |
| **Excel** | `mcp-win-stdio-excel` | 44 | Pandas querying, cell formatting, formulas, fuzzy reconciliation, COM automation |
| **Database** | `mcp-win-stdio-db` | 36 | PostgreSQL & MySQL connection pooling, schema diffs, index audits, safe queries |
| **SSH** | `mcp-win-stdio-ssh` | 34 | Multi-host connection pool, PTY terminal sessions, background jobs, SFTP |
| **Word** | `mcp-win-stdio-word` | 20 | Multi-unit geometry, typography, tables, template filling, COM PDF export |
| **Explorer** | `mcp-win-stdio-explorer` | 14 | Token-safe collapsible tree, AST code outlines, regex grep, fuzzy search |
| **TypeScript** | `mcp-win-stdio-tsc` | 12 | 0ms in-memory cache, multi-project watchers, actionable diagnostic fixes |
| **RAG** | `mcp-win-stdio-rag` | 11 | Web crawling, local & remote repository indexing, hybrid BM25 + TF-IDF search |
| **Excel & DB** | `mcp-win-stdio-excel-db` | 9 | Zero-context streaming from DB to Excel, chunked upserts, cross-source joins |
| **Arch** | `mcp-win-stdio-arch` | 5 | Vertical full-stack blueprint flowcharts, execution tracing, ERD diagrams |

---

## 🛠️ Detailed Tool Breakdown by Server

### 1. Git & GitHub MCP (`mcp-win-stdio-git`) — 46 Tools
* **Local Git Management**: `git_init`, `git_remote`, `git_restore`, `use_repo`, `list_repos`, `add_repo`, `remove_repo`, `rename_alias`, `git_status`, `git_diff`, `git_log`, `git_commit`, `git_branch`, `git_stash`, `git_sync`, `git_blame`, `git_reset`, `git_tag`, `git_grep`, `git_worktree`, `git_config`, `git_conflict_resolve`, `git_cherry_pick`, `git_clean_untracked`.
* **GitHub CLI Integration (`gh`)**: `gh_auth_status`, `gh_switch_account`, `gh_pr_list`, `gh_pr_view`, `gh_pr_diff`, `gh_pr_checkout`, `gh_pr_action`, `gh_pr_checks`, `gh_pr_review_comments`, `gh_release_list`, `gh_release_create`, `gh_issue_list`, `gh_issue_view`, `gh_issue_create`, `gh_issue_comment`, `gh_run_status`, `gh_gist_create`, `gh_search`, `gh_api`.
* **Synergy Workflows**:
  * `repo_overview`: Consolidated 360° health combining branch state, commit ahead/behind, open pull request, and active GitHub Actions runs.
  * `pr_quickstart`: Stage, commit, push, and open PR in one turn.
  * `issue_start_work`: Fetches issue metadata and branches cleanly to `feature/<id>-<slug>`.

### 2. Polyglot Database MCP (`mcp-win-stdio-db`) — 36 Tools
* **Schema & Inspection**: `list_connections`, `use_database`, `list_databases`, `list_schemas`, `describe_table` (automatic cross-schema resolution), `get_table_ddl`, `schema_overview`, `compact_schema_overview`, `get_table_sample`, `search_schema`, `generate_erd`.
* **Execution & Diagnostics**: `read_query` (hardened read-only execution with AST parsing and database-level transaction limits), `execute_query` (transactional DDL/DML), `explain_query`, `undo_query`, `get_database_stats`, `analyze_table_indexes`, `compare_schemas` (structural diff with migration SQL), `audit_database_health` (unindexed foreign keys, dead tuples, table bloat), `list_slow_queries`, `get_locks`, `diff_data`.
* **Connection & DBA Operations**: `add_connection`, `edit_connection`, `remove_connection`, `test_connection`, `create_database`, `drop_database` (safety confirmation required), `clone_database` (instant template clone on PostgreSQL), `terminate_connections`, `list_active_queries`, `get_audit_log`.
* **Streaming Utilities**: `dump_database` (`pg_dump`/`mysqldump`), `restore_database` (`psql`/`mysql`), `export_table`, `import_csv`.

### 3. Excel MCP (`mcp-win-stdio-excel`) — 44 Tools
* **Pandas Querying & Analysis**: `query_rows`, `read_range`, `get_column_values`, `compare_column_values`, `summarize_column`, `search_text`, `profile_sheet`, `query_excel_sql`.
* **Reconciliation & Merging**: `analyze_reconciliation_keys`, `reconcile_and_merge` (RapidFuzz fuzzy joins with 3-tab audit workbook).
* **OpenPyXL Editing & Formatting**: `create_workbook`, `append_rows`, `add_sheet`, `rename_sheet`, `delete_sheet`, `update_cells`, `write_range`, `format_cells`, `get_cell_formatting`, `apply_conditional_formatting`, `set_sheet_layout_and_freeze`, `clean_and_deduplicate_sheet`, `transform_sheet_data`, `export_transformed_workbook`, `audit_formulas`, `search_and_replace_cells`, `create_table`, `list_tables`, `insert_column`, `delete_column`, `insert_rows`, `delete_rows`, `merge_cells`, `diff_workbooks`, `create_chart`, `export_to_csv`, `export_to_json`.
* **Native Windows COM Automation**: `recalculate_and_save`, `export_to_pdf`, `refresh_data_and_pivots`, `run_vba_macro`, `get_active_excel_window`.

### 4. Multi-SSH MCP (`mcp-win-stdio-ssh`) — 34 Tools
* **Host Management**: `list_hosts`, `use_host`, `add_host`, `remove_host`, `test_host`, `list_active_connections`, `disconnect_host`, `ssh_system_overview`.
* **Execution & Interactive Shells**: `ssh_exec`, `ssh_exec_sudo`, `ssh_exec_script`, `ssh_exec_background`, `ssh_check_job`, `ssh_kill_job`, `ssh_pty_start`, `ssh_pty_send`, `ssh_pty_read`, `ssh_list_pty_sessions`, `ssh_pty_close`.
* **Remote Service & Package Management**: `ssh_list_packages`, `ssh_list_services`, `ssh_service_action` (start, stop, restart systemd units), `ssh_tail_logs`, `ssh_list_processes`.
* **SFTP & Port Forwarding**: `sftp_list_dir`, `sftp_read_file`, `sftp_write_file`, `sftp_stat`, `sftp_upload`, `sftp_download`, `sftp_remove`, `ssh_tunnel_open`, `ssh_tunnel_list`, `ssh_tunnel_close`.

### 5. Word MCP (`mcp-win-stdio-word`) — 20 Tools
* **Geometry & Layout**: `get_document_layout` (margins in inches, cm, mm, pt, orientation, section breaks), `get_paragraph_spacing_and_indentation`.
* **Typography & Styles**: `get_document_typography` (font names, point sizes, hex colors).
* **Images & Tables**: `get_document_images` (inline vs anchored floating graphics, dimensions, placement), `get_document_tables`, `insert_table`, `insert_image`.
* **Document Authoring**: `create_document`, `add_paragraph`, `add_heading`, `fill_template` (placeholder substitution), `replace_text`, `edit_paragraph`.
* **Inspection & Conversion**: `read_word_document`, `search_word_document`, `get_document_outline`, `get_document_metadata`, `get_headers_and_footers`, `inspect_revisions_and_comments`, `export_to_pdf` (Word COM automation).

### 6. Workspace Explorer MCP (`mcp-win-stdio-explorer`) — 14 Tools
* **Token-Safe Directory Navigation**: `list_dir`, `get_directory_tree` (collapses heavy dependencies like `node_modules`, `.next`, `dist`, `.git`), `workspace_summary`, `export_tree_to_file`.
* **Fast Search**: `find_files` (glob matching), `fuzzy_find` (RapidFuzz typo-tolerant filename searching), `grep_search` (in-file regex grep with context windows).
* **Code Intelligence**: `get_code_outline` (AST extraction of Python classes/functions and JS/TS signatures), `get_file_info`, `find_symbol`, `get_code_stats`, `find_duplicate_files`.
* **Safe Content Access**: `read_file` (windowed line slicing with binary protection), `read_head_tail`.

### 7. TypeScript Diagnostic Watcher MCP (`mcp-win-stdio-tsc`) — 12 Tools
* **Dynamic Multi-Project Registry**: `list_projects`, `use_project`, `add_project`, `remove_project`.
* **Instant Diagnostic Querying**: `get_tsc_errors` (0ms in-memory cache), `get_file_errors`, `get_error_summary`, `get_error_category_breakdown`, `suggest_error_fixes`.
* **Compiler Watchers**: `list_watched_projects`, `watch_project`, `restart_tsc_watcher`.

### 8. RAG Knowledge Base MCP (`mcp-win-stdio-rag`) — 11 Tools
* **Ingestion & Crawling**: `crawl_and_index_url` (crawls documentation and extracts content), `index_local_codebase`, `index_remote_repo`.
* **Hybrid Search & Retrieval**: `query_knowledge_base` (hybrid BM25 + TF-IDF semantic retrieval), `find_related_chunks`, `get_chunk_context`, `get_knowledge_tree`.
* **Lifecycle & Maintenance**: `list_rag_collections`, `rag_status`, `delete_rag_collection`, `prune_rag_cache`.

### 9. Excel & DB Power Engine MCP (`mcp-win-stdio-excel-db`) — 9 Tools
* **Zero-Context Streaming**: `db_to_excel_stream` (streams millions of database rows directly to Excel without loading data into the LLM context window).
* **Chunked Batch Upserting**: `excel_to_db_upsert` (bulk-inserts Excel data into PostgreSQL or MySQL with validation).
* **Federated Cross-Joins**: `query_unified_sources` (in-memory DuckDB/SQLite join across an SQL database table and an Excel sheet).
* **Master Reconciliation**: `reconcile_db_vs_excel`, `compare_master_datasets`, `generate_master_migration_plan`, `sync_master_to_db`, `py_template_pipeline`, `db_to_excel_template`.

### 10. Architecture Knowledge Graph MCP (`mcp-win-stdio-arch`) — 5 Tools
* **Blueprint Generation**: `get_full_stack_blueprint` (generates full-stack vertical architecture flowcharts).
* **Tracing & Blast-Radius**: `trace_execution_path` (traces entry points through service layers down to database entities), `analyze_blast_radius` (dependency impact analysis for proposed refactors).
* **Diagramming**: `generate_erd_diagram`, `scan_workspace_architecture`.
