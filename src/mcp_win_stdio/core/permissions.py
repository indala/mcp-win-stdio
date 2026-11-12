"""
Permission enforcement module for mws gateway and remote tunnels.
Enforces strict fail-closed read_only vs read_write boundaries across all MCP servers and tools.
"""

from typing import Optional, Set, Tuple

# Strict server-qualified allowlist of audited safe read-only tools.
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
    If server is omitted, fails closed: only returns False if the tool is safe on all servers.
    """
    tool = (tool_name or "").lower().strip()
    if server:
        return not is_tool_safe(server, tool)

    # Fail closed: require tool to be safe on all servers where it exists
    return not any(t == tool for (_, t) in SAFE_READ_TOOLS)


def check_tool_permission(server: str, tool_name: str, mode: str = "read_only") -> Tuple[bool, Optional[str]]:
    """
    Validate whether a tool execution is permitted under the given mode.
    Strictly fail-closed: in 'read_only' mode, only tools in SAFE_READ_TOOLS are allowed.
    """
    norm_mode = (mode or "read_only").lower().strip()
    if norm_mode == "read_write":
        return True, None

    srv = normalize_server_name(server)
    tool = (tool_name or "").lower().strip()

    if (srv, tool) in SAFE_READ_TOOLS:
        return True, None

    return (
        False,
        f"Permission Denied: Tool '{tool}' on server '{server}' is not approved for 'read_only' mode.",
    )
