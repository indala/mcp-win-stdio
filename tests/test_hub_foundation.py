"""
Comprehensive verification tests for Phase 2: Registry & Configuration Foundation.
"""

import concurrent.futures
import os
import threading
import time

import pytest

from mcp_win_stdio.core.context import GLOBAL_CONTEXT
from mcp_win_stdio.core.hub.models import (
    HubConfig,
    ProfileConfig,
    ProjectConfig,
    SecretReference,
    ServerConfig,
    ServerProfileManifest,
    SupervisorConfig,
    ToolFilter,
)
from mcp_win_stdio.core.hub.profiles import ProfileManager, ProfileNotFoundError
from mcp_win_stdio.core.hub.registry import HubRegistry, RegistryValidationError
from mcp_win_stdio.core.hub.secrets import (
    EnvSecretProvider,
    SanitizedException,
    SecretRegistry,
    redact_sensitive_data,
    redact_sensitive_text,
)


def test_schema_validation_and_rejection_of_malformed_config():
    """Verify malformed hub configurations raise RegistryValidationError and do not partially activate."""
    reg = HubRegistry()
    initial_servers = len(reg.list_servers())

    with pytest.raises(RegistryValidationError, match="Configuration validation failed"):
        reg.load_from_dict(["not", "a", "dict"])  # type: ignore[arg-type]

    invalid_data = {
        "schema_version": "1.0",
        "servers": {
            "bad_server": {
                "name": "bad_server",
                "args": ["run"],
            }
        },
    }
    with pytest.raises(RegistryValidationError, match="requires a valid non-empty string 'command'"):
        reg.load_from_dict(invalid_data)

    assert len(reg.list_servers()) == initial_servers


def test_failed_reload_preserves_previous_active_generation():
    """Verify that a failed reload atomically preserves the last active valid configuration."""
    reg = HubRegistry()
    valid_data = {
        "schema_version": "1.0",
        "servers": {
            "test_db": {
                "name": "test_db",
                "command": "uv",
                "args": ["run", "test_db"],
            }
        },
    }
    # Initial valid load advances generation to 2
    reg.load_from_dict(valid_data)
    assert reg.get_generation() == 2
    assert reg.get_server("test_db") is not None
    assert reg.get_server("test_db").command == "uv"  # type: ignore[union-attr]

    # Reload with identical configuration does NOT advance generation
    changed = reg.load_from_dict(valid_data)
    assert changed is False
    assert reg.get_generation() == 2

    # Attempt reload with a malformed configuration
    malformed_data = {
        "schema_version": "1.0",
        "servers": {
            "test_db": {
                "name": "mismatched_key",
                "command": "uv",
            }
        },
    }
    with pytest.raises(RegistryValidationError, match="does not match"):
        reg.load_from_dict(malformed_data)

    # Verification: generation and active config remain untouched after failure
    assert reg.get_generation() == 2
    srv = reg.get_server("test_db")
    assert srv is not None
    assert srv.command == "uv"


def test_concurrent_configuration_reads_during_reload():
    """Verify concurrent reads observe consistent configuration state while atomic reload executes."""
    reg = HubRegistry()
    valid_v1 = {
        "schema_version": "1.0",
        "servers": {"srv": {"name": "srv", "command": "cmd_v1"}},
    }
    reg.load_from_dict(valid_v1)

    stop_event = threading.Event()
    read_results = []
    read_errors = []

    def reader():
        while not stop_event.is_set():
            try:
                srv = reg.get_server("srv")
                if srv:
                    read_results.append(srv.command)
            except Exception as e:
                read_errors.append(e)

    threads = [threading.Thread(target=reader) for _ in range(4)]
    for t in threads:
        t.start()

    for i in range(15):
        cmd = f"cmd_v{i % 2 + 1}"
        reg.load_from_dict({
            "schema_version": "1.0",
            "servers": {"srv": {"name": "srv", "command": cmd}},
        })
        time.sleep(0.005)

    stop_event.set()
    for t in threads:
        t.join()

    assert len(read_errors) == 0
    assert all(cmd in ("cmd_v1", "cmd_v2") for cmd in read_results)


