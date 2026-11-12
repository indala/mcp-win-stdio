"""
Permission enforcement module for mws gateway and remote tunnels.
Enforces strict fail-closed read_only vs read_write boundaries across all MCP servers and tools.
"""

from contextvars import ContextVar
from typing import Dict, Optional, Set, Tuple

# Request-scoped ContextVar for active auth_mode (e.g. 'bearer', 'none', 'oauth')
CURRENT_AUTH_MODE: ContextVar[str] = ContextVar("current_auth_mode", default="bearer")

# Request-scoped ContextVar for allowing sensitive reads in unauthenticated mode
CURRENT_ALLOW_SENSITIVE_READS: ContextVar[bool] = ContextVar("current_allow_sensitive_reads", default=False)

# Strict server-qualified allowlist of audited safe read-only tools (129 tools).
# Any tool NOT explicitly in this set is treated as mutating and BLOCKED in read_only mode (fail-closed).
SAFE_READ_TOOLS: Set[Tuple[str, str]] = {
    # arch (5 tools)
    ("arch", "blueprint_audit"),
    ("arch", "blueprint_erd"),
    ("arch", "blueprint_feature"),
    ("arch", "blueprint_impact"),
    ("arch", "blueprint_trace"),

    # db (23 tools)
    ("db", "analyze_table_indexes"),
    ("db", "audit_database_health"),
    ("db", "compact_schema_overview"),
    ("db", "compare_schemas"),
    ("db", "describe_table"),
    ("db", "diff_data"),
    ("db", "explain_query"),
    ("db", "generate_erd"),
    ("db", "get_audit_log"),
    ("db", "get_database_stats"),
    ("db", "get_locks"),
    ("db", "get_table_ddl"),
    ("db", "get_table_sample"),
    ("db", "list_active_queries"),
    ("db", "list_connections"),
    ("db", "list_databases"),
    ("db", "list_schemas"),
    ("db", "list_slow_queries"),
    ("db", "read_query"),
    ("db", "schema_overview"),
    ("db", "search_schema"),
    ("db", "test_connection"),

    # excel (16 tools)
    ("excel", "analyze_reconciliation_keys"),
    ("excel", "audit_formulas"),
    ("excel", "compare_column_values"),
    ("excel", "diff_workbooks"),
    ("excel", "get_active_excel_window"),
    ("excel", "get_cell_formatting"),
    ("excel", "get_column_values"),
    ("excel", "get_workbook_info"),
    ("excel", "list_tables"),
    ("excel", "preview_sheet"),
    ("excel", "profile_sheet"),
    ("excel", "query_excel_sql"),
    ("excel", "query_rows"),
    ("excel", "read_range"),
    ("excel", "search_text"),
    ("excel", "summarize_column"),

    # excel_db / excel-db (3 tools)
    ("excel_db", "compare_master_datasets"),
    ("excel_db", "query_unified_sources"),
    ("excel_db", "reconcile_db_vs_excel"),

    # explorer (13 tools)
    ("explorer", "find_duplicate_files"),
    ("explorer", "find_files"),
    ("explorer", "find_symbol"),
    ("explorer", "fuzzy_find"),
    ("explorer", "get_code_outline"),
    ("explorer", "get_code_stats"),
    ("explorer", "get_directory_tree"),
    ("explorer", "get_file_info"),
    ("explorer", "grep_search"),
    ("explorer", "list_dir"),
    ("explorer", "read_file"),
    ("explorer", "read_head_tail"),
    ("explorer", "workspace_summary"),

    # git (19 tools)
    ("git", "gh_auth_status"),
    ("git", "gh_issue_list"),
    ("git", "gh_issue_view"),
    ("git", "gh_pr_checks"),
    ("git", "gh_pr_diff"),
    ("git", "gh_pr_list"),
    ("git", "gh_pr_review_comments"),
    ("git", "gh_pr_view"),
    ("git", "gh_release_list"),
    ("git", "gh_run_status"),
    ("git", "gh_search"),
    ("git", "git_blame"),
    ("git", "git_diff"),
    ("git", "git_grep"),
    ("git", "git_log"),
    ("git", "git_status"),
    ("git", "list_repos"),
    ("git", "repo_overview"),

    # rag (6 tools)
    ("rag", "find_related_chunks"),
    ("rag", "get_chunk_context"),
    ("rag", "get_knowledge_tree"),
    ("rag", "list_rag_collections"),
    ("rag", "query_knowledge_base"),
    ("rag", "rag_status"),

    # ssh (16 tools)
    ("ssh", "list_active_connections"),
    ("ssh", "list_hosts"),
    ("ssh", "sftp_list_dir"),
    ("ssh", "sftp_read_file"),
    ("ssh", "sftp_stat"),
    ("ssh", "ssh_check_job"),
    ("ssh", "ssh_list_packages"),
    ("ssh", "ssh_list_processes"),
    ("ssh", "ssh_list_pty_sessions"),
    ("ssh", "ssh_list_services"),
    ("ssh", "ssh_pty_read"),
    ("ssh", "ssh_system_overview"),
    ("ssh", "ssh_tail_logs"),
    ("ssh", "ssh_tunnel_list"),
    ("ssh", "test_host"),

    # tsc (7 tools)
    ("tsc", "get_error_category_breakdown"),
    ("tsc", "get_error_summary"),
    ("tsc", "get_file_errors"),
    ("tsc", "get_tsc_errors"),
    ("tsc", "list_projects"),
    ("tsc", "list_watched_projects"),
    ("tsc", "suggest_error_fixes"),

    # word (11 tools)
    ("word", "get_document_images"),
    ("word", "get_document_layout"),
    ("word", "get_document_metadata"),
    ("word", "get_document_outline"),
    ("word", "get_document_tables"),
    ("word", "get_document_typography"),
    ("word", "get_headers_and_footers"),
    ("word", "get_paragraph_spacing_and_indentation"),
    ("word", "inspect_revisions_and_comments"),
    ("word", "read_word_document"),
    ("word", "search_word_document"),

    # gateway (13 safe tools)
    ("gateway", "call_server"),
    ("gateway", "describe_tool"),
    ("gateway", "get_active_sessions"),
    ("gateway", "get_server_prompt"),
    ("gateway", "list_server_prompts"),
    ("gateway", "list_server_resource_templates"),
    ("gateway", "list_server_resources"),
    ("gateway", "list_servers"),
    ("gateway", "list_workflows"),
    ("gateway", "manage_context"),
    ("gateway", "read_artifact"),
    ("gateway", "read_server_resource"),
    ("gateway", "search_tools"),
}

