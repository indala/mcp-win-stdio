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
        results = list(executor.map(worker, range(10)))

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


def test_lease_protected_session_lifecycle():
    """Verify active sessions under lease are never evicted, and capacity limits are enforced safely."""
    import time

    import pytest

    reg = ContextManager(max_sessions=3, max_idle_seconds=3600.0, active_lease_seconds=10.0)

    # Fill capacity with 3 active sessions
    reg.set("workspace", "/path/1", session_id="s1")
    reg.set("workspace", "/path/2", session_id="s2")
    reg.set("workspace", "/path/3", session_id="s3")

    sessions_meta = reg.list_sessions()
    assert len(sessions_meta) == 3
    for sm in sessions_meta:
        assert sm["is_active"] is True
        assert "idle_seconds" in sm
        assert "created_seconds_ago" in sm

    # Attempting to allocate when all 3 are active under lease must raise RuntimeError
    with pytest.raises(RuntimeError, match="Maximum active sessions limit"):
        reg.get_session("s4")

    # Manually age session 's1' beyond the 10.0s active lease
    reg._sessions["s1"].last_accessed_at = time.time() - 15.0

    # Listing sessions now shows s1 as not active
    meta_map = {m["session_id"]: m for m in reg.list_sessions()}
    assert meta_map["s1"]["is_active"] is False
    assert meta_map["s2"]["is_active"] is True

    # Now allocating s4 should safely evict inactive session 's1'
    s4 = reg.get_session("s4")
    assert s4.session_id == "s4"
    assert "s1" not in reg._sessions
    assert "s2" in reg._sessions
    assert "s3" in reg._sessions
    assert "s4" in reg._sessions


def test_full_capacity_regression_existing_sessions_accessible():
    """Verify existing sessions remain fully operational when registry is at capacity."""
    import pytest

    reg = ContextManager(max_sessions=3, max_idle_seconds=3600.0, active_lease_seconds=600.0)
    reg.set("workspace", "/project/alpha", session_id="alpha")
    reg.set("workspace", "/project/beta", session_id="beta")
    reg.set("workspace", "/project/gamma", session_id="gamma")

    # Creating a new session must be rejected
    with pytest.raises(RuntimeError, match="Maximum active sessions limit"):
        reg.get_session("delta")

    # Accessing and modifying existing sessions must succeed without raising RuntimeError
    assert reg.get("workspace", session_id="alpha") == "/project/alpha"
    reg.set("workspace", "/project/alpha_v2", session_id="alpha")
    assert reg.get("workspace", session_id="alpha") == "/project/alpha_v2"

    snap = reg.snapshot(session_id="beta")
    assert snap["workspace"]["active"] == "/project/beta"
    assert len(reg._sessions) == 3


def test_concurrent_creation_at_capacity():
    """Verify concurrent creation attempts at capacity maintain capacity invariant without evicting active sessions."""
    import concurrent.futures

    reg = ContextManager(max_sessions=3, max_idle_seconds=3600.0, active_lease_seconds=600.0)
    reg.set("workspace", "/initial/1", session_id="init_1")
    reg.set("workspace", "/initial/2", session_id="init_2")
    reg.set("workspace", "/initial/3", session_id="init_3")

    errors = []

    def try_create(idx):
        try:
            reg.get_session(f"new_{idx}")
            return "created"
        except RuntimeError as e:
            errors.append(str(e))
            return "rejected"

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        results = list(executor.map(try_create, range(10)))

    assert all(r == "rejected" for r in results)
    assert len(errors) == 10
    assert all("Maximum active sessions limit" in err for err in errors)

    # Invariant holds: exactly 3 initial sessions, none evicted
    assert len(reg._sessions) == 3
    assert set(reg._sessions.keys()) == {"init_1", "init_2", "init_3"}


def test_expired_session_pruned_on_retrieval():
    """Verify that retrieving a session past max_idle_seconds prunes it and returns a clean session."""
    import time

    reg = ContextManager(max_sessions=3, max_idle_seconds=60.0, active_lease_seconds=30.0)

    # 1. Populate session with context
    reg.set("workspace", "/old/workspace", session_id="exp_sid")
    assert reg.get("workspace", session_id="exp_sid") == "/old/workspace"

    # 2. Advance time beyond max_idle_seconds
    reg._sessions["exp_sid"].last_accessed_at = time.time() - 120.0

    # 3. Retrieving exp_sid must prune the expired session and allocate a fresh one
    fresh = reg.get_session("exp_sid")
    assert fresh.session_id == "exp_sid"
    # Old context stack must be discarded
    assert fresh.get("workspace") is None
    assert reg.get("workspace", session_id="exp_sid") is None


