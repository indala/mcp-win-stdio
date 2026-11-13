"""
Unit tests for Phase 3 Granular Tool Scoping & Blast Radius Containment.
Tests:
- ToolScopeFilter parsing, validation, fail-fast typo suggestions (difflib)
- Precedence hierarchy: disallow overrides allow
- Meta-gateway tool exemption (gateway tools always permitted for dynamic routing)
- Dynamic catalog filtering in get_server_catalog()
- Dynamic tool search filtering in search_tools()
- Runtime execution rejection in call_tool() and call_server()
- Snippet generation with scoping flags in generate_snippet()
"""

import pytest

import mcp_win_stdio.server.catalog as cat
import mcp_win_stdio.server.server as srv
from mcp_win_stdio.core.clients import generate_snippet
from mcp_win_stdio.core.permissions import CURRENT_SCOPE_FILTER, ToolScopeFilter


class TestToolScopeFilter:
    """Test ToolScopeFilter initialization, validation, and scoping checks."""

    def test_default_permits_all(self):
        f = ToolScopeFilter()
        assert f.is_server_allowed("excel") is True
        assert f.is_server_allowed("db") is True
        assert f.is_tool_allowed("excel", "preview_sheet") is True
        assert f.is_tool_allowed("db", "read_query") is True
        assert f.is_tool_allowed("gateway", "search_tools") is True

    def test_allow_servers_whitelist(self):
        f = ToolScopeFilter(allow_servers={"excel", "rag"})
        assert f.is_server_allowed("excel") is True
        assert f.is_server_allowed("rag") is True
        assert f.is_server_allowed("db") is False
        assert f.is_server_allowed("ssh") is False
        assert f.is_tool_allowed("excel", "preview_sheet") is True
        assert f.is_tool_allowed("db", "read_query") is False
        # Meta-gateway tools always allowed
        assert f.is_server_allowed("gateway") is True
        assert f.is_tool_allowed("gateway", "search_tools") is True

    def test_disallow_servers_blacklist(self):
        f = ToolScopeFilter(disallow_servers={"ssh", "db"})
        assert f.is_server_allowed("excel") is True
        assert f.is_server_allowed("ssh") is False
        assert f.is_server_allowed("db") is False
        assert f.is_tool_allowed("ssh", "ssh_exec") is False

    def test_disallow_overrides_allow(self):
        # When a server is in both allow and disallow, disallow wins
        f = ToolScopeFilter(allow_servers={"excel", "db"}, disallow_servers={"db"})
        assert f.is_server_allowed("excel") is True
        assert f.is_server_allowed("db") is False

    def test_allow_tools_whitelist(self):
        f = ToolScopeFilter(allow_tools={"preview_sheet", "get_workbook_info"})
        assert f.is_tool_allowed("excel", "preview_sheet") is True
        assert f.is_tool_allowed("excel", "get_workbook_info") is True
        assert f.is_tool_allowed("excel", "update_cells") is False
        assert f.is_tool_allowed("gateway", "call_tool") is True

    def test_disallow_tools_blacklist(self):
        f = ToolScopeFilter(disallow_tools={"excel_to_db_upsert", "git_reset"})
        assert f.is_tool_allowed("excel_db", "query_unified_sources") is True
        assert f.is_tool_allowed("excel_db", "excel_to_db_upsert") is False
        assert f.is_tool_allowed("git", "git_reset") is False

    def test_check_scope_reasons(self):
        f = ToolScopeFilter(allow_servers={"excel"}, disallow_tools={"update_cells"})
        ok, err = f.check_scope("excel", "preview_sheet")
        assert ok is True
        assert err is None

        ok, err = f.check_scope("db", "read_query")
        assert ok is False
        assert "not in active allowed servers scope" in err

        ok, err = f.check_scope("excel", "update_cells")
        assert ok is False
        assert "explicitly blacklisted by active scope" in err


class TestToolScopeFilterValidation:
    """Test CLI parsing and typo detection."""

    def test_valid_cli_string_parsing(self):
        f = ToolScopeFilter.from_cli_strings(
            allow_servers_str="excel,rag",
            disallow_tools_str="excel_to_db_upsert,git_reset",
            validate=True,
        )
        assert f.allow_servers == {"excel", "rag"}
        assert f.disallow_tools == {"excel_to_db_upsert", "git_reset"}

    def test_invalid_server_typo_suggestion(self):
        with pytest.raises(ValueError) as exc:
            ToolScopeFilter.from_cli_strings(allow_servers_str="excil", validate=True)
        assert "Did you mean 'excel'?" in str(exc.value)

    def test_invalid_tool_typo_suggestion(self):
        with pytest.raises(ValueError) as exc:
            ToolScopeFilter.from_cli_strings(allow_tools_str="read_quer", validate=True)
        assert "Did you mean 'read_query'?" in str(exc.value)