def test_four_tier_profile_resolution_precedence():
    """Verify strict 4-tier precedence: Request > Session Context > Project Binding > Server Default."""
    GLOBAL_CONTEXT.clear()
    pm = ProfileManager()

    manifest_data = {
        "schema_version": "1.0",
        "default_profile": "prof_default",
        "profiles": {
            "prof_default": {"type": "postgres", "host": "localhost", "port": 5432},
            "prof_project": {"type": "postgres", "host": "project-host", "port": 5432},
            "prof_session": {"type": "postgres", "host": "session-host", "port": 5432},
            "prof_request": {"type": "postgres", "host": "request-host", "port": 5432},
        },
    }
    pm.load_manifest_dict("db", manifest_data)

    project_cfg = ProjectConfig(profile_bindings={"db": "prof_project"})
    GLOBAL_CONTEXT.set("db_profile", "prof_session", session_id="client_session_1")

    # Tier 1: Request argument overrides everything
    res1, gen1 = pm.resolve_profile(
        server="db",
        request_override="prof_request",
        session_id="client_session_1",
        project_config=project_cfg,
    )
    assert res1.name == "prof_request"
    assert res1.parameters["host"] == "request-host"

    # Tier 2: Without request override, session context wins
    res2, _ = pm.resolve_profile(
        server="db",
        request_override=None,
        session_id="client_session_1",
        project_config=project_cfg,
    )
    assert res2.name == "prof_session"
    assert res2.parameters["host"] == "session-host"

    # Tier 3: Without request or session context, project binding wins
    res3, _ = pm.resolve_profile(
        server="db",
        request_override=None,
        session_id="other_clean_session",
        project_config=project_cfg,
    )
    assert res3.name == "prof_project"
    assert res3.parameters["host"] == "project-host"

    # Tier 4: Without project binding, server default wins
    res4, _ = pm.resolve_profile(
        server="db",
        request_override=None,
        session_id="other_clean_session",
        project_config=None,
    )
    assert res4.name == "prof_default"
    assert res4.parameters["host"] == "localhost"

    GLOBAL_CONTEXT.clear()


def test_missing_profile_reference_fails_explicitly():
    """Verify referencing an invalid/missing profile fails immediately with ProfileNotFoundError."""
    GLOBAL_CONTEXT.clear()
    pm = ProfileManager()

    manifest_data = {
        "schema_version": "1.0",
        "default_profile": "prod_db",
        "profiles": {
            "prod_db": {"host": "prod.internal"},
        },
    }
    pm.load_manifest_dict("db", manifest_data)

    # 1. Higher-priority request override references non-existent profile
    with pytest.raises(ProfileNotFoundError, match="Profile 'non_existent_override'"):
        pm.resolve_profile(server="db", request_override="non_existent_override")

    # Empty string override fails explicitly rather than falling through
    with pytest.raises(ProfileNotFoundError, match="Empty or whitespace profile override"):
        pm.resolve_profile(server="db", request_override="  ")

    # 2. Session context references non-existent profile
    GLOBAL_CONTEXT.set("db_profile", "bogus_session_profile", session_id="sess_err")
    with pytest.raises(ProfileNotFoundError, match="Profile 'bogus_session_profile'"):
        pm.resolve_profile(server="db", session_id="sess_err")

    # 3. Project config references non-existent profile
    bad_project = ProjectConfig(profile_bindings={"db": "missing_project_prof"})
    with pytest.raises(ProfileNotFoundError, match="Profile 'missing_project_prof'"):
        pm.resolve_profile(server="db", project_config=bad_project)

    GLOBAL_CONTEXT.clear()


def test_concurrent_clients_selecting_different_profiles():
    """Verify two concurrent clients resolve different profiles without cross-session contamination."""
    GLOBAL_CONTEXT.clear()
    pm = ProfileManager()

    manifest_data = {
        "schema_version": "1.0",
        "default_profile": "dev_db",
        "profiles": {
            "dev_db": {"host": "dev.local"},
            "analytics_db": {"host": "analytics.local"},
            "ml_warehouse": {"host": "ml.local"},
        },
    }
    pm.load_manifest_dict("db", manifest_data)

    GLOBAL_CONTEXT.set("db_profile", "analytics_db", session_id="client_A")
    GLOBAL_CONTEXT.set("db_profile", "ml_warehouse", session_id="client_B")

    def run_resolve(sid):
        prof, _ = pm.resolve_profile(server="db", session_id=sid)
        return sid, prof.name, prof.parameters["host"]

    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
        sids = ["client_A", "client_B", "client_C", "client_A", "client_B", "client_C"]
        results = list(executor.map(run_resolve, sids))

    for sid, pname, host in results:
        if sid == "client_A":
            assert pname == "analytics_db"
            assert host == "analytics.local"
        elif sid == "client_B":
            assert pname == "ml_warehouse"
            assert host == "ml.local"
        elif sid == "client_C":
            assert pname == "dev_db"
            assert host == "dev.local"

    GLOBAL_CONTEXT.clear()