# Explicit catalog of mutating tools (122 tools).
# Together with SAFE_READ_TOOLS (129 tools), accounts for all 251 runtime tools.
MUTATING_TOOLS: Set[Tuple[str, str]] = {
    # db (14 tools)
    ("db", "add_connection"),
    ("db", "clone_database"),
    ("db", "create_database"),
    ("db", "drop_database"),
    ("db", "dump_database"),
    ("db", "edit_connection"),
    ("db", "execute_query"),
    ("db", "export_table"),
    ("db", "import_csv"),
    ("db", "remove_connection"),
    ("db", "restore_database"),
    ("db", "terminate_connections"),
    ("db", "undo_query"),
    ("db", "use_database"),

    # excel (28 tools)
    ("excel", "add_sheet"),
    ("excel", "append_rows"),
    ("excel", "apply_conditional_formatting"),
    ("excel", "clean_and_deduplicate_sheet"),
    ("excel", "create_chart"),
    ("excel", "create_table"),
    ("excel", "create_workbook"),
    ("excel", "delete_column"),
    ("excel", "delete_rows"),
    ("excel", "delete_sheet"),
    ("excel", "export_to_csv"),
    ("excel", "export_to_json"),
    ("excel", "export_to_pdf"),
    ("excel", "export_transformed_workbook"),
    ("excel", "format_cells"),
    ("excel", "insert_column"),
    ("excel", "insert_rows"),
    ("excel", "merge_cells"),
    ("excel", "recalculate_and_save"),
    ("excel", "reconcile_and_merge"),
    ("excel", "refresh_data_and_pivots"),
    ("excel", "rename_sheet"),
    ("excel", "run_vba_macro"),
    ("excel", "search_and_replace_cells"),
    ("excel", "set_sheet_layout_and_freeze"),
    ("excel", "transform_sheet_data"),
    ("excel", "update_cells"),
    ("excel", "write_range"),

    # excel_db (6 tools)
    ("excel_db", "db_to_excel_stream"),
    ("excel_db", "db_to_excel_template"),
    ("excel_db", "excel_to_db_upsert"),
    ("excel_db", "generate_master_migration_plan"),
    ("excel_db", "py_template_pipeline"),
    ("excel_db", "sync_master_to_db"),

    # explorer (3 tools)
    ("explorer", "export_tree_to_file"),
    ("explorer", "replace_in_file"),
    ("explorer", "write_file"),

    # gateway (5 tools)
    ("gateway", "call_tool"),
    ("gateway", "delete_workflow"),
    ("gateway", "run_workflow"),
    ("gateway", "save_workflow"),
    ("gateway", "stop_server"),

    # git (23 tools)
    ("git", "add_repo"),
    ("git", "gh_api"),
    ("git", "gh_gist_create"),
    ("git", "gh_issue_comment"),
    ("git", "gh_issue_create"),
    ("git", "gh_pr_action"),
    ("git", "gh_pr_checkout"),
    ("git", "gh_release_create"),
    ("git", "gh_switch_account"),
    ("git", "git_branch"),
    ("git", "git_cherry_pick"),
    ("git", "git_clean_untracked"),
    ("git", "git_commit"),
    ("git", "git_config"),
    ("git", "git_conflict_resolve"),
    ("git", "git_init"),
    ("git", "git_remote"),
    ("git", "git_reset"),
    ("git", "git_restore"),
    ("git", "git_stash"),
    ("git", "git_sync"),
    ("git", "git_tag"),
    ("git", "git_worktree"),
    ("git", "issue_start_work"),
    ("git", "pr_quickstart"),
    ("git", "remove_repo"),
    ("git", "rename_alias"),
    ("git", "use_repo"),

    # rag (5 tools)
    ("rag", "crawl_and_index_url"),
    ("rag", "delete_rag_collection"),
    ("rag", "index_local_codebase"),
    ("rag", "index_remote_repo"),
    ("rag", "prune_rag_cache"),

    # ssh (19 tools)
    ("ssh", "add_host"),
    ("ssh", "disconnect_host"),
    ("ssh", "remove_host"),
    ("ssh", "sftp_download"),
    ("ssh", "sftp_remove"),
    ("ssh", "sftp_upload"),
    ("ssh", "sftp_write_file"),
    ("ssh", "ssh_exec"),
    ("ssh", "ssh_exec_background"),
    ("ssh", "ssh_exec_script"),
    ("ssh", "ssh_exec_sudo"),
    ("ssh", "ssh_kill_job"),
    ("ssh", "ssh_pty_close"),
    ("ssh", "ssh_pty_send"),
    ("ssh", "ssh_pty_start"),
    ("ssh", "ssh_service_action"),
    ("ssh", "ssh_tunnel_close"),
    ("ssh", "ssh_tunnel_open"),
    ("ssh", "use_host"),

    # tsc (5 tools)
    ("tsc", "add_project"),
    ("tsc", "remove_project"),
    ("tsc", "restart_tsc_watcher"),
    ("tsc", "use_project"),
    ("tsc", "watch_project"),

    # word (9 tools)
    ("word", "add_heading"),
    ("word", "add_paragraph"),
    ("word", "create_document"),
    ("word", "edit_paragraph"),
    ("word", "export_to_pdf"),
    ("word", "fill_template"),
    ("word", "insert_image"),
    ("word", "insert_table"),
    ("word", "replace_text"),
}

