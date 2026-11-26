# `git (Git CLI)`

> Local Git CLI used for repository inspection, diffs, commits, branching, stashing, worktrees, blame, and repo status.

## Tool Metadata

| Property | Details |
| :--- | :--- |
| **Category** | External CLI & Binary |
| **Install / Prerequisite** | `winget install --id Git.Git -e` |
| **Used By (`mcp-win-stdio`)** | `packages/mcp-win-stdio-git/`, `packages/mcp-win-stdio-explorer/src/mcp_win_stdio/explorer/server.py`, `src/mcp_win_stdio/cli.py` |

## Subcommands, Flags & Environment Variables

| Function Name / Variable | Attributes & Description |
| :--- | :--- |
| `git init [-b <branch>]` | `subcommand` · Initialize repository (with `initial_branch` in `git_init`). |
| `git status [--porcelain]` | `subcommand` · Show working tree status; `--porcelain` is parsed by `git_status` & `workspace_summary`. |
| `git diff [--staged] [<target>] [-- <paths>]` | `subcommand` · Compute working tree, staged, or branch/commit diffs (`git_diff`). |
| `git log [-n <max_count>] [--format=...]` | `subcommand` · Structured commit history (`git_log`). |
| `git add` / `git commit -m <msg>` | `subcommand` · Stage files and create commits (`git_commit`, `pr_quickstart`). |
| `git branch` / `git switch` / `git checkout` | `subcommand` · List, create, switch, and delete branches (`git_branch`, `issue_start_work`). |
| `git stash [push\|pop\|list\|drop\|clear]` | `subcommand` · Save and restore dirty working tree state (`git_stash`). |
| `git fetch` / `git pull` / `git push [-u]` | `subcommand` · Sync local branches with remotes (`git_sync`, `pr_quickstart`). |
| `git restore [--staged] [--source=<ref>]` | `subcommand` · Discard working tree edits or unstage files (`git_restore`, `git_reset`). |
| `git reset [--soft\|--mixed\|--hard] <target>` | `subcommand` · Move `HEAD` / reset index (`git_reset`). |
| `git blame [-L <start>,<end>] <file>` | `subcommand` · Line-by-line commit attribution (`git_blame`). |
| `git tag` / `git remote` / `git worktree` | `subcommand` · Manage tags (`git_tag`), remotes (`git_remote`), and isolated worktrees (`git_worktree`). |
| `git grep [-n] [-i] <pattern>` | `subcommand` · Regex search across tracked files (`git_grep`). |
| `git config [--global\|--local\|--system]` | `subcommand` · Read/write `user.name`, `user.email`, `credential.helper`, etc. |
| `git cherry-pick` / `git merge` / `git rebase` / `git clean` | `subcommand` · Apply commits (`git_cherry_pick`), manage conflicts (`git_conflict_resolve`), clean untracked (`git_clean_untracked`). |
| `GIT_TERMINAL_PROMPT=0` | `env variable` · Set by `run_git_command()` to disable interactive credential/password prompts. |
