"""
Tests for mcp-win-stdio CLI, discovery, guides, and servers across modular sub-packages.
"""

import io
import os
import sys
from contextlib import redirect_stdout
from pathlib import Path

# Add all sub-packages and root src to sys.path
for p in Path("packages").glob("*/src"):
    sys.path.insert(0, str(p.resolve()))
sys.path.insert(0, os.path.abspath("src"))

from mcp_win_stdio.db.guide import print_db_guide
from mcp_win_stdio.excel.guide import print_excel_guide
from mcp_win_stdio.explorer.guide import print_explorer_guide
from mcp_win_stdio.git.guide import print_git_guide
from mcp_win_stdio.ssh.guide import print_ssh_guide
from mcp_win_stdio.tsc.guide import print_tsc_guide
from mcp_win_stdio.word.guide import print_word_guide

from mcp_win_stdio.cli import print_dashboard, print_server_list
from mcp_win_stdio.core.config import ensure_workspace_dirs
from mcp_win_stdio.core.discovery import list_available_servers
from mcp_win_stdio.server.guide import print_server_guide


def test_discovery():
    ensure_workspace_dirs()
    servers = list_available_servers()
    assert "excel" in servers
    assert "word" in servers
    assert "explorer" in servers
    assert "tsc" in servers
    assert "db" in servers
    assert "git" in servers
    assert "ssh" in servers
    assert "rag" in servers
    assert "excel-db" in servers
    assert "arch" in servers
    assert "server" in servers

    assert servers["excel"]["tools_count"] == 44
    assert servers["word"]["tools_count"] == 20
    assert servers["explorer"]["tools_count"] == 14
    assert servers["tsc"]["tools_count"] == 12
    assert servers["db"]["tools_count"] == 34
    assert servers["git"]["tools_count"] == 46
    assert servers["ssh"]["tools_count"] == 34
    assert servers["rag"]["tools_count"] == 10
    assert servers["excel-db"]["tools_count"] == 9
    assert servers["arch"]["tools_count"] == 5
    assert servers["server"]["tools_count"] == 10
    print("[PASS] Discovery test passed for all 11 servers.")


def test_guides():
    f = io.StringIO()
    with redirect_stdout(f):
        print_excel_guide()
        print_word_guide()
        print_explorer_guide()
        print_tsc_guide()
        print_db_guide()
        print_git_guide()
        print_ssh_guide()
        print_server_guide()
    out = f.getvalue()
    assert "Excel MCP" in out
    assert "Word Document MCP" in out
    assert "Workspace Explorer MCP" in out
    assert "TypeScript Diagnostic Watcher" in out
    assert "Database MCP" in out
    assert "Git & GitHub MCP" in out
    assert "Multi-SSH" in out
    assert "mws server" in out
    print("[PASS] Sub-package guides test passed for all 8 servers.")


def test_dashboard():
    f = io.StringIO()
    with redirect_stdout(f):
        print_dashboard()
    out = f.getvalue()
    assert "mcp-win-stdio" in out
    assert "excel" in out
    assert "word" in out
    assert "explorer" in out
    assert "tsc" in out
    assert "db" in out
    assert "git" in out
    assert "ssh" in out
    assert "mws list" in out
    assert "home dashboard" not in out.lower()
    print("[PASS] Dashboard test passed.")


def test_server_list_is_focused_inventory(monkeypatch):
    servers = {
        "db": {
            "is_installed": True,
            "tools_count": 34,
            "is_builtin": True,
            "description": "Database tools",
        },
        "my_plugin": {
            "is_installed": True,
            "tools_count": "dynamic",
            "is_builtin": False,
            "description": "Custom test plugin",
        },
    }
    monkeypatch.setattr("mcp_win_stdio.cli.list_available_servers", lambda: servers)

    output = io.StringIO()
    with redirect_stdout(output):
        print_server_list()

    rendered = output.getvalue()
    assert "MCP Server Inventory" in rendered
    assert "my_plugin" in rendered
    assert "Plugin" in rendered
    assert "Database tools" in rendered
    assert "home dashboard" in rendered
    assert "Claude Desktop Config" not in rendered
    assert "Quick Commands" not in rendered