ALL_KNOWN_TOOLS: Set[Tuple[str, str]] = SAFE_READ_TOOLS | MUTATING_TOOLS

# Mapping from tool_name to set of server names hosting that tool
TOOL_TO_SERVERS_MAP: Dict[str, Set[str]] = {}
for _srv, _tool in ALL_KNOWN_TOOLS:
    TOOL_TO_SERVERS_MAP.setdefault(_tool, set()).add(_srv)

# Tools that access sensitive local filesystem contents, production databases, or remote infrastructure.
# On unauthenticated public tunnels (--auth none), these are blocked unless allow_sensitive_reads=True.
# Only safe discovery, structure, schema, outline, and compiler diagnostic tools are exposed by default.
UNAUTHENTICATED_RESTRICTED_TOOLS: Set[Tuple[str, str]] = {
    # Direct raw filesystem reading and content-based pattern exfiltration
    ("explorer", "read_file"),
    ("explorer", "read_head_tail"),
    ("explorer", "grep_search"),
    # Direct database query execution and data sampling
    ("db", "read_query"),
    ("db", "get_table_sample"),
    ("db", "diff_data"),
    # Spreadsheet content and row-level data reading (metadata like get_workbook_info / list_tables remains safe)
    ("excel", "preview_sheet"),
    ("excel", "read_range"),
    ("excel", "query_rows"),
    ("excel", "get_column_values"),
    ("excel", "compare_column_values"),
    ("excel", "summarize_column"),
    ("excel", "search_text"),
    ("excel", "query_excel_sql"),
    ("excel", "diff_workbooks"),
    # Cross-source database and spreadsheet queries
    ("excel_db", "query_unified_sources"),
    ("excel_db", "compare_master_datasets"),
    ("excel_db", "reconcile_db_vs_excel"),
    # Document content reading (typography and metadata remain safe)
    ("word", "read_word_document"),
    ("word", "search_word_document"),
    ("word", "get_document_tables"),
    ("word", "get_document_images"),
    ("word", "inspect_revisions_and_comments"),
    # Repository commit/content exfiltration
    ("git", "git_grep"),
    ("git", "git_diff"),
    ("git", "git_blame"),
    ("git", "git_log"),
    ("git", "gh_pr_diff"),
    # Knowledge base raw content retrieval and similarity exfiltration
    ("rag", "query_knowledge_base"),
    ("rag", "find_related_chunks"),
    ("rag", "get_chunk_context"),
    # All SSH tools inspect remote infrastructure
    ("ssh", "ssh_system_overview"),
    ("ssh", "ssh_list_packages"),
    ("ssh", "ssh_list_services"),
    ("ssh", "ssh_tail_logs"),
    ("ssh", "ssh_list_processes"),
    ("ssh", "sftp_list_dir"),
    ("ssh", "sftp_read_file"),
    ("ssh", "sftp_stat"),
    ("ssh", "ssh_check_job"),
    ("ssh", "ssh_list_pty_sessions"),
    ("ssh", "ssh_pty_read"),
    ("ssh", "ssh_tunnel_list"),
    ("ssh", "list_hosts"),
    ("ssh", "list_active_connections"),
    ("ssh", "test_host"),
}


