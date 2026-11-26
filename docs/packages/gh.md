# `gh (GitHub CLI)`

> Official GitHub CLI used for PRs, issues, CI workflow runs, releases, gists, code search, and GitHub API requests.

## Tool Metadata

| Property | Details |
| :--- | :--- |
| **Category** | External CLI & Binary |
| **Install / Prerequisite** | `winget install --id GitHub.cli -e` |
| **Used By (`mcp-win-stdio`)** | `packages/mcp-win-stdio-git/src/mcp_win_stdio/git/server.py`, `cli.py`, `guide.py`, `src/mcp_win_stdio/cli.py` |

## Subcommands, Flags & Environment Variables

| Function Name / Variable | Attributes & Description |
| :--- | :--- |
| `gh auth status` / `gh auth switch` | `subcommand` · Check GitHub login status and switch accounts (`gh_auth_status`, `gh_switch_account`). |
| `gh pr list` / `view` / `diff` / `checkout` | `subcommand` · Inspect and check out Pull Requests (`gh_pr_list`, `gh_pr_view`, `gh_pr_diff`, `gh_pr_checkout`). |
| `gh pr create` / `review` / `merge` / `close` / `reopen` | `subcommand` · Create PRs (`pr_quickstart`) and run lifecycle actions (`gh_pr_action`). |
| `gh pr checks [--watch]` | `subcommand` · Inspect CI/CD check runs and status for a PR (`gh_pr_checks`). |
| `gh issue list` / `view` / `create` / `comment` | `subcommand` · Manage GitHub issues (`gh_issue_list`, `gh_issue_view`, `gh_issue_create`, `gh_issue_comment`, `issue_start_work`). |
| `gh run list` / `gh run view` | `subcommand` · Inspect GitHub Actions workflow runs (`gh_run_status`, `repo_overview`). |
| `gh release list` / `gh release create` | `subcommand` · List and publish releases (`gh_release_list`, `gh_release_create`). |
| `gh gist create` | `subcommand` · Create public/secret GitHub gists (`gh_gist_create`). |
| `gh search` | `subcommand` · Search GitHub repos, issues, PRs, and code (`gh_search`). |
| `gh api <endpoint>` | `subcommand` · Authenticated REST/GraphQL GitHub API calls (`gh_api`, `gh_pr_review_comments`). |
| `GH_PROMPT_DISABLED=1` | `env variable` · Set by `run_gh_command()` to enforce non-interactive execution. |