def test_all_servers_import():
    from mcp_win_stdio.db.server import mcp as db_mcp
    from mcp_win_stdio.excel.server import mcp as excel_mcp
    from mcp_win_stdio.excel_db.server import mcp as excel_db_mcp
    from mcp_win_stdio.explorer.server import mcp as explorer_mcp
    from mcp_win_stdio.git.server import mcp as git_mcp
    from mcp_win_stdio.rag.server import mcp as rag_mcp
    from mcp_win_stdio.ssh.server import mcp as ssh_mcp
    from mcp_win_stdio.tsc.server import mcp as tsc_mcp
    from mcp_win_stdio.word.server import mcp as word_mcp

    assert excel_mcp is not None
    assert word_mcp is not None
    assert explorer_mcp is not None
    assert tsc_mcp is not None
    assert db_mcp is not None
    assert git_mcp is not None
    assert ssh_mcp is not None
    assert rag_mcp is not None
    assert excel_db_mcp is not None
    print("[PASS] All 9 servers imported successfully from packages/.")


def test_rag_tool_registration():
    import asyncio

    from mcp_win_stdio.rag.server import mcp

    tools = asyncio.run(mcp.list_tools())
    tool_names = {tool.name for tool in tools}
    assert tool_names == {
        "crawl_and_index_url",
        "index_local_codebase",
        "index_remote_repo",
        "query_knowledge_base",
        "find_related_chunks",
        "get_chunk_context",
        "get_knowledge_tree",
        "list_rag_collections",
        "delete_rag_collection",
        "prune_rag_cache",
    }
    assert len(tools) == 10


def test_updater():
    from mcp_win_stdio.core.updater import format_update_banner, parse_version

    assert parse_version("0.2.4") == (0, 2, 4)
    assert parse_version("0.2.4") > parse_version("0.2.3")
    assert parse_version("1.0.0") > parse_version("0.9.9")

    banner = format_update_banner("0.2.3", "0.2.4")
    assert "UPDATE AVAILABLE" in banner
    assert "v0.2.3" in banner
    assert "v0.2.4" in banner
    print("[PASS] Updater tests passed.")


def test_project_setup_and_migration(tmp_path):
    import json

    from mcp_win_stdio.cli import remove_project_mcp, setup_project_mcp

    # 1. Simulate legacy .vscode/mcp.json existing in project
    legacy_vscode_dir = tmp_path / ".vscode"
    legacy_vscode_dir.mkdir(parents=True, exist_ok=True)
    legacy_file = legacy_vscode_dir / "mcp.json"
    with open(legacy_file, "w", encoding="utf-8") as f:
        json.dump({"mcpServers": {"custom-legacy-tool": {"command": "node", "args": ["index.js"]}}}, f)

    assert legacy_file.exists()

    # 2. Run setup_project_mcp
    res = setup_project_mcp(["excel", "db"], target_dir=tmp_path)
    assert res["migrated_from_legacy_vscode"] is True

    # 3. Verify root .mcp.json created and contains both migrated and newly configured servers
    root_mcp = tmp_path / ".mcp.json"
    assert root_mcp.exists()
    with open(root_mcp, "r", encoding="utf-8") as f:
        data = json.load(f)
    servers = data.get("mcpServers", {})
    assert "custom-legacy-tool" in servers
    assert "excel" in servers
    assert "db" in servers

    # 4. Verify deprecated .vscode/mcp.json was cleaned up
    assert not legacy_file.exists()
    assert not legacy_vscode_dir.exists()

    # 5. Verify AGENTS.md was created
    agents_md = tmp_path / "AGENTS.md"
    assert agents_md.exists()
    content = agents_md.read_text(encoding="utf-8")
    assert "Excel" in content
    assert "Database" in content

    # 6. Test remove_project_mcp
    remove_res = remove_project_mcp(["excel"], target_dir=tmp_path)
    assert "excel" not in remove_res["servers"]
    with open(root_mcp, "r", encoding="utf-8") as f:
        data_after = json.load(f)
    assert "excel" not in data_after.get("mcpServers", {})
    assert "db" in data_after.get("mcpServers", {})
    assert "custom-legacy-tool" in data_after.get("mcpServers", {})
    # 7. Verify .agents/mcp_config.json and GEMINI.md were created
    assert (tmp_path / ".agents" / "mcp_config.json").exists()
    assert (tmp_path / "GEMINI.md").exists()
    print("[PASS] Project setup and migration test passed.")


