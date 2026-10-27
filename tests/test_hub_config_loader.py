"""
Unit and integration tests for Central Configuration Loader (Phase 5 Step 1).
Tests 5-tier discovery precedence, deterministic YAML/JSON selection, schema validation,
profile bridging, fail-closed remote auth, template generation, and Windows path safety.
"""

import json
from pathlib import Path

import pytest

from mcp_win_stdio.core.hub.config_loader import (
    generate_default_hub_config,
    load_hub_config,
    resolve_config_path,
)
from mcp_win_stdio.core.hub.models import ServerState
from mcp_win_stdio.core.hub.profiles import ProfileManager, ProfileNotFoundError


def test_cli_path_takes_precedence_over_all(tmp_path, monkeypatch):
    """Explicit CLI path takes strict precedence over env var, project, and user config."""
    cli_file = tmp_path / "cli_config.yaml"
    cli_file.write_text("schema_version: '1.0'\nruntime:\n  http_bridge:\n    port: 9001\n", encoding="utf-8")

    env_file = tmp_path / "env_config.yaml"
    env_file.write_text("schema_version: '1.0'\nruntime:\n  http_bridge:\n    port: 9002\n", encoding="utf-8")
    monkeypatch.setenv("MWS_HUB_CONFIG", str(env_file))

    cwd_dir = tmp_path / "project"
    cwd_dir.mkdir()
    (cwd_dir / "hub.yaml").write_text("schema_version: '1.0'\nruntime:\n  http_bridge:\n    port: 9003\n", encoding="utf-8")

    user_dir = tmp_path / "user"
    user_dir.mkdir()
    (user_dir / "hub.yaml").write_text("schema_version: '1.0'\nruntime:\n  http_bridge:\n    port: 9004\n", encoding="utf-8")

    path, tier = resolve_config_path(cli_path=cli_file, cwd=cwd_dir, user_dir=user_dir)
    assert path == cli_file.resolve()
    assert tier == "cli_argument"

    loaded = load_hub_config(cli_path=cli_file, cwd=cwd_dir, user_dir=user_dir)
    assert loaded.config.http_port == 9001
    assert loaded.source_tier == "cli_argument"


def test_env_var_takes_precedence_when_no_cli(tmp_path, monkeypatch):
    """MWS_HUB_CONFIG takes precedence when no CLI path is provided."""
    env_file = tmp_path / "env_config.yaml"
    env_file.write_text("schema_version: '1.0'\nruntime:\n  http_bridge:\n    port: 9002\n", encoding="utf-8")
    monkeypatch.setenv("MWS_HUB_CONFIG", str(env_file))

    cwd_dir = tmp_path / "project"
    cwd_dir.mkdir()
    (cwd_dir / "hub.yaml").write_text("schema_version: '1.0'\n", encoding="utf-8")

    path, tier = resolve_config_path(cli_path=None, cwd=cwd_dir)
    assert path == env_file.resolve()
    assert tier == "environment_variable"


def test_project_local_discovery_precedence(tmp_path, monkeypatch):
    """Project-local .mws/hub.yaml takes precedence over root hub.yaml and user-global."""
    monkeypatch.delenv("MWS_HUB_CONFIG", raising=False)

    cwd_dir = tmp_path / "my_project"
    mws_dir = cwd_dir / ".mws"
    mws_dir.mkdir(parents=True)
    mws_file = mws_dir / "hub.yaml"
    mws_file.write_text("schema_version: '1.0'\nruntime:\n  http_bridge:\n    port: 8081\n", encoding="utf-8")

    root_file = cwd_dir / "hub.yaml"
    root_file.write_text("schema_version: '1.0'\nruntime:\n  http_bridge:\n    port: 8082\n", encoding="utf-8")

    user_dir = tmp_path / "user"
    user_dir.mkdir()
    (user_dir / "hub.yaml").write_text("schema_version: '1.0'\nruntime:\n  http_bridge:\n    port: 8083\n", encoding="utf-8")

    path, tier = resolve_config_path(cwd=cwd_dir, user_dir=user_dir)
    assert path == mws_file.resolve()
    assert tier == "project_local"