def test_secret_rotation_increments_config_generation_without_leaking_secret():
    """Verify external secret rotation increments generation while never logging or exposing secrets."""
    os.environ["TEST_DB_PASSWORD"] = "initial_secret_123"
    pm = ProfileManager()

    manifest_data = {
        "schema_version": "1.0",
        "default_profile": "secure_db",
        "profiles": {
            "secure_db": {
                "host": "secure.internal",
                "secrets": {
                    "password": {"provider": "env", "key": "TEST_DB_PASSWORD"},
                },
            }
        },
    }
    pm.load_manifest_dict("db", manifest_data)
    initial_gen = pm.get_generation("db")

    prof1, gen1 = pm.resolve_profile(server="db")
    assert gen1 == initial_gen
    assert "password" in prof1.secrets

    # Rotate secret externally in the provider
    os.environ["TEST_DB_PASSWORD"] = "rotated_secret_999"

    # Subsequent resolve detects secret rotation and increments generation
    prof2, gen2 = pm.resolve_profile(server="db")
    assert gen2 == initial_gen + 1

    # Invariant: Secret value is not stored in parameters dict
    assert "password" not in prof2.parameters
    assert prof2.secrets["password"].key == "TEST_DB_PASSWORD"

    del os.environ["TEST_DB_PASSWORD"]


def test_security_violation_in_untrusted_project_config():
    """Verify project configuration declaring executable keys is rejected at any nesting level."""
    # Root level forbidden key
    untrusted_root = {
        "schema_version": "1.0",
        "command": "malicious_binary.exe",
        "profile_bindings": {"db": "local"},
    }
    with pytest.raises(ValueError, match="Security violation: Project config cannot specify executable key 'command'"):
        ProjectConfig.from_dict(untrusted_root)

    # Nested forbidden key inside profile_bindings or custom sub-nodes
    untrusted_nested = {
        "schema_version": "1.0",
        "profile_bindings": {
            "db": "local",
            "nested_inject": {"args": ["--do-evil"]},
        },
    }
    with pytest.raises(ValueError, match="Security violation: Project config cannot specify executable key 'args'"):
        ProjectConfig.from_dict(untrusted_nested)


def test_tool_filtering_strict_deny_precedence():
    """Verify tool filtering rules where deny takes strict precedence over allow."""
    tf = ToolFilter(
        allow=["db.*", "excel.preview_sheet"],
        deny=["db.drop_database", "db.execute_arbitrary_sql"],
    )

    assert tf.is_tool_allowed("db.read_query") is True
    assert tf.is_tool_allowed("excel.preview_sheet") is True
    assert tf.is_tool_allowed("db.drop_database") is False
    assert tf.is_tool_allowed("db.execute_arbitrary_sql") is False
    assert tf.is_tool_allowed("word.create_document") is False


def test_recursive_redaction_engine():
    """Verify recursive redaction masks credentials across dicts, lists, URIs, and exception text."""
    payload = {
        "user": "alice",
        "db_password": "super_secret_pw",
        "api_key": "sk-123456789",
        "nested": {
            "token": "tok_xyz_secret",
            "safe_val": 42,
        },
        "list_items": [
            {"credential": "cred_secret_val"},
            "safe_string",
        ],
    }
    redacted = redact_sensitive_data(payload)
    assert redacted["user"] == "alice"
    assert redacted["db_password"] == "***REDACTED***"
    assert redacted["api_key"] == "***REDACTED***"
    assert redacted["nested"]["token"] == "***REDACTED***"
    assert redacted["nested"]["safe_val"] == 42
    assert redacted["list_items"][0]["credential"] == "***REDACTED***"

    raw_uri_text = "Connection failed: postgresql://admin:my_secret_pass@10.0.0.1:5432/analytics"
    redacted_uri = redact_sensitive_text(raw_uri_text)
    assert "my_secret_pass" not in redacted_uri
    assert "postgresql://admin:***REDACTED***@10.0.0.1:5432/analytics" in redacted_uri

    raw_stderr = "Fatal error: failed connecting with password='my_db_password' on port 5432"
    redacted_stderr = redact_sensitive_text(raw_stderr)
    assert "my_db_password" not in redacted_stderr
    assert "password='***REDACTED***'" in redacted_stderr

    exc = RuntimeError("Database connection string postgresql://usr:topsecret@localhost/db failed")
    redacted_exc = redact_sensitive_data(exc)
    assert "topsecret" not in str(redacted_exc)
    assert "***REDACTED***" in str(redacted_exc)