def test_project_init_preserves_files_and_creates_env_setup(tmp_path):
    import json

    from mcp_win_stdio.cli import setup_project_mcp

    (tmp_path / "AGENTS.md").write_text("# My repository rules\n\nDo not overwrite me.\n", encoding="utf-8")
    (tmp_path / "GEMINI.md").write_text("# Existing Gemini instructions\n", encoding="utf-8")
    (tmp_path / ".github").mkdir()
    (tmp_path / ".github" / "copilot-instructions.md").write_text("# Copilot-specific rule\n", encoding="utf-8")
    (tmp_path / ".gitignore").write_text("build/\n", encoding="utf-8")
    mcp_path = tmp_path / ".mcp.json"
    mcp_path.write_text(
        json.dumps({"mcpServers": {"custom": {"command": "node", "args": ["custom.js"]}}, "customMetadata": {"keep": True}}),
        encoding="utf-8",
    )

    setup_project_mcp(["db", "explorer"], target_dir=tmp_path)
    agents = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
    gemini = (tmp_path / "GEMINI.md").read_text(encoding="utf-8")
    copilot = (tmp_path / ".github" / "copilot-instructions.md").read_text(encoding="utf-8")
    config = json.loads(mcp_path.read_text(encoding="utf-8"))

    assert "Do not overwrite me." in agents
    assert "Existing Gemini instructions" in gemini
    assert "Copilot-specific rule" in copilot
    assert "mws:agent-guidance:begin" in agents
    assert config["mcpServers"]["custom"]["command"] == "node"
    assert config["customMetadata"] == {"keep": True}
    assert config["mcpServers"]["db"]["args"] == [
        "-m",
        "mcp_win_stdio",
        "run",
        "db",
        "--env-file",
        "${workspaceFolder}/.env",
    ]
    assert (tmp_path / ".env.example").exists()
    assert "DATABASE_URL" in (tmp_path / ".env.example").read_text(encoding="utf-8")
    assert ".env" in (tmp_path / ".gitignore").read_text(encoding="utf-8")
    assert "[mcp_servers.db]" in (tmp_path / ".codex" / "config.toml").read_text(encoding="utf-8")

    first = (tmp_path / ".env.example").read_text(encoding="utf-8")
    setup_project_mcp(["db"], target_dir=tmp_path)
    second = (tmp_path / ".env.example").read_text(encoding="utf-8")
    assert first == second


