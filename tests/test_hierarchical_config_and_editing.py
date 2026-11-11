"""
Tests for hierarchical configuration (mws config) and safe file editing tools (replace_in_file, write_file).
"""

import json
import os
import shutil
import tempfile
from pathlib import Path

import pytest
from mcp_win_stdio.explorer.server import replace_in_file, write_file

from mcp_win_stdio.core.config import (
    CONFIG_FILE,
    find_workspace_dir,
    get_effective_mode,
    get_workspace_config_path,
    is_require_confirm_on_prod_enabled,
    is_safe_writes_enabled,
    load_config,
    load_hierarchical_config,
    load_workspace_config,
    save_config,
)


def test_hierarchical_config_precedence(tmp_path):
    """Verify that workspace config overrides global config without mutating global."""
    ws_dir = tmp_path / "my_project"
    ws_dir.mkdir()
    ws_mws = ws_dir / ".mws"
    ws_mws.mkdir()
    ws_cfg_file = ws_mws / "config.json"

    # Workspace config sets mode to read_only and disables safe_writes
    ws_data = {
        "mode": "read_only",
        "safe_writes": False,
        "custom_project_flag": "alpha",
    }
    ws_cfg_file.write_text(json.dumps(ws_data), encoding="utf-8")

    # Load hierarchical
    cfg = load_hierarchical_config(workspace_dir=ws_dir)
    assert cfg["mode"] == "read_only"
    assert cfg["safe_writes"] is False
    assert cfg["custom_project_flag"] == "alpha"
    assert cfg["_resolved_sources"]["workspace_active"] is True
    assert cfg["_resolved_sources"]["workspace_path"] == str(ws_cfg_file)

    assert get_effective_mode(workspace_dir=ws_dir) == "read_only"
    assert is_safe_writes_enabled(workspace_dir=ws_dir) is False


def test_config_save_scopes(tmp_path):
    """Test saving to workspace vs global scopes."""
    ws_dir = tmp_path / "test_scope_ws"
    ws_dir.mkdir()

    # Save to workspace
    ws_saved = save_config({"mode": "read_write", "foo": "bar"}, scope="workspace", workspace_dir=ws_dir)
    assert ws_saved.exists()
    assert (ws_dir / ".mws" / "config.json").exists()

    ws_loaded = load_workspace_config(workspace_dir=ws_dir)
    assert ws_loaded.get("foo") == "bar"


def test_safe_file_write_and_replace(tmp_path):
    """Test write_file safeguards and replace_in_file precision and diff output."""
    target_file = tmp_path / "sample_service.ts"

    # 1. Create file with write_file
    initial_code = (
        "export class InventoryService {\n"
        "  async getAllProps() {\n"
        "    return this.db.query('SELECT * FROM props');\n"
        "  }\n"
        "}\n"
    )
    res_write = write_file(str(target_file), content=initial_code)
    assert res_write.get("success") is True
    assert target_file.exists()

    # 2. Prevent accidental overwrite without overwrite=True
    res_err = write_file(str(target_file), content="new text")
    assert "error" in res_err
    assert "already exists" in res_err["error"]

    # 3. Allow overwrite with overwrite=True
    res_ow = write_file(str(target_file), content=initial_code, overwrite=True)
    assert res_ow.get("success") is True

    # 4. Safe replace_in_file
    target_snippet = "    return this.db.query('SELECT * FROM props');"
    replacement_snippet = (
        "    // Carrier stock branch\n"
        "    return this.db.query('SELECT * FROM props JOIN carriers ON ...');"
    )

    res_replace = replace_in_file(str(target_file), target=target_snippet, replacement=replacement_snippet)
    assert res_replace.get("success") is True
    assert res_replace["replacements_made"] == 1
    assert "Carrier stock branch" in res_replace["diff"]

    updated_text = target_file.read_text(encoding="utf-8")
    assert "Carrier stock branch" in updated_text
    assert "SELECT * FROM props';" not in updated_text

    # 5. Non-matching target error
    res_not_found = replace_in_file(str(target_file), target="NON_EXISTENT_STRING", replacement="new")
    assert "error" in res_not_found
    assert "not found" in res_not_found["error"]


def test_replace_in_file_duplicate_rejection(tmp_path):
    """Test that ambiguous multiple occurrences are rejected to prevent corrupting code."""
    file_path = tmp_path / "duplicate_test.txt"
    file_path.write_text("item: 123\nitem: 123\n", encoding="utf-8")

    res = replace_in_file(str(file_path), target="item: 123", replacement="item: 456")
    assert "error" in res
    assert "matched 2 times" in res["error"]
