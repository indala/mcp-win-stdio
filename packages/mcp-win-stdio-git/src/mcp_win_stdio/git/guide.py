"""
Usage guide, prerequisites, and prompt recipes for Git & GitHub MCP server (mcp-win-stdio-git).
"""

import shutil
import subprocess
import sys

# Ensure Windows console uses UTF-8 without crashing on cp1252
if sys.platform == "win32":
    try:
        if hasattr(sys.stdout, "reconfigure"):
            getattr(sys.stdout, "reconfigure")(encoding="utf-8", errors="replace")
        if hasattr(sys.stderr, "reconfigure"):
            getattr(sys.stderr, "reconfigure")(encoding="utf-8", errors="replace")
    except Exception:
        pass


def get_git_prerequisites_status() -> dict:
    """Check current status of git, gh, and git credential helper."""
    git_bin = shutil.which("git")
    gh_bin = shutil.which("gh")
    gh_logged_in = False
    gh_account = None
    cred_helper_linked = False

    if gh_bin:
        try:
            res = subprocess.run(
                ["gh", "auth", "status"], capture_output=True, text=True, encoding="utf-8", errors="replace"
            )
            out = res.stderr or res.stdout
            if "Logged in to" in out:
                gh_logged_in = True
                for ln in out.splitlines():
                    if "Logged in to" in ln:
                        gh_account = ln.replace("✓", "").replace("âœ“", "").strip()
                        break
        except Exception:
            pass

    if git_bin and gh_bin:
        try:
            helper_res = subprocess.run(
                ["git", "config", "--get-all", "credential.helper"], capture_output=True, text=True
            )
            if "gh" in helper_res.stdout:
                cred_helper_linked = True
        except Exception:
            pass

    return {
        "git_installed": bool(git_bin),
        "gh_installed": bool(gh_bin),
        "gh_logged_in": gh_logged_in,
        "gh_account": gh_account,
        "cred_helper_linked": cred_helper_linked,
    }


def print_git_guide() -> None:
    status = get_git_prerequisites_status()

    print("=" * 80)
    print("      Unified Git & GitHub MCP Server (mcp-win-stdio-git)")
    print("=" * 80)

    print("\nPREREQUISITES & ENVIRONMENT STATUS:")
    print("-" * 80)
    if status["git_installed"]:
        print("  [OK] Git CLI: Installed")
    else:
        print("  [!]  Git CLI: NOT FOUND")
        print("       -> Run: winget install --id Git.Git -e")

    if status["gh_installed"]:
        print("  [OK] GitHub CLI (gh): Installed")
        if status["gh_logged_in"]:
            print(f"  [OK] GitHub Auth: Logged in ({status['gh_account'] or 'Active'})")
            if status["cred_helper_linked"]:
                print("  [OK] Git Credential Helper: Linked to gh (account switching active)")
            else:
                print("  [!]  Git Credential Helper: Not linked to gh")
                print("       -> Run: gh auth setup-git")
                print("          (Required so git commands & account switching use gh authentication)")
        else:
            print("  [!]  GitHub Auth: Not logged in")
            print("       -> Step 1: gh auth login")
            print("       -> Step 2: gh auth setup-git  (essential for git operations & account switching)")
    else:
        print("  [!]  GitHub CLI (gh): NOT FOUND (Required for PRs, issues, gists & CI runs)")
        print("       -> Step 1: winget install --id GitHub.cli -e")
        print("       -> Step 2: gh auth login")
        print("       -> Step 3: gh auth setup-git  (essential for git operations & account switching)")

    print("\nSETUP INSTRUCTIONS FOR NEW USERS:")
    print("-" * 80)
    print("  1. If Git or gh is not installed, install them using winget:")
    print("     winget install --id Git.Git -e")
    print("     winget install --id GitHub.cli -e")
    print("\n  2. Authenticate GitHub CLI:")
    print("     gh auth login")
    print("\n  3. Configure Git to use GitHub CLI credentials (CRUCIAL):")
    print("     gh auth setup-git")
    print("     * Why this is needed: Configures git credential.helper = '!gh auth git-credential'.")
    print("       Without this, local git push/pull and multi-account switching ('gh auth switch')")
    print("       will fail or fallback to outdated Windows credentials.")
    print("\n  4. Register with Claude Desktop or Claude Code CLI:")
    print("     mws add git")

    print("\nAVAILABLE TOOLS (26 Tools):")
    print("-" * 80)
    print(" Local Git Operations:")
    print("   * repo_overview        : 360-degree repo overview: branch, dirty state, PR, latest CI")
    print("   * use_repo             : Switch active repository workspace bookmark")
    print("   * list_repos           : List registered repository workspaces")
    print("   * add_repo             : Bookmark a repository path for multi-project workflows")
    print("   * git_status           : Structured status: staged, unstaged, untracked files")
    print("   * git_diff             : Token-safe diff (unstaged, staged index, branch comparisons)")
    print("   * git_log              : Structured commit history with hash, author, date, message")
    print("   * git_commit           : Stage and commit files with clean commit messages")
    print("   * git_branch           : List, create, switch, or safely delete branches")
    print("   * git_stash            : Stash changes: save, pop, list, drop")
    print("   * git_sync             : Fetch, pull, push with upstream tracking")
    print("   * git_blame            : Token-safe file blame with line range filtering")
    print("   * git_reset            : Safe file restore or commit reset (soft or guarded hard)")
    print("   * git_tag              : List, create, or delete Git tags")
    print("   * git_grep             : Fast regex search across tracked files")
    print("   * git_worktree         : Isolated branch workspaces: list, add, remove, prune")
    print("   * git_config           : Inspect or configure git settings (user.name, user.email)")
    print("   * git_conflict_resolve : Detect merge/rebase conflicts, abort, or continue")
    print("\n Remote GitHub Operations (via gh CLI):")
    print("   * gh_auth_status       : Check GitHub CLI authentication status and accounts")
    print("   * gh_switch_account    : Switch active GitHub account (personal vs work)")
    print("   * gh_pr_list           : List pull requests with state filters")
    print("   * gh_pr_view           : Deep view of PR: reviews, CI checks, mergeable state")
    print("   * gh_pr_diff           : View token-capped remote PR diff")
    print("   * gh_issue_list        : List repository issues with label/state filters")
    print("   * gh_run_status        : Inspect recent GitHub Actions workflow runs")
    print("   * gh_gist_create       : Share code snippets via GitHub Gists")
    print("\n Hybrid Synergy Workflows:")
    print("   * pr_quickstart        : Stage -> Commit -> Push -> Create PR via 'gh pr create'")
    print("   * issue_start_work     : Fetch issue from GitHub -> Checkout feature branch locally")

    print("\nPROMPT RECIPES FOR CLAUDE:")
    print("-" * 80)
    print("  1. 'Give me a 360-degree overview of the current repo, open PRs, and recent CI runs using repo_overview.'")
    print("  2. 'Pick up issue #12, check its details, and create a local branch using issue_start_work.'")
    print(
        "  3. 'Stage all modified files, commit with message \"feat: new feature\", push, and open a PR with pr_quickstart.'"
    )
    print("  4. 'Switch active GitHub account to my work account using gh_switch_account.'")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    print_git_guide()