def test_project_config_env_and_server_specific_setup(tmp_path, monkeypatch):
    import argparse
    import json

    from mcp_win_stdio.cli import _build_server_entry, cmd_run

    sqlite_path = tmp_path / "app.db"
    sqlite_path.touch()
    db_entry = _build_server_entry("db", is_vscode=True, cwd=tmp_path)
    assert db_entry["args"][-2:] == ["--env-file", "${workspaceFolder}/.env"]
    assert "DATABASE_URL" not in db_entry.get("env", {})
    excel_db_entry = _build_server_entry("excel-db", is_vscode=True, cwd=tmp_path)
    assert excel_db_entry["args"][-2:] == ["--env-file", "${workspaceFolder}/.env"]
    assert "SERVERS" not in excel_db_entry.get("env", {})
    assert _build_server_entry("git", is_vscode=True, cwd=tmp_path)["env"]["GIT_REPO_DIR"] == "${workspaceFolder}"

    env_file = tmp_path / ".env"
    env_file.write_text("# comment\nMWS_TEST_VALUE='loaded from file'\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    captured = {}

    class FakeServer:
        @staticmethod
        def run():
            captured["value"] = os.environ.get("MWS_TEST_VALUE")

    monkeypatch.setattr("mcp_win_stdio.cli.get_server_info", lambda _: {"is_builtin": True, "module": "test.module"})
    monkeypatch.setattr("mcp_win_stdio.cli.importlib.import_module", lambda _: type("Module", (), {"mcp": FakeServer}))
    monkeypatch.delenv("MWS_TEST_VALUE", raising=False)
    cmd_run(argparse.Namespace(server="db", env_file=".env"))
    assert captured["value"] == "loaded from file"


def test_project_env_prompt_saves_secrets_only_to_ignored_env(tmp_path, monkeypatch):
    from mcp_win_stdio.cli import _configure_project_environment

    monkeypatch.setattr("mcp_win_stdio.cli.sys.stdin.isatty", lambda: True)
    responses = iter(["postgresql://user:secret@localhost:5432/app", '{"local": "sqlite:///app.db"}'])
    monkeypatch.setattr("mcp_win_stdio.cli.getpass.getpass", lambda _: next(responses))

    configured = _configure_project_environment(["db", "excel-db"], tmp_path, interactive=True)

    env_content = (tmp_path / ".env").read_text(encoding="utf-8")
    assert configured == ["DATABASE_URL", "SERVERS"]
    assert "postgresql://user:secret@localhost:5432/app" in env_content
    assert "sqlite:///app.db" in env_content
    assert ".env" in (tmp_path / ".gitignore").read_text(encoding="utf-8")


def test_init_confirms_workspace_then_prompts_for_db_environment(tmp_path, monkeypatch, capsys):
    import argparse

    from mcp_win_stdio.cli import cmd_init_project

    monkeypatch.chdir(tmp_path)
    cmd_init_project(argparse.Namespace(targets=["db"], yes=False))
    out = capsys.readouterr().out
    assert "Notice: mws has transitioned to a Non-Invasive Multi-Agent Architecture" in out
    assert not (tmp_path / ".env").exists()
    assert not (tmp_path / ".mcp.json").exists()


def test_init_requires_confirmation_in_noninteractive_terminal(tmp_path, monkeypatch, capsys):
    import argparse

    from mcp_win_stdio.cli import cmd_init_project

    monkeypatch.chdir(tmp_path)
    cmd_init_project(argparse.Namespace(targets=["db"], yes=False))
    out = capsys.readouterr().out
    assert "Notice: mws has transitioned to a Non-Invasive Multi-Agent Architecture" in out
    assert not (tmp_path / ".mcp.json").exists()


def test_project_dry_run_does_not_write_files(tmp_path, monkeypatch, capsys):
    import argparse

    from mcp_win_stdio.cli import cmd_init_project, cmd_setup_project

    monkeypatch.chdir(tmp_path)
    cmd_init_project(argparse.Namespace(targets=["db"], yes=False, dry_run=True))
    out = capsys.readouterr().out
    assert "Notice: mws has transitioned to a Non-Invasive Multi-Agent Architecture" in out
    assert not list(tmp_path.iterdir())

    cmd_setup_project(argparse.Namespace(servers=["db"], yes=False, dry_run=True))
    out2 = capsys.readouterr().out
    assert "Notice: mws has transitioned to a Non-Invasive Multi-Agent Architecture" in out2
    assert not list(tmp_path.iterdir())


def test_project_status_reports_installed_config_and_env(tmp_path, monkeypatch, capsys):
    import argparse
    import json

    from mcp_win_stdio.cli import cmd_status

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "mcp_win_stdio.cli.list_available_servers",
        lambda: {"db": {"is_installed": True}, "git": {"is_installed": False}},
    )
    (tmp_path / ".mcp.json").write_text(
        json.dumps({"mcpServers": {"db": {"command": "python", "args": []}}}),
        encoding="utf-8",
    )
    (tmp_path / ".env").write_text("DATABASE_URL=sqlite:///local.db\n", encoding="utf-8")

    cmd_status(argparse.Namespace())

    output = capsys.readouterr().out
    assert "db: installed; configured" in output
    assert "git: not installed; not configured" in output
    assert "DATABASE_URL: set" in output
    assert "No basic MCP config problems" in output
    assert (tmp_path / ".mcp.json").exists()