class TestCatalogAndExecutionFiltering:
    """Test dynamic filtering across catalog, search, and execution dispatch."""

    def test_catalog_scoped_to_excel(self):
        f = ToolScopeFilter.from_cli_strings(allow_servers_str="excel")
        token = CURRENT_SCOPE_FILTER.set(f)
        try:
            catalog = cat.get_server_catalog()
            assert list(catalog["servers"].keys()) == ["excel"]
            assert catalog["total_servers"] == 1
        finally:
            CURRENT_SCOPE_FILTER.reset(token)

    def test_search_tools_filtering(self):
        f = ToolScopeFilter.from_cli_strings(allow_servers_str="excel")
        token = CURRENT_SCOPE_FILTER.set(f)
        try:
            # Query for database tool returns empty because db server is scoped out
            db_res = cat.search_tools(query="read_query")
            assert len(db_res) == 0

            # Query for excel tool returns results
            xl_res = cat.search_tools(query="preview_sheet")
            assert len(xl_res) > 0
            assert xl_res[0]["server"] == "excel"
        finally:
            CURRENT_SCOPE_FILTER.reset(token)

    def test_execution_call_tool_rejected(self):
        f = ToolScopeFilter.from_cli_strings(allow_servers_str="excel", disallow_tools_str="preview_sheet")
        token = CURRENT_SCOPE_FILTER.set(f)
        try:
            # Server out of scope
            r1 = srv.call_tool(name="read_query", server="db")
            assert r1.get("isError") is True
            assert "Scope Denied" in r1.get("error")

            # Tool blacklisted on allowed server
            r2 = srv.call_tool(name="preview_sheet", server="excel")
            assert r2.get("isError") is True
            assert "Scope Denied" in r2.get("error")
        finally:
            CURRENT_SCOPE_FILTER.reset(token)

    def test_execution_call_server_rejected(self):
        f = ToolScopeFilter.from_cli_strings(allow_servers_str="excel")
        token = CURRENT_SCOPE_FILTER.set(f)
        try:
            r = srv.call_server(server="db")
            assert r.get("isError") is True
            assert "Scope Denied" in r.get("error")
        finally:
            CURRENT_SCOPE_FILTER.reset(token)


class TestClientSnippetScoping:
    """Test that generated JSON config snippets embed scope arguments."""

    def test_generate_snippet_with_scope(self):
        snippet = generate_snippet(
            server_name="mws",
            client_id="cursor",
            allow_servers="excel,rag",
            disallow_tools="excel_to_db_upsert",
        )
        assert '"--allow-servers"' in snippet
        assert '"excel,rag"' in snippet
        assert '"--disallow-tools"' in snippet
        assert '"excel_to_db_upsert"' in snippet


class TestAdvancedAuditEdgeCases:
    """Tests covering ChatGPT audit requirements: disambiguation, task isolation, and defaults."""

    def test_server_qualified_tool_disambiguation(self):
        # 'export_to_pdf' exists on both 'excel' and 'word'
        # Bare name 'export_to_pdf' is strictly rejected with ambiguous collision error
        with pytest.raises(ValueError) as exc:
            ToolScopeFilter.from_cli_strings(allow_tools_str="export_to_pdf")
        assert "Ambiguous tool name 'export_to_pdf'" in str(exc.value)
        assert "excel.export_to_pdf" in str(exc.value)

        # Disallow bare name collision is also rejected
        with pytest.raises(ValueError) as exc2:
            ToolScopeFilter.from_cli_strings(disallow_tools_str="export_to_pdf")
        assert "Ambiguous tool name 'export_to_pdf'" in str(exc2.value)

        # Server-qualified allow explicitly permits targeted server only
        f = ToolScopeFilter.from_cli_strings(allow_tools_str="excel.export_to_pdf")
        assert f.is_tool_allowed("excel", "export_to_pdf") is True
        assert f.is_tool_allowed("word", "export_to_pdf") is False

        # Server-qualified blacklist explicitly disallows targeted server only
        f_dis = ToolScopeFilter.from_cli_strings(disallow_tools_str="word.export_to_pdf")
        assert f_dis.is_tool_allowed("excel", "export_to_pdf") is True
        assert f_dis.is_tool_allowed("word", "export_to_pdf") is False

    def test_detached_child_task_lifecycle_and_scope_revocation(self):
        """
        Tests the security behavior of detached background tasks outliving a request.
        When request_scope.revoke() is called in the middleware finally block:
        1. Any detached task that attempts to invoke tools AFTER request completion fails closed (Scope Expired).
        2. Prohibits detached background execution beyond the authenticated request lifecycle.
        """
        import asyncio

        async def run_scenario():
            request_scope = ToolScopeFilter(allow_servers={"excel"}).clone()
            token = CURRENT_SCOPE_FILTER.set(request_scope)

            detached_result_before_finish = None
            detached_result_after_finish = None

            async def detached_background_worker():
                nonlocal detached_result_before_finish, detached_result_after_finish
                # Task executes while parent request is still active
                active_scope = CURRENT_SCOPE_FILTER.get()
                detached_result_before_finish = active_scope.check_scope("excel", "preview_sheet")

                # Wait for parent request to complete and revoke scope
                await asyncio.sleep(0.05)
                # Task attempts to execute after parent request completed
                detached_result_after_finish = active_scope.check_scope("excel", "preview_sheet")

            # Spawn detached task
            bg_task = asyncio.create_task(detached_background_worker())

            # Yield control briefly so worker runs while request is active
            await asyncio.sleep(0.01)

            # Parent request completes: middleware revokes request_scope and resets ContextVar
            request_scope.revoke()
            CURRENT_SCOPE_FILTER.reset(token)
            assert CURRENT_SCOPE_FILTER.get() is None

            # Wait for background task to attempt tool execution after request completion
            await bg_task

            # Before request finish: execution was permitted
            assert detached_result_before_finish[0] is True

            # After request finish: execution fails closed with Scope Expired
            assert detached_result_after_finish[0] is False
            assert "Scope Expired" in detached_result_after_finish[1]

        asyncio.run(run_scenario())

