"""
Permission enforcement module for mws gateway and remote tunnels.
Enforces strict fail-closed read_only vs read_write boundaries across all MCP servers and tools.
"""

import difflib
from contextvars import ContextVar
from typing import Dict, List, Optional, Set, Tuple

# Request-scoped ContextVar for active auth_mode (e.g. 'bearer', 'none', 'oauth')
CURRENT_AUTH_MODE: ContextVar[str] = ContextVar("current_auth_mode", default="bearer")

# Request-scoped ContextVar for allowing sensitive reads in unauthenticated mode
CURRENT_ALLOW_SENSITIVE_READS: ContextVar[bool] = ContextVar("current_allow_sensitive_reads", default=False)

# Request-scoped ContextVar for active ToolScopeFilter (granular server/tool whitelisting)
CURRENT_SCOPE_FILTER: ContextVar[Optional["ToolScopeFilter"]] = ContextVar("current_scope_filter", default=None)

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
    srv = normalize_server_name(server)
    tool = (tool_name or "").lower().strip()

    # Confidentiality check for unauthenticated tunnels (enforced across all permission modes)
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

    norm_mode = (mode or "read_only").lower().strip()
    if norm_mode == "read_write":
        return True, None

    if (srv, tool) not in SAFE_READ_TOOLS:
        return (
            False,
            f"Permission Denied: Tool '{tool}' on server '{server}' is not approved for 'read_only' mode.",
        )

    return True, None


def check_capability_permission(
    server: str,
    capability_method: str,
    auth_mode: Optional[str] = None,
    allow_sensitive_reads: Optional[bool] = None,
) -> Tuple[bool, Optional[str]]:
    """
    Validate whether an MCP capability operation (resources/*, prompts/*) on a target server
    is permitted under the active scope filter and authentication ceiling.

    Enforces policy at the target-server boundary:
    1. Scope boundary: Verifies the target server is allowed under CURRENT_SCOPE_FILTER.
    2. Confidentiality boundary: On unauthenticated public tunnels (--auth none), reading resource
       payloads (resources/read) or rendering prompts (prompts/get) is restricted if the server
       exposes sensitive local/infrastructure data (derived from UNAUTHENTICATED_RESTRICTED_TOOLS
       or ssh), unless allow_sensitive_reads is explicitly granted.
    """
    srv = normalize_server_name(server)

    # 1. Target server scope filter check
    scope_filter = CURRENT_SCOPE_FILTER.get()
    if scope_filter and not scope_filter.is_server_allowed(srv):
        return (
            False,
            f"Scope Error: Access to server '{server}' is not permitted under the active scope filter.",
        )

    # 2. Confidentiality check for unauthenticated tunnels
    eff_auth = (auth_mode or CURRENT_AUTH_MODE.get() or "bearer").lower().strip()
    eff_allow_sens = (
        allow_sensitive_reads
        if allow_sensitive_reads is not None
        else CURRENT_ALLOW_SENSITIVE_READS.get()
    )

    if eff_auth == "none" and not eff_allow_sens:
        is_sensitive_server = srv == "ssh" or any(s == srv for s, _ in UNAUTHENTICATED_RESTRICTED_TOOLS)
        if is_sensitive_server and capability_method in ("resources/read", "prompts/get"):
            return (
                False,
                f"Access Denied: Capability '{capability_method}' on server '{server}' accesses sensitive "
                f"data and is restricted on unauthenticated public tunnels (--auth none). "
                f"Use '--auth bearer' for protected access, or start the tunnel with '--allow-sensitive-reads'.",
            )

    return True, None