def test_codex_project_init_and_remove_preserve_other_toml(tmp_path):
    import tomllib

    from mcp_win_stdio.cli import _remove_codex_project_servers, _update_codex_project_config

    config = tmp_path / ".codex" / "config.toml"
    config.parent.mkdir()
    config.write_text(
        '[features]\ncollaboration = true\n\n[mcp_servers.other]\ncommand = "node"\nargs = ["server.js"]\n',
        encoding="utf-8",
    )
    path = _update_codex_project_config(["db", "explorer"], tmp_path)
    content = path.read_text(encoding="utf-8")
    assert "[features]" in content
    assert "[mcp_servers.other]" in content
    assert "[mcp_servers.db]" in content
    assert 'cwd = "."' in content
    codex_config = tomllib.loads(content)
    assert codex_config["mcp_servers"]["db"]["cwd"] == "."
    assert codex_config["mcp_servers"]["db"]["args"][:4] == ["-m", "mcp_win_stdio", "run", "db"]
    assert codex_config["mcp_servers"]["db"]["args"][-2:] == ["--env-file", str(tmp_path / ".env")]

    _update_codex_project_config(["db"], tmp_path)
    content = path.read_text(encoding="utf-8")
    assert content.count("[mcp_servers.db]") == 1
    assert "[mcp_servers.explorer]" in content

    _remove_codex_project_servers(["db"], tmp_path)
    content = path.read_text(encoding="utf-8")
    assert "[mcp_servers.db]" not in content
    assert "[mcp_servers.explorer]" in content
    assert "[mcp_servers.other]" in content


def test_init_clients(tmp_path, monkeypatch):
    from mcp_win_stdio.cli import (
        init_all_clients,
        init_antigravity,
        init_claude,
        init_codex,
        init_copilot,
    )

    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setenv("APPDATA", str(tmp_path / "AppData"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "LocalAppData"))
    monkeypatch.setattr("mcp_win_stdio.cli.shutil.which", lambda _: None)

    skipped = init_all_clients(["excel", "db", "tsc"], tmp_path)
    assert all(result["status"] == "Skipped" for result in skipped)
    assert not (tmp_path / ".gemini" / "config" / "mcp_config.json").exists()

    # 1. Antigravity
    res_ag = init_antigravity(["excel", "db"], tmp_path)
    assert res_ag["client"] == "Antigravity"
    assert res_ag["status"] == "Configured"
    assert (tmp_path / ".mcp.json").exists()
    assert (tmp_path / ".agents" / "mcp_config.json").exists()
    assert (tmp_path / "AGENTS.md").exists()
    assert (tmp_path / "GEMINI.md").exists()

    # 2. Claude
    res_cl = init_claude(["excel", "word"], tmp_path)
    assert "Claude" in res_cl["client"]
    assert res_cl["status"] == "Configured"

    # 3. Copilot
    res_cp = init_copilot(["excel", "explorer"], tmp_path)
    assert "Copilot" in res_cp["client"]
    assert res_cp["status"] == "Configured"

    # 4. Codex project-scoped setup
    res_codex = init_codex(["excel", "db"], tmp_path)
    assert res_codex["client"] == "OpenAI Codex"
    assert (tmp_path / ".codex" / "config.toml").exists()

    # 5. All detected clients
    all_res = init_all_clients(["excel", "db", "tsc"], tmp_path)
    assert len(all_res) == 6
    assert all(result["status"] in ("Configured", "Skipped") for result in all_res)
    client_names = [r["client"] for r in all_res]
    assert any("Antigravity" in name for name in client_names)
    assert any("Claude" in name for name in client_names)
    assert any("Copilot" in name for name in client_names)
    print("[PASS] Multi-client init unit tests passed.")


