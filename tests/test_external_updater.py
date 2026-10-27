"""
Unit tests for Windows External Updater & Uninstaller Supervisor
"""

import sys
from pathlib import Path
from mcp_win_stdio.core.external_updater import (
    get_local_appdata_dir,
    ensure_external_updater_scripts,
    ensure_external_updater_script,
    SUPERVISOR_SCRIPT_CONTENT,
)


def test_get_local_appdata_dir():
    appdata = get_local_appdata_dir()
    assert isinstance(appdata, Path)
    assert appdata.exists()
    assert appdata.name == "bin"
    assert appdata.parent.name == "mcp-win-stdio"


def test_ensure_external_updater_scripts(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    target_py = str(Path(sys.executable).resolve())
    base_py = str(Path(getattr(sys, "_base_executable", sys.executable)).resolve())

    supervisor, updater, uninstaller = ensure_external_updater_scripts(target_py, base_py)

    assert supervisor.exists()
    assert supervisor.name == "supervisor.py"
    assert updater.exists()
    assert updater.name == "mws-updater.cmd"
    assert uninstaller.exists()
    assert uninstaller.name == "mws-uninstaller.cmd"

    # Verify updater script content
    up_text = updater.read_text(encoding="utf-8")
    assert "supervisor.py" in up_text
    assert "update" in up_text
    assert '"mcp-win-stdio[all]"' in up_text

    # Verify uninstaller script content
    un_text = uninstaller.read_text(encoding="utf-8")
    assert "supervisor.py" in un_text
    assert "uninstall" in un_text
    assert '"mcp-win-stdio"' in un_text

    # Verify supervisor is stdlib-only (no mcp_win_stdio import statements)
    sup_text = supervisor.read_text(encoding="utf-8")
    assert "\nimport mcp_win_stdio" not in sup_text
    assert "\nfrom mcp_win_stdio" not in sup_text
    assert "k32.OpenProcess" in sup_text
    assert "k32.WaitForSingleObject" in sup_text


def test_ensure_external_updater_script_alias(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    alias_path = ensure_external_updater_script()
    assert alias_path.exists()
    assert alias_path.name == "mws-updater.cmd"