def test_user_global_yaml_over_json_with_warning(tmp_path, monkeypatch, caplog):
    """When both hub.yaml and legacy hub.json exist in user directory, YAML wins and logs warning."""
    monkeypatch.delenv("MWS_HUB_CONFIG", raising=False)
    user_dir = tmp_path / "user_home" / ".mcp-win-stdio"
    user_dir.mkdir(parents=True)

    yaml_file = user_dir / "hub.yaml"
    yaml_file.write_text("schema_version: '1.0'\nruntime:\n  http_bridge:\n    port: 8090\n", encoding="utf-8")

    json_file = user_dir / "hub.json"
    json_file.write_text(json.dumps({"schema_version": "1.0", "runtime": {"http_bridge": {"port": 8091}}}), encoding="utf-8")

    empty_cwd = tmp_path / "empty_project"
    empty_cwd.mkdir()

    with caplog.at_level("WARNING"):
        path, tier = resolve_config_path(cwd=empty_cwd, user_dir=user_dir)
        assert path == yaml_file.resolve()
        assert tier == "user_global"
        assert "takes precedence" in caplog.text


def test_explicit_missing_file_raises_immediately(tmp_path, monkeypatch):
    """Missing file specified via CLI or environment raises FileNotFoundError without silent fallback."""
    # 1. CLI path
    with pytest.raises(FileNotFoundError, match="Explicitly specified configuration file not found"):
        resolve_config_path(cli_path=tmp_path / "nonexistent.yaml")

    # 2. Env variable
    monkeypatch.setenv("MWS_HUB_CONFIG", str(tmp_path / "ghost_env.yaml"))
    with pytest.raises(FileNotFoundError, match="Configuration file specified in MWS_HUB_CONFIG not found"):
        resolve_config_path()


def test_malformed_yaml_or_json_raises_actionable_error(tmp_path):
    """Corrupted or invalid syntax raises ValueError with file path context."""
    bad_yaml = tmp_path / "corrupt.yaml"
    bad_yaml.write_text("schema_version: '1.0'\nruntime: [invalid yaml {:\n", encoding="utf-8")

    with pytest.raises(ValueError, match="Invalid YAML"):
        load_hub_config(cli_path=bad_yaml)

    bad_json = tmp_path / "corrupt.json"
    bad_json.write_text("{ unquoted_key: 123 ", encoding="utf-8")

    with pytest.raises(ValueError, match="Invalid JSON"):
        load_hub_config(cli_path=bad_json)


def test_unsupported_fields_rejected(tmp_path):
    """Unsupported top-level or runtime fields must be rejected fail-closed."""
    # 1. Unknown top-level key
    bad_top = tmp_path / "bad_top.yaml"
    bad_top.write_text("schema_version: '1.0'\nunknown_section:\n  foo: bar\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Unsupported top-level configuration key"):
        load_hub_config(cli_path=bad_top)

    # 2. Unknown runtime key
    bad_rt = tmp_path / "bad_rt.yaml"
    bad_rt.write_text("schema_version: '1.0'\nruntime:\n  cluster_discovery: true\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Unsupported runtime configuration key"):
        load_hub_config(cli_path=bad_rt)


def test_invalid_ports_and_env_names_rejected(tmp_path):
    """Out-of-range port numbers and malformed env variable names must be rejected."""
    # Invalid port (out of range)
    p_high = tmp_path / "port_high.yaml"
    p_high.write_text("schema_version: '1.0'\nruntime:\n  http_bridge:\n    port: 70000\n", encoding="utf-8")
    with pytest.raises(ValueError, match="between 1 and 65535"):
        load_hub_config(cli_path=p_high)

    # Invalid env var name (contains dashes)
    bad_env = tmp_path / "bad_env.yaml"
    bad_env.write_text("schema_version: '1.0'\nruntime:\n  http_bridge:\n    auth_token_env: 'INVALID-NAME!'\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Invalid environment variable name"):
        load_hub_config(cli_path=bad_env)