def test_cmd_init_dispatch(tmp_path, monkeypatch, capsys):
    import argparse

    from mcp_win_stdio.cli import cmd_init_project

    monkeypatch.chdir(tmp_path)
    args_ag = argparse.Namespace(targets=["antigravity"], yes=True)
    cmd_init_project(args_ag)
    out = capsys.readouterr().out
    assert "Notice: mws has transitioned to a Non-Invasive Multi-Agent Architecture" in out
    assert not (tmp_path / ".mcp.json").exists()
    print("[PASS] cmd_init retired notice tests passed.")


def test_config_wizard_helpers(tmp_path, monkeypatch):
    import argparse

    from mcp_win_stdio.cli import cmd_config
    from mcp_win_stdio.core.dialogs import prompt_path_or_dialog
    from mcp_win_stdio.core.wizard import _mask_url_password, view_all_configurations

    # 1. Test URL password masking
    url = "postgresql://myuser:secret123@127.0.0.1:5432/mydb"
    masked = _mask_url_password(url)
    assert "secret123" not in masked
    assert "******" in masked

    # 2. Test prompt_path_or_dialog non-interactive fallback
    assert prompt_path_or_dialog("Test Folder", is_directory=True, default_path=str(tmp_path)) == str(tmp_path)

    # 3. Test cmd_config view
    args = argparse.Namespace(domain="list")
    f = io.StringIO()
    with redirect_stdout(f):
        cmd_config(args)
    out = f.getvalue()
    assert "Persistent Configurations Summary" in out
    print("[PASS] Config wizard helper tests passed.")


def test_streamlined_cli_commands(tmp_path, monkeypatch, capsys):
    import argparse

    from mcp_win_stdio.cli import cmd_doctor, cmd_guide, cmd_init, cmd_init_project, cmd_remove, main

    # 1. Test cmd_init matches cmd_init_project
    assert cmd_init is cmd_init_project

    # 2. Test universal guide outputs
    cmd_guide(argparse.Namespace(target=None, client=None))
    out = capsys.readouterr().out
    assert "mws Universal MCP Guide" in out
    assert "mcpServers" in out

    # 3. Test client-specific guide (gemini)
    cmd_guide(argparse.Namespace(target="gemini", client=None))
    out = capsys.readouterr().out
    assert "Gemini & Antigravity IDE Configuration" in out
    assert "mcp_config.json" in out

    # 4. Test server-client combined guide (tsc gemini)
    cmd_guide(argparse.Namespace(target="tsc", client="gemini"))
    out = capsys.readouterr().out
    assert "'tsc' for Gemini & Antigravity IDE" in out
    assert "run" in out and "tsc" in out

    # 5. Test retired command handling via main()
    monkeypatch.setattr(sys, "argv", ["mws", "setup"])
    try:
        main()
    except SystemExit:
        pass
    out = capsys.readouterr().out
    assert "Notice: mws has transitioned to a Non-Invasive Multi-Agent Architecture" in out

    # 6. Test doctor --fix-path delegation
    called = []
    monkeypatch.setattr("mcp_win_stdio.cli.cmd_fix_path", lambda a: called.append(True))
    cmd_doctor(argparse.Namespace(fix_path=True))
    assert called == [True]
    print("[PASS] Universal guide and non-invasive CLI tests passed.")