class ToolScopeFilter:
    """
    Granular tool and server domain scoping engine.
    Controls tool visibility and execution via allow/disallow lists for servers and specific tools.

    Evaluation precedence (fail-closed, disallow overrides allow):
    1. Server Domain Scope:
       - If server is in disallow_servers -> BLOCKED
       - If allow_servers is specified and server not in allow_servers -> BLOCKED
    2. Tool Name Scope:
       - If tool is in disallow_tools -> BLOCKED
       - If allow_tools is specified and tool not in allow_tools -> BLOCKED
    3. Meta-gateway tools ('gateway' namespace) are ALWAYS permitted for discovery and routing,
       ensuring on-demand catalog searches and execution dispatch function properly for allowed tools.
    """

    KNOWN_SERVERS: Set[str] = {
        "arch",
        "db",
        "excel",
        "excel_db",
        "explorer",
        "git",
        "rag",
        "ssh",
        "tsc",
        "word",
    }

    def __init__(
        self,
        allow_servers: Optional[Set[str]] = None,
        disallow_servers: Optional[Set[str]] = None,
        allow_tools: Optional[Set[str]] = None,
        disallow_tools: Optional[Set[str]] = None,
    ) -> None:
        self.allow_servers: Optional[Set[str]] = (
            {normalize_server_name(s) for s in allow_servers} if allow_servers is not None else None
        )
        self.disallow_servers: Set[str] = (
            {normalize_server_name(s) for s in disallow_servers} if disallow_servers is not None else set()
        )
        self.allow_tools: Optional[Set[str]] = (
            {t.lower().strip() for t in allow_tools} if allow_tools is not None else None
        )
        self.disallow_tools: Set[str] = (
            {t.lower().strip() for t in disallow_tools} if disallow_tools is not None else set()
        )
        self._is_active: bool = True

    def revoke(self) -> None:
        """Explicitly revoke/expire this scope filter upon request termination."""
        self._is_active = False

    def clone(self) -> "ToolScopeFilter":
        """Create a new active instance sharing the same scoping rules."""
        cloned = ToolScopeFilter(
            allow_servers=self.allow_servers,
            disallow_servers=self.disallow_servers,
            allow_tools=self.allow_tools,
            disallow_tools=self.disallow_tools,
        )
        return cloned

    def is_unrestricted(self) -> bool:
        """Returns True if this filter enforces no restrictions (all servers & tools allowed)."""
        return (
            self._is_active
            and self.allow_servers is None
            and not self.disallow_servers
            and self.allow_tools is None
            and not self.disallow_tools
        )

    def is_server_allowed(self, server: str) -> bool:
        """Check if server domain is permitted under current scope."""
        if not self._is_active:
            return False
        srv = normalize_server_name(server)
        if srv == "gateway":
            return True
        if srv in self.disallow_servers:
            return False
        if self.allow_servers is not None and srv not in self.allow_servers:
            return False
        return True

    def is_tool_allowed(self, server: str, tool_name: str) -> bool:
        """Check if specific tool on target server is permitted under current scope."""
        if not self._is_active:
            return False
        srv = normalize_server_name(server)
        tool = (tool_name or "").lower().strip()
        qualified_tool = f"{srv}.{tool}"

        # Meta-gateway tools are always permitted so discovery and routing work
        if srv == "gateway":
            return True

        # 1. Check server domain scope
        if not self.is_server_allowed(srv):
            return False

        # 2. Check explicit tool blacklist (disallow overrides allow)
        # Matches either bare tool name ('export_to_pdf') or server-qualified ('excel.export_to_pdf')
        if tool in self.disallow_tools or qualified_tool in self.disallow_tools:
            return False

        # 3. Check explicit tool whitelist
        # If whitelist is configured, permits if either bare tool name or qualified name is present
        if self.allow_tools is not None and tool not in self.allow_tools and qualified_tool not in self.allow_tools:
            return False

        return True

    def check_scope(self, server: str, tool_name: str) -> Tuple[bool, Optional[str]]:
        """
        Validate whether (server, tool_name) is permitted by scope.
        Returns (is_permitted, denial_reason).
        """
        if not self._is_active:
            return (
                False,
                f"Scope Expired: The request authorization scope for tool '{tool_name}' on server '{server}' has terminated.",
            )

        srv = normalize_server_name(server)
        tool = (tool_name or "").lower().strip()
        qualified_tool = f"{srv}.{tool}"

        if srv == "gateway":
            return True, None

        if srv in self.disallow_servers:
            return (
                False,
                f"Scope Denied: Server '{server}' is explicitly blacklisted by active scope (--disallow-servers).",
            )

        if self.allow_servers is not None and srv not in self.allow_servers:
            return (
                False,
                f"Scope Denied: Server '{server}' is not in active allowed servers scope (--allow-servers {', '.join(sorted(self.allow_servers))}).",
            )

        if tool in self.disallow_tools or qualified_tool in self.disallow_tools:
            return (
                False,
                f"Scope Denied: Tool '{tool}' on server '{server}' is explicitly blacklisted by active scope (--disallow-tools).",
            )

        if self.allow_tools is not None and tool not in self.allow_tools and qualified_tool not in self.allow_tools:
            return (
                False,
                f"Scope Denied: Tool '{tool}' on server '{server}' is not in active allowed tools scope (--allow-tools).",
            )

        return True, None

    @classmethod
    def from_cli_strings(
        cls,
        allow_servers_str: Optional[str] = None,
        disallow_servers_str: Optional[str] = None,
        allow_tools_str: Optional[str] = None,
        disallow_tools_str: Optional[str] = None,
        validate: bool = True,
    ) -> "ToolScopeFilter":
        """
        Parse comma-separated CLI argument strings into a validated ToolScopeFilter instance.
        Fails fast if unknown servers or tool names are specified, providing typo suggestions.
        """

        def _split_clean(val: Optional[str]) -> Optional[Set[str]]:
            if val is None or not str(val).strip():
                return None
            items = {item.strip() for item in str(val).split(",") if item.strip()}
            return items if items else None

        allow_srv = _split_clean(allow_servers_str)
        disallow_srv = _split_clean(disallow_servers_str)
        allow_t = _split_clean(allow_tools_str)
        disallow_t = _split_clean(disallow_tools_str)

        if validate:
            cls.validate_scope_inputs(
                allow_servers=allow_srv,
                disallow_servers=disallow_srv,
                allow_tools=allow_t,
                disallow_tools=disallow_t,
            )

        return cls(
            allow_servers=allow_srv,
            disallow_servers=disallow_srv,
            allow_tools=allow_t,
            disallow_tools=disallow_t,
        )

    @classmethod
    def validate_scope_inputs(
        cls,
        allow_servers: Optional[Set[str]] = None,
        disallow_servers: Optional[Set[str]] = None,
        allow_tools: Optional[Set[str]] = None,
        disallow_tools: Optional[Set[str]] = None,
    ) -> None:
        """
        Validate server and tool names against registered catalog.
        Raises ValueError with difflib typo suggestions on invalid names.
        """
        valid_srvs = {s.replace("_", "-") for s in cls.KNOWN_SERVERS} | cls.KNOWN_SERVERS

        for srv_set, flag_name in ((allow_servers, "--allow-servers"), (disallow_servers, "--disallow-servers")):
            if not srv_set:
                continue
            for s in srv_set:
                norm_s = normalize_server_name(s)
                if norm_s not in cls.KNOWN_SERVERS:
                    matches = difflib.get_close_matches(s, list(valid_srvs), n=2, cutoff=0.6)
                    hint = f" Did you mean '{matches[0]}'?" if matches else ""
                    raise ValueError(f"Invalid server '{s}' specified in {flag_name}.{hint} Available servers: {', '.join(sorted(valid_srvs))}")

        # Validate tools (accepts both bare tool names and server-qualified 'server.tool')
        valid_tool_names = {t for _, t in ALL_KNOWN_TOOLS}
        valid_qualified_tools = {f"{srv}.{t}" for srv, t in ALL_KNOWN_TOOLS} | {
            f"{srv.replace('_', '-')}.{t}" for srv, t in ALL_KNOWN_TOOLS
        }
        all_acceptable_tools = valid_tool_names | valid_qualified_tools

        # Ambiguous multi-server collision map
        ambiguous_tools = {tool: srvs for tool, srvs in TOOL_TO_SERVERS_MAP.items() if len(srvs) > 1}

        for tool_set, flag_name in ((allow_tools, "--allow-tools"), (disallow_tools, "--disallow-tools")):
            if not tool_set:
                continue
            for t in tool_set:
                norm_t = t.lower().strip()
                if norm_t not in all_acceptable_tools:
                    matches = difflib.get_close_matches(norm_t, list(all_acceptable_tools), n=2, cutoff=0.6)
                    hint = f" Did you mean '{matches[0]}'?" if matches else ""
                    raise ValueError(f"Invalid tool '{t}' specified in {flag_name}.{hint}")
                # Reject bare names that collide across multiple servers
                if norm_t in ambiguous_tools and "." not in norm_t:
                    candidate_servers = sorted(ambiguous_tools[norm_t])
                    suggestions = [f"{srv}.{norm_t}" for srv in candidate_servers]
                    raise ValueError(
                        f"Ambiguous tool name '{t}' specified in {flag_name}. Tool '{t}' exists on multiple servers: "
                        f"{', '.join(candidate_servers)}. You must specify the server explicitly using dot notation "
                        f"(e.g. {suggestions[0]} or {suggestions[1]})."
                    )