def normalize_server_name(server: str) -> str:
    """Normalize server name to lowercase without hyphens."""
    return (server or "").lower().strip().replace("-", "_")


def is_tool_safe(server: str, tool_name: str) -> bool:
    """Return True if (server, tool_name) is explicitly in SAFE_READ_TOOLS allowlist."""
    srv = normalize_server_name(server)
    tool = (tool_name or "").lower().strip()
    return (srv, tool) in SAFE_READ_TOOLS


def is_tool_mutating(tool_name: str, server: Optional[str] = None) -> bool:
    """
    Check if a tool is mutating.
    Requires server name for strict server-qualified evaluation.
    If server is omitted, fails closed: only returns False if the tool is known and safe on ALL servers where it exists.
    """
    tool = (tool_name or "").lower().strip()
    if server:
        return not is_tool_safe(server, tool)

    # Server omitted: lookup all servers where tool exists
    servers = TOOL_TO_SERVERS_MAP.get(tool)
    if not servers:
        # Unknown or unclassified tool: fail closed
        return True

    # Require tool to be safe on ALL servers where it exists
    return not all((srv, tool) in SAFE_READ_TOOLS for srv in servers)


def check_tool_permission(
    server: str,
    tool_name: str,
    mode: str = "read_only",
    auth_mode: Optional[str] = None,
    allow_sensitive_reads: Optional[bool] = None,
) -> Tuple[bool, Optional[str]]:
    """
    Validate whether a tool execution is permitted under the given mode and auth_mode.
    Strictly fail-closed:
    - In 'read_only' mode, only tools in SAFE_READ_TOOLS are allowed.
    - In 'auth_mode == none', sensitive tools (explorer file reads, database queries, ssh inspection)
      are blocked unless allow_sensitive_reads is True.
    """
    norm_mode = (mode or "read_only").lower().strip()
    if norm_mode == "read_write":
        return True, None

    srv = normalize_server_name(server)
    tool = (tool_name or "").lower().strip()

    if (srv, tool) not in SAFE_READ_TOOLS:
        return (
            False,
            f"Permission Denied: Tool '{tool}' on server '{server}' is not approved for 'read_only' mode.",
        )

    # Confidentiality check for unauthenticated tunnels
    eff_auth = (auth_mode or CURRENT_AUTH_MODE.get() or "bearer").lower().strip()
    eff_allow_sens = (
        allow_sensitive_reads
        if allow_sensitive_reads is not None
        else CURRENT_ALLOW_SENSITIVE_READS.get()
    )

    if eff_auth == "none" and not eff_allow_sens:
        if (srv, tool) in UNAUTHENTICATED_RESTRICTED_TOOLS or srv == "ssh":
            return (
                False,
                f"Access Denied: Tool '{tool}' on server '{server}' accesses sensitive local or infrastructure "
                f"data and is restricted on unauthenticated public tunnels (--auth none). "
                f"Use '--auth bearer' for protected access, or start the tunnel with '--allow-sensitive-reads'.",
            )

    return True, None
