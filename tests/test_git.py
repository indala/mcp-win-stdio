"""
Unit and integration tests for mcp-win-stdio Git & GitHub MCP server.
"""

import os
import sys
from pathlib import Path

for p in Path("packages").glob("*/src"):
    sys.path.insert(0, str(p.resolve()))
sys.path.insert(0, os.path.abspath("src"))
import subprocess
import tempfile

from mcp_win_stdio.git.server import (
    _filter_git_output,
    _truncate_output,
    get_gh_missing_guidance,
    get_git_missing_guidance,
    gh_auth_status,
    git_branch,
    git_commit,
    git_conflict_resolve,
    git_diff,
    git_grep,
    git_init,
    git_log,
    git_remote,
    git_restore,
    git_status,
    git_tag,
    is_gh_installed,
    is_git_installed,
    list_repos,
    remove_repo,
    rename_alias,
    repo_overview,
    use_repo,
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


def test_alias_resolution_and_init():
    with tempfile.TemporaryDirectory() as tmp_dir:
        repo_dir = Path(tmp_dir) / "test_project"

        # Test git_init
        init_res = git_init(repo_path=str(repo_dir), initial_branch="main", alias="test_alias")
        assert init_res["success"] is True
        assert init_res["initial_branch"] == "main"
        assert (repo_dir / ".git").exists()

        # Test alias resolution in use_repo
        use_res = use_repo(repo_path="test_alias")
        assert use_res["success"] is True
        assert use_res["name"] == "test_project"

        # Test alias resolution in git_status
        status_res = git_status(repo_path="test_alias")
        assert status_res["success"] is True
        assert status_res["clean"] is True

        # Test git_remote
        rem_add = git_remote(
            action="add", name="origin", url="https://github.com/test/repo.git", repo_path="test_alias"
        )
        assert rem_add["success"] is True

        rem_list = git_remote(action="list", repo_path="test_alias")
        assert rem_list["success"] is True
        assert "origin" in rem_list["remotes"]

        rem_get = git_remote(action="get-url", name="origin", repo_path="test_alias")
        assert rem_get["success"] is True
        assert "github.com/test/repo.git" in rem_get["url"]

    print("[PASS] test_alias_resolution_and_init passed.")


def test_local_git_operations():
    # Create isolated temp repo
    with tempfile.TemporaryDirectory() as tmp_dir:
        repo_dir = Path(tmp_dir)

        # 1. Init git repo
        subprocess.run(["git", "init", "-b", "main"], cwd=str(repo_dir), check=True, capture_output=True)
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

        # 4. Commit with include_untracked
        commit_res = git_commit(message="initial commit", include_untracked=True, repo_path=str(repo_dir))
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

        # 7. Modify file and check git diff with pagination
        test_file.write_text(
            "print('hello world modified')\n" + "\n".join([f"# line {i}" for i in range(100)]), encoding="utf-8"
        )
        diff_res = git_diff(offset_lines=0, max_lines=20, repo_path=str(repo_dir))
        assert diff_res["success"] is True
        assert diff_res["returned_lines"] == 20
        assert diff_res["has_more"] is True
        assert diff_res["next_offset"] == 20

        # Next chunk
        diff_chunk2 = git_diff(offset_lines=20, max_lines=20, repo_path=str(repo_dir))
        assert diff_chunk2["success"] is True
        assert diff_chunk2["offset_lines"] == 20

        # 8. Test git_restore
        restore_res = git_restore(files=["sample.py"], repo_path=str(repo_dir))
        assert restore_res["success"] is True
        assert "hello world modified" not in test_file.read_text(encoding="utf-8")

        # 9. Git grep
        grep_res = git_grep(pattern="hello", repo_path=str(repo_dir))
        assert grep_res["success"] is True
        assert grep_res["total_found"] >= 1

        # 10. Git tags
        tag_res = git_tag(action="create", tag_name="v1.0.0", message="first release", repo_path=str(repo_dir))
        assert tag_res["success"] is True
        tags_list = git_tag(action="list", repo_path=str(repo_dir))
        assert "v1.0.0" in tags_list["tags"]

        # 11. Conflict detection status
        conf_res = git_conflict_resolve(action="status", repo_path=str(repo_dir))
        assert conf_res["success"] is True
        assert conf_res["in_conflict"] is False

        # 12. Repo overview (gracefully handles non-GitHub repo)
        ov_res = repo_overview(repo_path=str(repo_dir))
        assert ov_res["branch"] == "feature/test-branch"
        assert "in_progress_state" in ov_res

    print("[PASS] test_local_git_operations passed.")


def test_bookmark_management():
    with tempfile.TemporaryDirectory() as tmp_dir:
        repo1 = Path(tmp_dir) / "repo1"
        repo2 = Path(tmp_dir) / "repo2"
        git_init(repo_path=str(repo1), alias="alias1")
        git_init(repo_path=str(repo2), alias="alias2")

        # Verify both registered
        list_res = list_repos()
        aliases = [r["alias"] for r in list_res["repositories"]]
        assert "alias1" in aliases
        assert "alias2" in aliases

        # Test rename_alias
        ren_res = rename_alias(old_alias="alias1", new_alias="alias-renamed")
        assert ren_res["success"] is True
        assert ren_res["old_alias"] == "alias1"
        assert ren_res["new_alias"] == "alias-renamed"

        # Verify renaming reflected in list_repos
        list_res2 = list_repos()
        aliases2 = [r["alias"] for r in list_res2["repositories"]]
        assert "alias1" not in aliases2
        assert "alias-renamed" in aliases2

        # Test use_repo with renamed alias
        use_res = use_repo(repo_path="alias-renamed")
        assert use_res["success"] is True
        assert use_res["name"] == "repo1"

        # Test remove_repo
        rem_res = remove_repo(alias_or_path="alias-renamed")
        assert rem_res["success"] is True
        assert rem_res["removed_alias"] == "alias-renamed"

        # Verify removal reflected
        list_res3 = list_repos()
        aliases3 = [r["alias"] for r in list_res3["repositories"]]
        assert "alias-renamed" not in aliases3

        # Clean up alias2
        remove_repo(alias_or_path="alias2")

    print("[PASS] test_bookmark_management passed.")


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
    test_alias_resolution_and_init()
    test_bookmark_management()
    test_local_git_operations()
    test_auth_status()
    print("\nAll Git MCP tests passed successfully!")
