# mcp-win-stdio-git

Unified Git & GitHub Model Context Protocol (MCP) server for Windows & Claude Desktop: **33 tools** seamlessly unifying local Git repository management and remote GitHub CLI (`gh`) operations with hybrid synergy workflows.

Part of the **`mcp-win-stdio`** Windows-optimized suite.

---

## 🚀 Features (33 Tools)

- **Local Git Suite (20 Tools)**:
  - Repository initialization (`git_init`) and bookmark management (`use_repo`, `list_repos`, `add_repo`, `remove_repo`, `rename_alias`).
  - Remotes management (`git_remote`: list, add, set-url, remove, get-url).
  - Safe file restoration (`git_restore`) and guarded destructive reset (`git_reset`).
  - Branching (`git_branch`), staging & commits with untracked safeguards (`git_commit`), paginated chunked diffs (`git_diff`), commit logs (`git_log`), stashing (`git_stash`), remote sync (`git_sync`), blame (`git_blame`), tags (`git_tag`), cherry-pick (`git_cherry_pick`), clean (`git_clean_untracked`), regex search (`git_grep`), and config (`git_config`).
  - Isolated background workspaces via `git_worktree`.
  - In-progress merge and rebase conflict detection & resolution (`git_conflict_resolve`).
- **Remote GitHub CLI Suite (10 Tools)**:
  - Pull requests (`gh_pr_list`, `gh_pr_view`, `gh_pr_diff`, `gh_pr_checkout`, `gh_pr_action`, `gh_pr_checks`, `gh_pr_review_comments`).
  - Releases (`gh_release_list`, `gh_release_create`).
  - Issue tracking (`gh_issue_list`, `gh_issue_view`, `gh_issue_create`, `gh_issue_comment`).
  - CI/CD workflow monitoring (`gh_run_status`).
  - Global search (`gh_search`) and direct API caller (`gh_api`).
  - Gist snippet creation (`gh_gist_create`).
  - Multi-account awareness and switching (`gh_auth_status`, `gh_switch_account`).
- **Hybrid Synergy Workflows (3 Tools)**:
  - `repo_overview`: 360-degree status combining local branch, dirty status, ahead/behind tracking, active open PR, and latest GitHub Actions workflow run.
  - `pr_quickstart`: Stage -> commit -> push -> open GitHub PR via `gh pr create` in a single tool call.
  - `issue_start_work`: Fetches GitHub issue details and automatically checks out a linked feature branch `feature/<id>-<slug>`.
- **Zero-Friction Fallback**:
  - Works 100% locally if GitHub CLI is not installed or unauthenticated, and provides copy-pasteable `winget` commands to install.


---

## 📋 Prerequisites & Setup

1. **Install Git CLI** (if not installed):
   ```powershell
   winget install --id Git.Git -e
   ```

2. **Install GitHub CLI** (recommended for PRs, Issues, Actions):
   ```powershell
   winget install --id GitHub.cli -e
   ```

3. **Authenticate & Setup Git Credential Helper**:
   ```powershell
   gh auth login
   gh auth setup-git
   ```
   > [!IMPORTANT]
   > `gh auth setup-git` is crucial so your local git push/pull and multi-account switching (`gh_switch_account`) authenticate smoothly.

---

## 📦 Installation

```powershell
pip install mcp-win-stdio-git
```
*(Installing this package automatically installs `mws` CLI orchestrator)*.

---

## 🚀 One-Command Claude Setup

```powershell
mws setup git
# or:
mws add git
```
This automatically configures Claude Desktop (`claude_desktop_config.json`) and Claude Code CLI with zero manual JSON editing.

### Manual Configuration
```json
"git": {
  "command": "python",
  "args": ["-m", "mcp_win_stdio.git"]
}
```

---

## 📖 CLI Commands & Interactive Guide

```powershell
mws git guide      # Complete tool reference & prompt recipes
mws git doctor     # Verify Git, GitHub CLI, and credential helper status
mws git setup      # Configure Claude Desktop / Claude Code
mws git run        # Launch server over stdio
```

---

## 📜 License
MIT License. Copyright (c) 2026 Mohan Kumar Indala.
