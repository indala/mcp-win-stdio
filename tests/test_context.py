from mcp_win_stdio.core.context import ContextManager


def test_context_stack_push_pop():
    ctx = ContextManager()
    assert ctx.get("db_connection") is None

    # Set initial
    ctx.set("db_connection", "dev_db")
    assert ctx.get("db_connection") == "dev_db"

    # Push override
    ctx.push("db_connection", "prod_db")
    assert ctx.get("db_connection") == "prod_db"

    # Pop restores previous
    popped = ctx.pop("db_connection")
    assert popped == "prod_db"
    assert ctx.get("db_connection") == "dev_db"

    # Pop again restores empty
    popped2 = ctx.pop("db_connection")
    assert popped2 == "dev_db"
    assert ctx.get("db_connection") is None


def test_independent_stacks():
    ctx = ContextManager()
    ctx.set("db_connection", "mysql_local")
    ctx.set("ssh_host", "hetzner_node")
    ctx.set("workspace", "/projects/app")

    assert ctx.get("db_connection") == "mysql_local"
    assert ctx.get("ssh_host") == "hetzner_node"
    assert ctx.get("workspace") == "/projects/app"

    # Overriding ssh_host should not touch db_connection
    ctx.push("ssh_host", "aws_prod")
    assert ctx.get("ssh_host") == "aws_prod"
    assert ctx.get("db_connection") == "mysql_local"


def test_argument_resolution():
    ctx = ContextManager()
    ctx.set("db_connection", "postgres_stage")
    ctx.set("ssh_host", "remote_box")

    # DB tool missing connection
    args, injected = ctx.resolve_arguments(
        server="db",
        tool_name="read_query",
        arguments={"query": "SELECT 1;"},
        expected_params=["query", "connection"],
    )
    assert args["connection"] == "postgres_stage"
    assert injected == {"connection": "postgres_stage"}

    # Explicit argument wins over context
    args2, injected2 = ctx.resolve_arguments(
        server="db",
        tool_name="read_query",
        arguments={"query": "SELECT 1;", "connection": "explicit_db"},
        expected_params=["query", "connection"],
    )
    assert args2["connection"] == "explicit_db"
    assert injected2 == {}


def test_snapshot():
    ctx = ContextManager()
    ctx.set("server", "db")
    ctx.push("db_connection", "db_1")
    ctx.push("db_connection", "db_2")

    snap = ctx.snapshot()
    assert snap["server"]["active"] == "db"
    assert snap["db_connection"]["active"] == "db_2"
    assert snap["db_connection"]["depth"] == 2


def test_multi_session_context_isolation():
    """Verify that multiple agent sessions retain isolated contexts without crosstalk."""
    ctx = ContextManager()

    # Session 1 (Antigravity): sets dev database
    ctx.set("db_connection", "ijitest_dev", session_id="antigravity_agent")
    ctx.set("workspace", "/dev/app", session_id="antigravity_agent")

    # Session 2 (Claude): sets production analytics database
    ctx.set("db_connection", "analytics_prod", session_id="claude_desktop")
    ctx.set("ssh_host", "remote_cluster", session_id="claude_desktop")

    # Verify Antigravity's context is untouched
    assert ctx.get("db_connection", session_id="antigravity_agent") == "ijitest_dev"
    assert ctx.get("workspace", session_id="antigravity_agent") == "/dev/app"
    assert ctx.get("ssh_host", session_id="antigravity_agent") is None

    # Verify Claude's context is untouched
    assert ctx.get("db_connection", session_id="claude_desktop") == "analytics_prod"
    assert ctx.get("ssh_host", session_id="claude_desktop") == "remote_cluster"
    assert ctx.get("workspace", session_id="claude_desktop") is None

    # Verify default session is unaffected
    assert ctx.get("db_connection") is None


def test_concurrent_session_access_and_pruning():
    """Verify thread-safe concurrent session access and LRU lifecycle pruning."""
    import concurrent.futures

    reg = ContextManager(max_sessions=10, max_idle_seconds=0.1)

    def worker(idx):
        sid = f"worker_{idx}"
        reg.set("db_connection", f"db_{idx}", session_id=sid)
        val = reg.get("db_connection", session_id=sid)
        return sid, val

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        results = list(executor.map(worker, range(15)))

    for sid, val in results:
        expected_db = f"db_{sid.split('_')[1]}"
        assert val == expected_db

    # Sleep slightly to trigger max_idle_seconds expiration
    import time
    time.sleep(0.15)

    # Access a new session to trigger prune
    reg.get_session("new_session")
    # Expired sessions should be pruned
    assert len(reg._sessions) <= 10


