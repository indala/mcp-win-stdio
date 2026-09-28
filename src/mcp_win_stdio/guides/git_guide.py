"""
Usage guide and prompt recipes for Git & GitHub MCP server (mcp-win-stdio.git).
"""

def print_git_guide() -> None:
    guide_text = """
================================================================================
           Unified Git & GitHub MCP Server (mcp-win-stdio.git)
================================================================================

Description:
  Unified Model Context Protocol server for local Git repository management
  and remote GitHub CLI (gh) operations.
  Features seamless workspace switching, token-safe diffs and logs,
  Windows CRLF filtering, and hybrid synergy workflows.

Available Tools (26 Tools):
--------------------------------------------------------------------------------
1.  repo_overview
    - Unified 360-degree repository status: local branch, dirty status, ahead/behind
      tracking, associated open PR, and latest GitHub Actions workflow run.
    - Args: repo_path (optional str)

2.  use_repo
    - Switches active repository workspace. Auto-detects from cwd if not specified.
    - Args: repo_path (optional str)

3.  list_repos
    - Lists registered repository bookmarks, active repo, and status.

4.  add_repo
    - Bookmarks a repository path for multi-project workflows.
    - Args: repo_path (str), alias (optional str)

5.  pr_quickstart
    - All-in-one flow: stage -> commit -> push -> open PR via 'gh pr create'.
    - Args: title (str), body (optional str), branch (optional str), files (optional list), draft (optional bool)

6.  issue_start_work
    - Fetches issue from GitHub, creates and checks out a feature branch locally.
    - Args: issue_number (int), branch_prefix (optional str: 'feature', 'fix')

7.  git_status
    - Structured status showing staged, unstaged, untracked files, and in-progress states.
    - Args: repo_path (optional str)

8.  git_diff
    - Token-safe diff (unstaged, staged index, or branch-to-branch).
    - Args: staged (bool), target (optional str), path (optional str), max_lines (int)

9.  git_log
    - Structured commit history with hash, author, relative date, and subject.
    - Args: max_count (int), branch (optional str), path (optional str)

10. git_commit
    - Stage files and commit with a clean message. Checks git author identity.
    - Args: message (str), files (optional list), all_modified (bool)

11. git_branch
    - List, create, switch, or safely delete branches.
    - Args: action (str: 'list', 'create', 'switch', 'delete'), branch_name (optional str)

12. git_stash
    - Stash changes: save, pop, list, drop.
    - Args: action (str: 'list', 'save', 'pop', 'drop'), message (optional str), index (int)

13. git_sync
    - Remote synchronization: fetch, pull, push with upstream tracking.
    - Args: action (str: 'fetch', 'pull', 'push'), remote (str), branch (optional str), set_upstream (bool)

14. git_blame
    - Token-safe file blame with line range filtering.
    - Args: file_path (str), start_line (optional int), end_line (optional int)

15. git_reset
    - Safe file restore or commit reset (soft or guarded hard reset).
    - Args: mode (str: 'restore', 'soft', 'hard'), files (optional list), confirm_destructive (bool)

16. git_tag
    - List, create, or delete Git tags.
    - Args: action (str: 'list', 'create', 'delete'), tag_name (optional str), message (optional str)

17. git_grep
    - Fast regex pattern search across tracked repository files.
    - Args: pattern (str), path_spec (optional str), ignore_case (bool), max_results (int)

18. git_worktree
    - Isolated branch workspaces: list, add, remove, prune.
    - Args: action (str: 'list', 'add', 'remove', 'prune'), path (optional str), branch (optional str)

19. git_config
    - Inspect or set git config (user.name, user.email, core.autocrlf).
    - Args: action (str: 'get', 'set'), key (optional str), value (optional str), scope (str)

20. git_conflict_resolve
    - Detect merge/rebase conflicts, abort, or continue.
    - Args: action (str: 'status', 'abort', 'continue')

21. gh_auth_status
    - Check GitHub CLI authentication status and scopes.

22. gh_pr_list
    - List pull requests with state filters (open, closed, merged).
    - Args: state (str), limit (int)

23. gh_pr_view
    - View full PR details including reviews, CI checks, and mergeable state.
    - Args: pr_number (int)

24. gh_pr_diff
    - View token-capped remote PR diff.
    - Args: pr_number (int), max_lines (int)

25. gh_issue_list
    - List issues with labels, state, and assignee filters.
    - Args: state (str), limit (int), assignee (optional str), labels (optional list)

26. gh_run_status
    - Inspect recent GitHub Actions CI/CD runs and results.
    - Args: limit (int)

================================================================================
💡 Prompt Recipes for Claude Desktop & Claude Code CLI:
================================================================================

1. Repository Health Check:
   "Give me a 360-degree overview of the current repo, open PRs, and recent CI runs using repo_overview."

2. Issue-Driven Development:
   "Pick up GitHub issue #12, inspect its requirements, and create a local branch using issue_start_work."

3. Quick Ship / PR Creation:
   "Stage all changes, commit with message 'feat: add git mcp', push, and open a PR using pr_quickstart."

4. Conflict Investigation:
   "Check if there are any merge or rebase conflicts using git_conflict_resolve."
"""
    print(guide_text)
