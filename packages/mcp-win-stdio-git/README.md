# mcp-win-stdio-git

Unified Git & GitHub Model Context Protocol (MCP) server for Windows & Claude Desktop: **26 tools** seamlessly unifying local Git repository management and remote GitHub CLI (`gh`) operations with hybrid synergy workflows.

Part of the **`mcp-win-stdio`** Windows-optimized suite.

---

## 🚀 Features

- **Local Git Suite (14 Tools)**:
  - Branch management (`git_branch`), staging & commits with identity checks (`git_commit`), token-safe diffs (`git_diff`), commit logs (`git_log`), stashing (`git_stash`), remote sync (`git_sync`), blame (`git_blame`), tags (`git_tag`), and regex search (`git_grep`).
  - Safe restoration and guarded destructive reset (`git_reset`).
  - Isolated background workspaces via `git_worktree`.
  - In-progress merge and rebase conflict detection & resolution (`git_conflict_resolve`).
- **Remote GitHub CLI Suite (10 Tools)**:
  - Pull requests (`gh_pr_list`, `gh_pr_view`, `gh_pr_diff`, `gh_pr_checkout`, `gh_pr_action` for merge/close/reopen).
  - Issue tracking (`gh_issue_list`, `gh_issue_view`, `gh_issue_create`, `gh_issue_comment`).
  - CI/CD workflow monitoring (`gh_run_status`).
  - Gist snippet creation (`gh_gist_create`) and global GitHub search (`gh_search`).
  - Multi-account awareness and switching (`gh_auth_status`, `gh_switch_account`).
- **Hybrid Synergy Tools**:
  - `repo_overview`: 360-degree status combining local branch, dirty status, ahead/behind tracking, active open PR, and latest GitHub Actions workflow run.
  - `pr_quickstart`: Stage -> commit -> push -> open GitHub PR in a single tool call.
  - `issue_start_work`: Fetches GitHub issue details and automatically checks out a linked feature branch `feature/<id>-<slug>`.
- **Zero-Friction Fallback**:
  - Works 100% locally if GitHub CLI is not installed or unauthenticated, and provides copy-pasteable `winget` commands to install.

---

## 📦 Quick Start

### 1. Installation
```powershell
pip install mcp-win-stdio-git
# or with the full suite:
pip install mcp-win-stdio[git]
```

### 2. Check Health & Dependencies
```powershell
mws-git doctor
```

### 3. Claude Desktop Configuration
```json
"git": {
  "command": "python",
  "args": ["-m", "mcp_win_stdio.git"]
}
```

### 4. Claude Code CLI Command
```powershell
claude mcp add -s user git -- "python" -m mcp_win_stdio.git
```