def test_remote_binding_without_auth_fails_closed(tmp_path, monkeypatch):
    """Remote host binding (0.0.0.0) without an existing non-empty env token fails closed."""
    monkeypatch.delenv("UNSET_TOKEN_XYZ", raising=False)
    remote_cfg = tmp_path / "remote.yaml"
    remote_cfg.write_text(
        "schema_version: '1.0'\nruntime:\n  http_bridge:\n    host: 0.0.0.0\n    auth_token_env: UNSET_TOKEN_XYZ\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="requires environment variable 'UNSET_TOKEN_XYZ' to be set and non-empty"):
        load_hub_config(cli_path=remote_cfg)


def test_defaults_bind_loopback_and_empty_servers():
    """Default implicit configuration binds to 127.0.0.1:8080 and does not blindly enable servers."""
    loaded = load_hub_config(cli_path=None, cwd=Path("nonexistent_path_xyz"), user_dir=Path("nonexistent_user_dir_xyz"))
    assert loaded.config.http_host == "127.0.0.1"
    assert loaded.config.http_port == 8080
    assert len(loaded.config.servers) == 0
    assert loaded.source_tier == "default_implicit"
    assert loaded.source_path is None


def test_existing_connection_profiles_bridged_without_credentials_in_hub(tmp_path):
    """Existing db_connections.json and ssh_hosts.json are bridged into ProfileManager."""
    user_dir = tmp_path / ".mcp-win-stdio"
    user_dir.mkdir()

    # 1. Setup db_connections.json
    db_conns = {
        "default": "prod_postgres",
        "connections": {
            "prod_postgres": {
                "type": "postgres",
                "url": "postgresql://admin:secret_pass_123@db.prod.internal:5432/main",
            },
            "analytics_mysql": {
                "type": "mysql",
                "host": "analytics.internal",
                "user": "analyst",
            },
        },
    }
    (user_dir / "db_connections.json").write_text(json.dumps(db_conns), encoding="utf-8")

    # 2. Setup ssh_hosts.json
    ssh_hosts = {
        "active_host": "bastion",
        "hosts": {
            "bastion": {
                "hostname": "bastion.corp.net",
                "port": 2222,
                "user": "secops",
            }
        },
    }
    (user_dir / "ssh_hosts.json").write_text(json.dumps(ssh_hosts), encoding="utf-8")

    # Load configuration
    pm = ProfileManager()
    loaded = load_hub_config(user_dir=user_dir, profile_manager=pm)

    # Hub config has NO passwords or database URLs copied into it
    assert "secret_pass_123" not in str(loaded.config.__dict__)

    # Profiles are properly registered in ProfileManager
    prof_db, _ = pm.resolve_profile("db")
    assert prof_db.name == "prod_postgres"
    assert prof_db.type == "postgres"

    prof_ssh, _ = pm.resolve_profile("ssh")
    assert prof_ssh.name == "bastion"
    assert prof_ssh.parameters["port"] == 2222


def test_missing_higher_priority_profile_fails_immediately(tmp_path):
    """Explicitly requesting a missing profile via override fails immediately with ProfileNotFoundError."""
    user_dir = tmp_path / ".mcp-win-stdio"
    user_dir.mkdir()
    (user_dir / "db_connections.json").write_text(
        json.dumps({"default": "local_db", "connections": {"local_db": {"type": "sqlite"}}}),
        encoding="utf-8",
    )

    pm = ProfileManager()
    load_hub_config(user_dir=user_dir, profile_manager=pm)

    # Request override for non-existent profile
    with pytest.raises(ProfileNotFoundError, match="Profile 'ghost_database'"):
        pm.resolve_profile("db", request_override="ghost_database")


def test_default_template_generation_safeguards(tmp_path):
    """generate_default_hub_config generates valid template and prevents accidental overwrite."""
    out_file = tmp_path / "generated_hub.yaml"

    # 1. First generation succeeds
    content1 = generate_default_hub_config(target_path=out_file)
    assert "schema_version: \"1.0\"" in content1
    assert "127.0.0.1" in content1
    assert out_file.exists()

    # 2. Overwrite=False fails closed if file exists
    with pytest.raises(FileExistsError, match="already exists"):
        generate_default_hub_config(target_path=out_file, overwrite=False)

    # 3. Overwrite=True succeeds
    content2 = generate_default_hub_config(target_path=out_file, overwrite=True)
    assert content2 == content1


def test_windows_paths_with_spaces_and_special_chars(tmp_path):
    """Path resolution operates cleanly with Windows paths containing spaces."""
    spaced_dir = tmp_path / "My Folder With Spaces" / "Deep Path"
    spaced_dir.mkdir(parents=True)
    config_file = spaced_dir / "hub.yaml"
    config_file.write_text("schema_version: '1.0'\nruntime:\n  http_bridge:\n    port: 8088\n", encoding="utf-8")

    resolved_path, tier = resolve_config_path(cli_path=config_file)
    assert resolved_path == config_file.resolve()
    assert tier == "cli_argument"

    loaded = load_hub_config(cli_path=config_file)
    assert loaded.config.http_port == 8088