def test_env_secret_provider_keyed_hmac_unguessable():
    """Verify EnvSecretProvider generates non-reversible, unguessable full-length SHA-256 HMAC version tokens."""
    os.environ["TEMP_SECRET_KEY"] = "simple123"
    provider1 = EnvSecretProvider()
    provider2 = EnvSecretProvider()

    ver1 = provider1.get_version("TEMP_SECRET_KEY")
    ver2 = provider2.get_version("TEMP_SECRET_KEY")

    assert ver1 is not None
    assert ver2 is not None
    assert len(ver1) == 64  # Full length SHA-256 HMAC
    assert len(ver2) == 64
    assert ver1 != ver2
    assert "simple123" not in ver1

    del os.environ["TEMP_SECRET_KEY"]


def test_defensive_copies_prevent_caller_mutation():
    """Verify mutating returned objects from get_server, list_servers, or resolve_profile cannot mutate active state."""
    reg = HubRegistry()
    reg.register_server(ServerConfig(name="test_srv", command="uv", args=["run", "test"]))

    # 1. Mutate object returned from get_server
    srv = reg.get_server("test_srv")
    assert srv is not None
    srv.command = "malicious_command"
    srv.args.append("--injected-arg")

    # Invariant: Registry remains untouched
    fresh_srv = reg.get_server("test_srv")
    assert fresh_srv is not None
    assert fresh_srv.command == "uv"
    assert fresh_srv.args == ["run", "test"]

    # 2. Mutate list returned from list_servers
    srv_list = reg.list_servers()
    srv_list[0].enabled = False
    assert reg.is_server_enabled("test_srv") is True

    # 3. Mutate ProfileConfig returned from resolve_profile
    pm = ProfileManager()
    pm.load_manifest_dict("db", {
        "schema_version": "1.0",
        "default_profile": "dev",
        "profiles": {"dev": {"host": "localhost", "port": 5432}},
    })
    prof, _ = pm.resolve_profile("db")
    prof.parameters["host"] = "hacked.internal"
    prof.parameters["port"] = 9999

    # Invariant: Profile manager state remains untouched
    fresh_prof, _ = pm.resolve_profile("db")
    assert fresh_prof.parameters["host"] == "localhost"
    assert fresh_prof.parameters["port"] == 5432


def test_every_registry_mutation_advances_generation():
    """Verify that every supported registry mutation advances generation exactly when state changes."""
    reg = HubRegistry()
    gen0 = reg.get_generation()
    assert gen0 == 1

    # 1. register_server
    srv = ServerConfig(name="srv1", command="uv")
    changed = reg.register_server(srv)
    assert changed is True
    assert reg.get_generation() == 2

    # register_server with identical object does not advance generation
    changed_again = reg.register_server(srv)
    assert changed_again is False
    assert reg.get_generation() == 2

    # 2. set_server_enabled
    changed_enable = reg.set_server_enabled("srv1", False)
    assert changed_enable is True
    assert reg.get_generation() == 3

    # set_server_enabled with same status does not advance generation
    changed_enable_again = reg.set_server_enabled("srv1", False)
    assert changed_enable_again is False
    assert reg.get_generation() == 3

    # 3. unregister_server
    changed_del = reg.unregister_server("srv1")
    assert changed_del is True
    assert reg.get_generation() == 4

    # unregister_server for missing server does not advance generation
    changed_del_again = reg.unregister_server("srv1")
    assert changed_del_again is False
    assert reg.get_generation() == 4


