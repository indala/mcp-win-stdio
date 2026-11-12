"""
Permission enforcement module for mws gateway and remote tunnels.
Enforces read_only vs read_write boundaries server-side across all MCP servers and tools.
"""

import re
from typing import Optional, Set, Tuple

# Explicit list of mutating / state-altering tools per server
MUTATING_TOOLS: Set[str] = {
    # db
    "execute_query",
    "undo_query",
    "remove_connection",
    "add_connection",
    "edit_connection",
    "create_database",
    "drop_database",
    "clone_database",
    "terminate_connections",
    "restore_database",
    "import_csv",
    # explorer
    "write_file",
    "replace_in_file",
    # ssh
    "ssh_exec",
    "ssh_exec_sudo",
    "ssh_exec_script",
    "ssh_exec_background",
    "ssh_kill_job",
    "ssh_pty_start",
    "ssh_pty_send",
    "ssh_service_action",
    "sftp_write_file",
    "sftp_upload",
    "sftp_remove",
    "add_host",
    "remove_host",
    "disconnect_host",
    "ssh_tunnel_open",
    "ssh_tunnel_close",
    # git
    "git_init",
    "git_commit",
    "git_branch",
    "git_stash",
    "git_sync",
    "git_restore",
    "git_reset",
    "git_tag",
    "git_conflict_resolve",
    "git_cherry_pick",
    "git_clean_untracked",
    "add_repo",
    "remove_repo",
    "rename_alias",
    "gh_issue_create",
    "gh_issue_comment",
    "gh_pr_action",
    "gh_gist_create",
    "gh_release_create",
    # excel
    "create_workbook",
    "append_rows",
    "add_sheet",
    "rename_sheet",
    "delete_sheet",
    "update_cells",
    "write_range",
    "format_cells",
    "apply_conditional_formatting",
    "set_sheet_layout_and_freeze",
    "create_chart",
    "clean_and_deduplicate_sheet",
    "transform_sheet_data",
    "reconcile_and_merge",
    "recalculate_and_save",
    "run_vba_macro",
    "search_and_replace_cells",
    "create_table",
    "insert_column",
    "delete_column",
    "insert_rows",
    "delete_rows",
    "merge_cells",
    # excel-db
    "excel_to_db_upsert",
    "sync_master_to_db",
    "py_template_pipeline",
    # word
    "edit_paragraph",
    "insert_table",
    "create_document",
    "add_paragraph",
    "add_heading",
    "fill_template",
    "replace_text",
    "insert_image",
    # tsc
    "add_project",
    "remove_project",
    "restart_tsc_watcher",
    # rag
    "crawl_and_index_url",
    "index_local_codebase",
    "index_remote_repo",
    "delete_rag_collection",
    "prune_rag_cache",
    # workflows
    "run_workflow",
}

# Prefix patterns matching mutating operations
MUTATING_PATTERNS = re.compile(
    r"^(create|update|delete|drop|insert|append|modify|edit|replace|remove|write|exec|execute|kill|sync|clone|restore|upload|commit|clean)_",
    re.IGNORECASE,
)


def is_tool_mutating(tool_name: str) -> bool:
    """Return True if tool performs write, update, delete, or external execution."""
    norm = tool_name.lower().strip()
    if norm in MUTATING_TOOLS:
        return True
    return bool(MUTATING_PATTERNS.match(norm))


def check_tool_permission(server: str, tool_name: str, mode: str = "read_only") -> Tuple[bool, Optional[str]]:
    """
    Validate whether a tool execution is permitted under the given mode.
    Returns (True, None) if permitted, or (False, error_message) if blocked.
    """
    norm_mode = mode.lower().strip()
    if norm_mode == "read_write":
        return True, None

    # In read_only mode, strictly block all mutating tools
    if is_tool_mutating(tool_name):
        return (
            False,
            f"Permission Denied: Tool '{tool_name}' on server '{server}' performs write/execution "
            f"operations and is strictly blocked in 'read_only' mode.",
        )

    return True, None