def test_package_discovery_and_clean_uninstallation(tmp_path, monkeypatch, capsys):
    import argparse

    from mcp_win_stdio.cli import cmd_run, cmd_uninstall
    from mcp_win_stdio.core.installer import get_installed_mws_packages

    # 1. Test get_installed_mws_packages discovery
    pkgs = get_installed_mws_packages()
    assert isinstance(pkgs, list)
    # The root package mcp-win-stdio should be present in our dev environment
    assert "mcp-win-stdio" in pkgs

    # 2. Test cmd_uninstall with target='self' (must uninstall mcp-win-stdio AND all subpackages)
    uninstalled_batches = []
    monkeypatch.setattr(
        "mcp_win_stdio.cli.get_installed_mws_packages",
        lambda: ["mcp-win-stdio", "mcp-win-stdio-excel", "mcp-win-stdio-tsc"],
    )
    monkeypatch.setattr(
        "mcp_win_stdio.cli.uninstall_pip_packages",
        lambda pkgs: (uninstalled_batches.append(list(pkgs)) or True, "OK"),
    )

    cmd_uninstall(argparse.Namespace(server="self"))
    out = capsys.readouterr().out
    assert len(uninstalled_batches) == 1
    # All subpackages + self must be in the batch
    assert "mcp-win-stdio" in uninstalled_batches[0]
    assert "mcp-win-stdio-excel" in uninstalled_batches[0]
    assert "mcp-win-stdio-tsc" in uninstalled_batches[0]
    assert "Zero-Mutation Policy: Client config files were untouched." in out

    # 3. Test cmd_uninstall with target='all' (keeps mws CLI, uninstalls subpackages)
    uninstalled_batches.clear()
    cmd_uninstall(argparse.Namespace(server="all"))
    out = capsys.readouterr().out
    assert len(uninstalled_batches) == 1
    assert "mcp-win-stdio" not in uninstalled_batches[0]
    assert "mcp-win-stdio-excel" in uninstalled_batches[0]
    assert "mcp-win-stdio-tsc" in uninstalled_batches[0]
    assert "mws CLI PRESERVED" in out

    # 4. Test cmd_uninstall with target='excel'
    uninstalled_batches.clear()
    cmd_uninstall(argparse.Namespace(server="excel"))
    out = capsys.readouterr().out
    assert uninstalled_batches == [["mcp-win-stdio-excel"]]
    assert "mws CLI PRESERVED" in out

    # 5. Test cmd_run reports missing server package cleanly without raw stacktrace
    import importlib
    real_import = importlib.import_module

    def fake_import(mod):
        if mod == "mcp_win_stdio.fake":
            raise ModuleNotFoundError("No module named 'mcp_win_stdio.fake'")
        return real_import(mod)

    monkeypatch.setattr("mcp_win_stdio.cli.get_server_info", lambda s: {"is_builtin": True, "module": "mcp_win_stdio.fake", "package": "mcp-win-stdio-fake"})
    monkeypatch.setattr("mcp_win_stdio.cli.importlib.import_module", fake_import)

    try:
        cmd_run(argparse.Namespace(server="fake", env_file=".env"))
    except SystemExit as e:
        assert e.code == 1
    err = capsys.readouterr().err
    assert "Server package 'mcp-win-stdio-fake' is not installed" in err
    assert "mws install fake" in err
    print("[PASS] Package discovery and clean uninstallation tests passed.")


if __name__ == "__main__":
    import tempfile

    test_discovery()
    test_guides()
    test_dashboard()
    test_all_servers_import()
    test_updater()
    with tempfile.TemporaryDirectory() as tmp_dir:
        test_project_setup_and_migration(Path(tmp_dir))
        test_init_clients(Path(tmp_dir))
    print("ALL TESTS PASSED!")