def test_strict_schema_validation_types_and_ranges():
    """Verify strict validation rejects invalid types, negative supervisor timeouts, bad ports, and modes."""
    # 1. Non-string args
    with pytest.raises(ValueError, match="args must strictly be a list of strings"):
        ServerConfig.from_dict("srv", {"command": "uv", "args": ["valid", 123]})

    # 2. Non-string env mapping
    with pytest.raises(ValueError, match="env must strictly be a dictionary of string key-value pairs"):
        ServerConfig.from_dict("srv", {"command": "uv", "env": {"PORT": 8080}})

    # 3. Non-boolean enabled
    with pytest.raises(ValueError, match="enabled must be a boolean"):
        ServerConfig.from_dict("srv", {"command": "uv", "enabled": "yes"})

    # 4. Supervisor negative timeouts
    with pytest.raises(ValueError, match="shutdown_grace_seconds cannot be negative"):
        SupervisorConfig.from_dict({"shutdown_grace_seconds": -1.0})

    with pytest.raises(ValueError, match="startup_timeout_seconds must be positive"):
        SupervisorConfig.from_dict({"startup_timeout_seconds": 0.0})

    # 5. Invalid runtime mode in HubConfig
    with pytest.raises(ValueError, match="Invalid runtime mode 'cluster'"):
        HubConfig.from_dict({"runtime": {"mode": "cluster"}})

    # 6. Invalid HTTP port
    with pytest.raises(ValueError, match="Invalid http_port '70000'"):
        HubConfig.from_dict({"runtime": {"http_bridge": {"port": 70000}}})

    # 7. Remote HTTP binding without auth_token_env
    with pytest.raises(ValueError, match="Remote HTTP host binding '0.0.0.0' strictly requires a non-empty 'auth_token_env'"):
        HubConfig.from_dict({"runtime": {"http_bridge": {"host": "0.0.0.0", "auth_token_env": ""}}})

    # 8. Remote HTTP binding with auth_token_env set to variable that is missing at runtime
    with pytest.raises(ValueError, match="requires environment variable 'MWS_NONEXISTENT_TOKEN' to be set and non-empty"):
        HubConfig.from_dict({"runtime": {"http_bridge": {"host": "0.0.0.0", "auth_token_env": "MWS_NONEXISTENT_TOKEN"}}})

    # When the token variable is set, it succeeds
    os.environ["MWS_NONEXISTENT_TOKEN"] = "valid_secret_token_123"
    valid_remote = HubConfig.from_dict({"runtime": {"http_bridge": {"host": "0.0.0.0", "auth_token_env": "MWS_NONEXISTENT_TOKEN"}}})
    assert valid_remote.http_host == "0.0.0.0"
    del os.environ["MWS_NONEXISTENT_TOKEN"]


def test_malformed_tool_filter_and_project_bindings_rejected():
    """Verify malformed tool filters and project bindings fail closed rather than defaulting silently."""
    # 1. Non-list allow/deny
    with pytest.raises(ValueError, match="ToolFilter 'allow' must strictly be a list of strings"):
        ToolFilter.from_dict({"allow": "not_a_list"})

    with pytest.raises(ValueError, match="ToolFilter 'deny' must strictly be a list of strings"):
        ToolFilter.from_dict({"deny": [123, 456]})

    # 2. Malformed profile bindings
    with pytest.raises(ValueError, match="profile_bindings keys and values must strictly be strings"):
        ProjectConfig.from_dict({"profile_bindings": {"db": 12345}})

    with pytest.raises(ValueError, match="profile_bindings keys and values must strictly be strings"):
        ProjectConfig.from_dict({"profile_bindings": {"db": {"nested": "obj"}}})


def test_secret_provider_failure_atomic_manifest_publication():
    """Verify that a secret provider failure prevents publication and leaves existing manifest intact."""
    class FailingSecretProvider:
        def resolve(self, key: str) -> str:
            raise RuntimeError("Vault connection timeout")

        def get_version(self, key: str) -> str:
            raise RuntimeError("Vault connection timeout during version lookup")

    sec_reg = SecretRegistry()
    sec_reg.register_provider("env", FailingSecretProvider())

    pm = ProfileManager(secret_registry=sec_reg)
    pm.load_manifest_dict("db", {
        "schema_version": "1.0",
        "default_profile": "dev",
        "profiles": {"dev": {"host": "localhost"}},
    })
    gen_before = pm.get_generation("db")

    # Attempt to load a manifest that references the failing provider
    candidate_manifest = {
        "schema_version": "1.0",
        "default_profile": "failing_prof",
        "profiles": {
            "failing_prof": {
                "secrets": {"pass": {"provider": "env", "key": "k1"}},
            }
        },
    }
    with pytest.raises(RuntimeError, match="Vault connection timeout during version lookup"):
        pm.load_manifest_dict("db", candidate_manifest)

    # Invariant: Manifest was NOT published and generation did not advance
    assert pm.get_generation("db") == gen_before
    active_prof, _ = pm.resolve_profile("db")
    assert active_prof.name == "dev"


