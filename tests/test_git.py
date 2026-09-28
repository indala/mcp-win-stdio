"""
Unit and integration tests for mcp-win-stdio Git & GitHub MCP server.
"""

import os
import sys
sys.path.insert(0, os.path.abspath("src"))

from pathlib import Path
import shutil
import subprocess
import tempfile

from mcp_win_stdio.git.server import (
    is_git_installed,
    is_gh_installed,
    get_git_missing_guidance,
    get_gh_missing_guidance,
    _truncate_output,
    _filter_git_output,
    resolve_repo_path,
    find_git_root,
    use_repo,
    list_repos,
    add_repo,
    repo_overview,
    git_status,
    git_commit,
    git_log,
    git_diff,
    git_branch,
    git_tag,
    git_grep,
    git_config,
    git_conflict_resolve,
    gh_auth_status,
)


def test_dependency_checkers():
    assert is_git_installed() is True
    git_guide = get_git_missing_guidance()
    assert git_guide["status"] == "tool_unavailable"
    assert "winget install --id Git.Git -e" in str(git_guide)

    gh_guide = get_gh_missing_guidance()
    assert gh_guide["status"] == "tool_unavailable"
    assert "winget install --id GitHub.cli -e" in str(gh_guide)
    print("[PASS] test_dependency_checkers passed.")


def test_output_capping_and_filter():
    long_diff = "\n".join([f"+ line {i}" for i in range(500)])
    capped = _truncate_output(long_diff, max_lines=100)
    assert capped["truncated"] is True
    assert capped["returned_lines"] == 100
    assert capped["total_lines"] == 500
    assert "[Output capped:" in capped["notice"]

    crlf_warning = "warning: in the working copy of 'foo.txt', LF will be replaced by CRLF the next time Git touches it\nactual content"
    filtered = _filter_git_output(crlf_warning)
    assert "LF will be replaced" not in filtered
    assert "actual content" in filtered
    print("[PASS] test_output_capping_and_filter passed.")


def test_local_git_operations():
    # Create isolated temp repo
    with tempfile.TemporaryDirectory() as tmp_dir:
        repo_dir = Path(tmp_dir)

        # 1. Init git repo
        subprocess.run(["git", "init"], cwd=str(repo_dir), check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test Runner"], cwd=str(repo_dir), check=True)
        subprocess.run(["git", "config", "user.email", "test@runner.local"], cwd=str(repo_dir), check=True)

        # 2. Test status on empty repo
        status_res = git_status(repo_path=str(repo_dir))
        assert status_res["success"] is True
        assert status_res["clean"] is True

        # 3. Create a file and verify untracked
        test_file = repo_dir / "sample.py"
        test_file.write_text("print('hello world')\n", encoding="utf-8")

        status_res2 = git_status(repo_path=str(repo_dir))
        assert status_res2["clean"] is False
        assert "sample.py" in status_res2["untracked"]

        # 4. Commit file
        commit_res = git_commit(
            message="initial commit",
            files=["sample.py"],
            repo_path=str(repo_dir)
        )
        assert commit_res["success"] is True

        # 5. Log verification
        log_res = git_log(repo_path=str(repo_dir))
        assert log_res["success"] is True
        assert log_res["count"] == 1
        assert log_res["commits"][0]["subject"] == "initial commit"
        assert log_res["commits"][0]["author"] == "Test Runner"

        # 6. Branch creation & listing
        b_res = git_branch(action="create", branch_name="feature/test-branch", repo_path=str(repo_dir))
        assert b_res["success"] is True

        list_b = git_branch(action="list", repo_path=str(repo_dir))
        assert list_b["success"] is True
        names = [b["name"] for b in list_b["branches"]]
        assert "feature/test-branch" in names

        # 7. Modify file and check git diff
        test_file.write_text("print('hello world modified')\n", encoding="utf-8")
        diff_res = git_diff(repo_path=str(repo_dir))
        assert diff_res["success"] is True
        assert "hello world modified" in diff_res["diff"]

        # 8. Git grep
        grep_res = git_grep(pattern="hello", repo_path=str(repo_dir))
        assert grep_res["success"] is True
        assert grep_res["total_found"] >= 1

        # 9. Git tags
        tag_res = git_tag(action="create", tag_name="v1.0.0", message="first release", repo_path=str(repo_dir))
        assert tag_res["success"] is True
        tags_list = git_tag(action="list", repo_path=str(repo_dir))
        assert "v1.0.0" in tags_list["tags"]

        # 10. Conflict detection status
        conf_res = git_conflict_resolve(action="status", repo_path=str(repo_dir))
        assert conf_res["success"] is True
        assert conf_res["in_conflict"] is False

        # 11. Repo overview (gracefully handles non-GitHub repo)
        ov_res = repo_overview(repo_path=str(repo_dir))
        assert ov_res["branch"] == "feature/test-branch"
        assert ov_res["is_dirty"] is True
        assert "in_progress_state" in ov_res

    print("[PASS] test_local_git_operations passed.")


def test_auth_status():
    if is_gh_installed():
        res = gh_auth_status()
        assert "raw_status" in res
        print(f"[PASS] test_auth_status passed (Logged in: {res.get('is_logged_in')}).")
    else:
        print("[SKIP] gh not installed, skipping gh_auth_status.")


if __name__ == "__main__":
    test_dependency_checkers()
    test_output_capping_and_filter()
    test_local_git_operations()
    test_auth_status()
    print("\nAll Git MCP tests passed successfully!")