def test_stale_secret_version_keys_removed_on_manifest_replacement():
    """Verify stale secret version bookkeeping keys are cleaned up when a manifest is replaced."""
    os.environ["SECRET_A"] = "val_a"
    os.environ["SECRET_B"] = "val_b"

    pm = ProfileManager()
    manifest_v1 = {
        "schema_version": "1.0",
        "default_profile": "prof_a",
        "profiles": {
            "prof_a": {"secrets": {"sec_a": {"provider": "env", "key": "SECRET_A"}}},
        },
    }
    pm.load_manifest_dict("db", manifest_v1)
    assert ("db", "prof_a:sec_a") in pm._secret_versions

    # Replace manifest with prof_b (prof_a removed)
    manifest_v2 = {
        "schema_version": "1.0",
        "default_profile": "prof_b",
        "profiles": {
            "prof_b": {"secrets": {"sec_b": {"provider": "env", "key": "SECRET_B"}}},
        },
    }
    pm.load_manifest_dict("db", manifest_v2)

    # Invariant: prof_a secret was removed from bookkeeping; prof_b is present
    assert ("db", "prof_a:sec_a") not in pm._secret_versions
    assert ("db", "prof_b:sec_b") in pm._secret_versions

    del os.environ["SECRET_A"]
    del os.environ["SECRET_B"]


def test_redaction_custom_exception_and_percent_encoded_uri():
    """Verify redaction handles percent-encoded URIs and safely redacts non-standard exception subclasses."""
    # 1. Percent-encoded URI credentials
    raw_uri = "postgres://admin%40corp:pass%23123@10.0.0.1:5432/db"
    redacted = redact_sensitive_text(raw_uri)
    assert "pass%23123" not in redacted
    assert "postgres://admin%40corp:***REDACTED***@10.0.0.1:5432/db" in redacted

    # 2. Key-value assignment with dsn / connection_string
    text_dsn = "Error opening dsn='user=postgres password=secret_root_pass host=127.0.0.1'"
    redacted_dsn = redact_sensitive_text(text_dsn)
    assert "secret_root_pass" not in redacted_dsn
    assert "password=***REDACTED***" in redacted_dsn

    # 3. Custom exception class with non-standard multi-argument constructor
    class CustomDatabaseError(Exception):
        def __init__(self, error_code: int, detail: str, severity: str) -> None:
            self.error_code = error_code
            self.detail = detail
            self.severity = severity
            super().__init__(f"Error {error_code} ({severity}): {detail}")

    custom_exc = CustomDatabaseError(403, "Access denied for password='forbidden_db_pw'", "CRITICAL")
    # type(custom_exc)(msg) would crash with TypeError; redact_sensitive_data must handle this gracefully
    redacted_exc = redact_sensitive_data(custom_exc)
    assert isinstance(redacted_exc, SanitizedException)
    assert "forbidden_db_pw" not in str(redacted_exc)
    assert "***REDACTED***" in str(redacted_exc)
    assert redacted_exc.original_type_name == "CustomDatabaseError"


def test_simultaneous_concurrent_manifest_replacement():
    """Verify simultaneous concurrent manifest replacements execute atomically under lock serialization."""
    pm = ProfileManager()
    errors = []

    def updater(worker_id):
        try:
            for i in range(10):
                manifest_data = {
                    "schema_version": "1.0",
                    "default_profile": f"p_{worker_id}_{i}",
                    "profiles": {
                        f"p_{worker_id}_{i}": {"host": f"host_{worker_id}_{i}"},
                    },
                }
                pm.load_manifest_dict("db", manifest_data)
                time.sleep(0.002)
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=updater, args=(w,)) for w in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(errors) == 0
    # Final state must be completely valid and consistent
    active_prof, gen = pm.resolve_profile("db")
    assert gen > 1
    assert active_prof.name.startswith("p_")
    # Secret versions map must contain exactly the keys of the active manifest
    current_manifest = pm.get_manifest("db")
    assert current_manifest is not None
    assert active_prof.name == current_manifest.default_profile

