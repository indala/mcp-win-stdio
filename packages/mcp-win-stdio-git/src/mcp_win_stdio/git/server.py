#!/usr/bin/env python3
"""
Unified Git & GitHub MCP Server for mcp-win-stdio.
Combines local Git repository management with remote GitHub CLI (gh) operations,
providing seamless repository switching, bookmark alias resolution, hybrid synergy workflows,
token-safe truncation, Windows CRLF filtering, and tiered fallback guidance.
"""

import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from typing import Any, Dict, List, Literal, Optional, Union

try:
    from mcp.server.mcpserver import MCPServer as FastMCP
except (ImportError, ModuleNotFoundError):
    from mcp.server.fastmcp import FastMCP

from mcp_win_stdio.core.config import INDALA_DIR, ensure_workspace_dirs

mcp = FastMCP("git-mcp")

# Persistent repository bookmarks
GIT_CONFIG_DIR = INDALA_DIR
REPOS_CONFIG_FILE = GIT_CONFIG_DIR / "git_repos.json"

_ACTIVE_REPO: Optional[Path] = None


# ==============================================================================
# Dependency Checkers & Tiered Guidance
# ==============================================================================

def is_git_installed() -> bool:
    """Check if 'git' is accessible on PATH."""
    return shutil.which("git") is not None


def is_gh_installed() -> bool:
    """Check if 'gh' (GitHub CLI) is accessible on PATH."""
    return shutil.which("gh") is not None


def get_git_missing_guidance() -> Dict[str, Any]:
    """Actionable guidance when Git CLI is not found on Windows."""
    return {
        "status": "tool_unavailable",
        "error": "Git CLI ('git') is not installed or not found on PATH.",
        "install_guidance": {
            "windows_winget": "winget install --id Git.Git -e",
            "official_site": "https://git-scm.com/download/win",
            "next_steps": [
                "Open PowerShell or Windows Terminal.",
                "Run: winget install --id Git.Git -e",
                "Restart your terminal, Claude Desktop, or IDE.",
                "Set author identity: git config --global user.name \"Your Name\" && git config --global user.email \"you@example.com\""
            ]
        }
    }


def get_gh_missing_guidance() -> Dict[str, Any]:
    """Actionable guidance when GitHub CLI is not found on Windows."""
    return {
        "status": "tool_unavailable",
        "error": "GitHub CLI ('gh') is not installed or not found on PATH.",
        "install_guidance": {
            "windows_winget": "winget install --id GitHub.cli -e",
            "official_site": "https://cli.github.com",
            "next_steps": [
                "Open PowerShell or Windows Terminal.",
                "Run: winget install --id GitHub.cli -e",
                "Restart your terminal, Claude Desktop, or IDE.",
                "Authenticate with GitHub: run 'gh auth login' and follow the browser prompt."
            ]
        },
        "note": "All local Git tools remain 100% operational without GitHub CLI."
    }


def get_gh_auth_missing_guidance() -> Dict[str, Any]:
    """Actionable guidance when GitHub CLI is installed but not authenticated."""
    return {
        "status": "auth_required",
        "error": "GitHub CLI ('gh') is installed, but not logged in to GitHub.",
        "login_guidance": {
            "command": "gh auth login",
            "steps": [
                "Open PowerShell or your terminal.",
                "Run: gh auth login",
                "Select 'GitHub.com', choose 'HTTPS', and log in via your web browser."
            ]
        },
        "note": "All local Git tools remain 100% operational without GitHub authentication."
    }


# ==============================================================================
# Subprocess Runners with Windows Safety & CRLF Sanitization
# ==============================================================================

def _filter_git_output(text: str) -> str:
    """Filter out noisy Windows CRLF replacement warnings."""
    if not text:
        return ""
    lines = text.splitlines()
    filtered = [
        ln for ln in lines
        if "LF will be replaced by CRLF" not in ln
        and "CRLF will be replaced by LF" not in ln
        and "warning: in the working copy of" not in ln
    ]
    return "\n".join(filtered).strip()


def _truncate_output(text: str, max_lines: int = 250, max_chars: int = 15000) -> Dict[str, Any]:
    """Protect LLM context window with token and line capping."""
    lines = text.splitlines()
    total_lines = len(lines)
    truncated = False

    if total_lines > max_lines:
        lines = lines[:max_lines]
        truncated = True

    result_text = "\n".join(lines)
    if len(result_text) > max_chars:
        result_text = result_text[:max_chars]
        truncated = True

    payload: Dict[str, Any] = {
        "content": result_text,
        "total_lines": total_lines,
        "returned_lines": len(lines),
        "truncated": truncated
    }
    if truncated:
        payload["notice"] = f"[Output capped: showing {len(lines)} of {total_lines} lines to protect context]"
    return payload


def run_git_command(args: List[str], cwd: Path, timeout: int = 30) -> Dict[str, Any]:
    """
    Execute git command with non-interactive flags and timeout protection.
    Prevents hangs on credentials, password prompts, or interactive editors.
    """
    if not is_git_installed():
        return get_git_missing_guidance()

    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GIT_EDITOR"] = "true"
    env["LC_ALL"] = "C.UTF-8"

    cmd = ["git"] + args
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd),
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout
        )
        stdout = _filter_git_output(proc.stdout)
        stderr = _filter_git_output(proc.stderr)

        return {
            "success": proc.returncode == 0,
            "returncode": proc.returncode,
            "stdout": stdout,
            "stderr": stderr
        }
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "error": f"Git command timed out after {timeout} seconds.",
            "command": " ".join(cmd)
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Failed to execute git command: {str(e)}",
            "command": " ".join(cmd)
        }


def run_gh_command(args: List[str], cwd: Path, timeout: int = 30) -> Dict[str, Any]:
    """
    Execute gh command with non-interactive flags and prompt suppression.
    """
    if not is_gh_installed():
        return get_gh_missing_guidance()

    env = os.environ.copy()
    env["GH_NO_UPDATE_NOTIFIER"] = "1"
    env["GH_PROMPT_DISABLED"] = "1"
    env["LC_ALL"] = "C.UTF-8"

    cmd = ["gh"] + args
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd),
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout
        )
        stdout = proc.stdout.strip()
        stderr = proc.stderr.strip()

        # Check for authentication errors
        if proc.returncode != 0 and any(kw in stderr.lower() for kw in ("not logged in", "authentication required", "gh auth login")):
            return get_gh_auth_missing_guidance()

        return {
            "success": proc.returncode == 0,
            "returncode": proc.returncode,
            "stdout": stdout,
            "stderr": stderr
        }
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "error": f"GitHub CLI command timed out after {timeout} seconds.",
            "command": " ".join(cmd)
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Failed to execute gh command: {str(e)}",
            "command": " ".join(cmd)
        }


# ==============================================================================
# Repository Context & Remote Auto-Detection
# ==============================================================================

def _load_repo_bookmarks() -> Dict[str, Any]:
    ensure_workspace_dirs()
    if REPOS_CONFIG_FILE.exists():
        try:
            with open(REPOS_CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {"active": None, "repos": {}}
    return {"active": None, "repos": {}}


def _save_repo_bookmarks(data: Dict[str, Any]) -> None:
    ensure_workspace_dirs()
    with open(REPOS_CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def find_git_root(start_path: Optional[str] = None) -> Optional[Path]:
    """Find closest git repository root climbing up from start_path or current dir."""
    curr = Path(start_path).resolve() if start_path else Path.cwd().resolve()
    for p in [curr] + list(curr.parents):
        git_dir = p / ".git"
        if git_dir.exists():
            return p
    return None


def resolve_repo_path(repo_path: Optional[str] = None) -> Path:
    """
    Resolve active repository path using priority:
    1. Explicit alias in registered bookmarks (e.g. 'backend', 'my-repo')
    2. Explicit filesystem path (relative or absolute)
    3. Currently active in-memory repository
    4. Saved active repository bookmark in ~/.mcp-win-stdio/git_repos.json
    5. GIT_REPO_DIR environment variable
    6. Upward climb from current working directory
    """
    global _ACTIVE_REPO

    if repo_path:
        target_str = str(repo_path).strip()
        bookmarks = _load_repo_bookmarks()
        repos = bookmarks.get("repos", {})

        # Check for registered bookmark alias or path match (case-insensitive)
        for key, p_str in repos.items():
            if key.lower() == target_str.lower() or p_str.lower() == target_str.lower():
                p = Path(p_str).resolve()
                if (p / ".git").exists() or find_git_root(str(p)):
                    return find_git_root(str(p)) or p
                return p

        # Check direct path
        p = Path(target_str).resolve()
        if (p / ".git").exists() or find_git_root(str(p)):
            return find_git_root(str(p)) or p
        return p

    if _ACTIVE_REPO and (_ACTIVE_REPO / ".git").exists():
        return _ACTIVE_REPO

    # Check bookmarks config
    bookmarks = _load_repo_bookmarks()
    active_bookmark = bookmarks.get("active")
    if active_bookmark and Path(active_bookmark).exists():
        _ACTIVE_REPO = Path(active_bookmark).resolve()
        return _ACTIVE_REPO

    # Environment variable fallback
    env_repo = os.environ.get("GIT_REPO_DIR")
    if env_repo and Path(env_repo).exists():
        _ACTIVE_REPO = Path(env_repo).resolve()
        return _ACTIVE_REPO

    # Upward climb from cwd
    cwd_root = find_git_root()
    if cwd_root:
        _ACTIVE_REPO = cwd_root
        return cwd_root

    return Path.cwd().resolve()


def get_remote_github_info(cwd: Path) -> Optional[Dict[str, str]]:
    """Extract GitHub owner and repository name from git remote origin URL."""
    res = run_git_command(["remote", "get-url", "origin"], cwd=cwd)
    if not res.get("success"):
        return None
    url = res.get("stdout", "").strip()
    if not url:
        return None

    # Matches https://github.com/owner/repo(.git) or git@github.com:owner/repo(.git)
    match = re.search(r"github\.com[/:](?P<owner>[\w\-]+)/(?P<repo>[\w\-\.]+?)(?:\.git)?$", url, re.IGNORECASE)
    if match:
        return {
            "owner": match.group("owner"),
            "repo": match.group("repo"),
            "url": url
        }
    return {"url": url, "owner": "", "repo": ""}


# ==============================================================================
# 1. Repository Context & Bookmarks
# ==============================================================================

@mcp.tool()
def use_repo(repo_path: Optional[str] = None) -> Dict[str, Any]:
    """
    Switch or display the active Git repository workspace.
    Supports directory paths or registered bookmark aliases (e.g. 'backend', 'C:/dev/project').
    If repo_path is not specified, auto-detects from the current working directory.
    
    Args:
        repo_path: Path to repository workspace or registered bookmark alias.
    """
    global _ACTIVE_REPO
    if not is_git_installed():
        return get_git_missing_guidance()

    target = resolve_repo_path(repo_path)
    if not target or not (target / ".git").exists():
        return {
            "success": False,
            "error": f"Directory '{repo_path or Path.cwd()}' is not a valid Git repository (no .git found)."
        }

    _ACTIVE_REPO = target
    bookmarks = _load_repo_bookmarks()
    bookmarks["active"] = str(target)
    if "repos" not in bookmarks:
        bookmarks["repos"] = {}
    bookmarks["repos"][target.name] = str(target)
    _save_repo_bookmarks(bookmarks)

    remote_info = get_remote_github_info(target)
    return {
        "success": True,
        "active_repo": str(target),
        "name": target.name,
        "remote_github": remote_info,
        "message": f"Active repository set to: {target}"
    }


@mcp.tool()
def list_repos() -> Dict[str, Any]:
    """
    List all registered repository bookmarks, the currently active repository, and directory validity.
    """
    bookmarks = _load_repo_bookmarks()
    active_path = str(_ACTIVE_REPO) if _ACTIVE_REPO else bookmarks.get("active")

    repos_list = []
    for alias, p_str in bookmarks.get("repos", {}).items():
        exists = Path(p_str).exists()
        is_git = (Path(p_str) / ".git").exists() if exists else False
        repos_list.append({
            "alias": alias,
            "path": p_str,
            "exists": exists,
            "is_git": is_git,
            "is_active": (p_str == active_path)
        })

    return {
        "active_repo": active_path,
        "bookmarks_count": len(repos_list),
        "repositories": repos_list
    }


@mcp.tool()
def add_repo(repo_path: str, alias: Optional[str] = None) -> Dict[str, Any]:
    """
    Bookmark a repository path with an optional alias for instant switching across multi-project workspaces.
    
    Args:
        repo_path: Local filesystem path to the Git repository.
        alias: Optional friendly alias (e.g. 'backend', 'frontend', 'docs'). Defaults to directory name.
    """
    p = find_git_root(repo_path)
    if not p or not (p / ".git").exists():
        return {
            "success": False,
            "error": f"Path '{repo_path}' is not a valid Git repository."
        }

    key = alias or p.name
    bookmarks = _load_repo_bookmarks()
    if "repos" not in bookmarks:
        bookmarks["repos"] = {}
    bookmarks["repos"][key] = str(p)
    _save_repo_bookmarks(bookmarks)

    return {
        "success": True,
        "alias": key,
        "path": str(p),
        "message": f"Repository '{key}' registered successfully."
    }


@mcp.tool()
def remove_repo(alias_or_path: str) -> Dict[str, Any]:
    """
    Remove or drop a repository bookmark or alias from registered workspaces.
    
    Args:
        alias_or_path: Bookmark alias name (e.g. 'backend') or filesystem path to remove.
    """
    bookmarks = _load_repo_bookmarks()
    repos = bookmarks.get("repos", {})
    target_str = str(alias_or_path).strip()

    removed_key = None
    if target_str in repos:
        removed_key = target_str
    else:
        for k, p in list(repos.items()):
            if k.lower() == target_str.lower() or p.lower() == target_str.lower():
                removed_key = k
                break

    if not removed_key:
        return {
            "success": False,
            "error": f"Bookmark or path '{alias_or_path}' not found in registered repositories.",
            "available_aliases": list(repos.keys())
        }

    removed_path = repos.pop(removed_key)
    if bookmarks.get("active") == removed_path:
        bookmarks["active"] = None
    _save_repo_bookmarks(bookmarks)

    return {
        "success": True,
        "removed_alias": removed_key,
        "removed_path": removed_path,
        "remaining_count": len(repos),
        "message": f"Bookmark alias '{removed_key}' successfully removed."
    }


@mcp.tool()
def rename_alias(old_alias: str, new_alias: str) -> Dict[str, Any]:
    """
    Rename an existing repository bookmark alias (e.g. rename 'backend' to 'api-service').
    
    Args:
        old_alias: Current bookmark alias name.
        new_alias: New alias name to assign.
    """
    bookmarks = _load_repo_bookmarks()
    repos = bookmarks.get("repos", {})
    old_key = str(old_alias).strip()
    new_key = str(new_alias).strip()

    if not new_key:
        return {"success": False, "error": "New alias name cannot be empty."}

    matched_key = None
    if old_key in repos:
        matched_key = old_key
    else:
        for k in repos:
            if k.lower() == old_key.lower():
                matched_key = k
                break

    if not matched_key:
        return {
            "success": False,
            "error": f"Alias '{old_alias}' not found in registered bookmarks.",
            "available_aliases": list(repos.keys())
        }

    target_path = repos.pop(matched_key)
    repos[new_key] = target_path
    bookmarks["repos"] = repos
    _save_repo_bookmarks(bookmarks)

    return {
        "success": True,
        "old_alias": matched_key,
        "new_alias": new_key,
        "path": target_path,
        "message": f"Successfully renamed bookmark alias from '{matched_key}' to '{new_key}'."
    }


@mcp.tool()
def git_init(
    repo_path: Optional[str] = None,

    initial_branch: str = "main",
    remote_url: Optional[str] = None,
    alias: Optional[str] = None
) -> Dict[str, Any]:
    """
    Initialize a new local Git repository, configure default branch, and optionally connect a remote origin.
    
    Args:
        repo_path: Directory path where repository will be created (defaults to current working directory).
        initial_branch: Initial branch name (default 'main').
        remote_url: Optional remote Git URL (e.g. 'https://github.com/owner/repo.git') to add as origin.
        alias: Optional bookmark alias to register in ~/.mcp-win-stdio/git_repos.json.
    """
    if not is_git_installed():
        return get_git_missing_guidance()

    target_dir = Path(repo_path).resolve() if repo_path else Path.cwd().resolve()
    target_dir.mkdir(parents=True, exist_ok=True)

    args = ["init", "-b", initial_branch]
    res = run_git_command(args, cwd=target_dir)
    if not res.get("success"):
        return {"success": False, "error": res.get("stderr") or res.get("stdout")}

    remote_msg = None
    if remote_url:
        r_res = run_git_command(["remote", "add", "origin", remote_url], cwd=target_dir)
        remote_msg = "Remote 'origin' added." if r_res.get("success") else f"Failed to add remote: {r_res.get('stderr')}"

    # Auto bookmark
    key = alias or target_dir.name
    bookmarks = _load_repo_bookmarks()
    if "repos" not in bookmarks:
        bookmarks["repos"] = {}
    bookmarks["repos"][key] = str(target_dir)
    bookmarks["active"] = str(target_dir)
    _save_repo_bookmarks(bookmarks)

    global _ACTIVE_REPO
    _ACTIVE_REPO = target_dir

    return {
        "success": True,
        "repository_path": str(target_dir),
        "initial_branch": initial_branch,
        "remote": remote_url,
        "remote_status": remote_msg,
        "alias": key,
        "message": f"Initialized Git repository in {target_dir} with initial branch '{initial_branch}'."
    }


# ==============================================================================
# 2. Hybrid Synergy Tools (Git + GH Combined)
# ==============================================================================

@mcp.tool()
def repo_overview(repo_path: Optional[str] = None) -> Dict[str, Any]:
    """
    Unified 360-degree repository status: local branch, dirty status, ahead/behind
    tracking, open Pull Request for active branch, and latest CI/CD workflow runs.
    Gracefully degrades if GitHub CLI ('gh') is not installed or not logged in.
    
    Args:
        repo_path: Optional path to repository workspace or bookmark alias.
    """
    if not is_git_installed():
        return get_git_missing_guidance()

    cwd = resolve_repo_path(repo_path)
    if not (cwd / ".git").exists():
        return {"success": False, "error": f"Not a git repository: {cwd}"}

    # 1. Local Git Branch & Status
    b_res = run_git_command(["branch", "--show-current"], cwd=cwd)
    curr_branch = b_res.get("stdout", "").strip() or "HEAD (detached)"

    s_res = run_git_command(["status", "--porcelain", "-b"], cwd=cwd)
    status_lines = s_res.get("stdout", "").splitlines()
    branch_header = status_lines[0] if status_lines else ""
    file_changes = status_lines[1:] if len(status_lines) > 1 else []

    # Tracking ahead/behind
    ahead, behind = 0, 0
    if "ahead" in branch_header:
        m = re.search(r"ahead (\d+)", branch_header)
        if m:
            ahead = int(m.group(1))
    if "behind" in branch_header:
        m = re.search(r"behind (\d+)", branch_header)
        if m:
            behind = int(m.group(1))

    # Conflict check
    is_merging = (cwd / ".git" / "MERGE_HEAD").exists()
    is_rebasing = (cwd / ".git" / "rebase-apply").exists() or (cwd / ".git" / "rebase-merge").exists()
    is_cherry_picking = (cwd / ".git" / "CHERRY_PICK_HEAD").exists()

    overview: Dict[str, Any] = {
        "repository_path": str(cwd),
        "branch": curr_branch,
        "tracking": branch_header.lstrip("## "),
        "ahead": ahead,
        "behind": behind,
        "uncommitted_files_count": len(file_changes),
        "is_dirty": len(file_changes) > 0,
        "in_progress_state": {
            "merging": is_merging,
            "rebasing": is_rebasing,
            "cherry_picking": is_cherry_picking
        }
    }

    # 2. Remote GitHub Status (Graceful degradation)
    remote_info = get_remote_github_info(cwd)
    overview["remote"] = remote_info

    if not is_gh_installed():
        overview["github"] = {
            "available": False,
            "status": "gh_missing",
            "message": "GitHub CLI ('gh') is not installed. Run 'winget install --id GitHub.cli -e' to view PRs and CI runs."
        }
        return overview

    # Query active PR for this branch
    pr_res = run_gh_command(["pr", "view", curr_branch, "--json", "number,title,state,url,mergeable,reviewDecision"], cwd=cwd)
    active_pr = None
    if pr_res.get("success"):
        try:
            active_pr = json.loads(pr_res.get("stdout", "{}"))
        except Exception:
            pass

    # Query latest GitHub Actions CI run
    run_res = run_gh_command(["run", "list", "--limit", "1", "--json", "databaseId,status,conclusion,name,headBranch,url"], cwd=cwd)
    latest_run = None
    if run_res.get("success"):
        try:
            runs = json.loads(run_res.get("stdout", "[]"))
            if runs:
                latest_run = runs[0]
        except Exception:
            pass

    overview["github"] = {
        "available": True,
        "active_pull_request": active_pr,
        "latest_ci_run": latest_run
    }

    return overview


@mcp.tool()
def pr_quickstart(
    title: str,
    body: Optional[str] = None,
    branch: Optional[str] = None,
    files: Optional[List[str]] = None,
    draft: bool = False,
    repo_path: Optional[str] = None
) -> Dict[str, Any]:
    """
    Seamless Hybrid Workflow:
    1. Stages specified files (or all changes if files is omitted)
    2. Commits with the specified title/body
    3. Pushes branch to origin with upstream tracking
    4. Creates a GitHub Pull Request via 'gh pr create'
    
    Args:
        title: Commit message and Pull Request title.
        body: Optional Pull Request description body.
        branch: Optional branch name to create/checkout.
        files: Optional list of specific files (relative or absolute) to stage.
        draft: Create Pull Request as draft (default False).
        repo_path: Optional repository path or bookmark alias.
    """
    if not is_git_installed():
        return get_git_missing_guidance()
    if not is_gh_installed():
        return get_gh_missing_guidance()

    cwd = resolve_repo_path(repo_path)
    if not (cwd / ".git").exists():
        return {"success": False, "error": f"Not a git repository: {cwd}"}

    # Step 1: Switch or verify branch
    if branch:
        run_git_command(["checkout", "-B", branch], cwd=cwd)
    b_res = run_git_command(["branch", "--show-current"], cwd=cwd)
    curr_branch = b_res.get("stdout", "").strip()

    if curr_branch in ("main", "master") and not branch:
        return {
            "success": False,
            "error": f"Cannot create PR directly from default branch '{curr_branch}'. Please specify a feature branch name."
        }

    # Step 2: Stage and Commit
    if files:
        run_git_command(["add"] + files, cwd=cwd)
    else:
        run_git_command(["add", "-A"], cwd=cwd)

    # Check if anything to commit
    st = run_git_command(["status", "--porcelain"], cwd=cwd)
    if st.get("stdout", "").strip():
        c_args = ["commit", "-m", title]
        if body:
            c_args += ["-m", body]
        c_res = run_git_command(c_args, cwd=cwd)
        if not c_res.get("success"):
            return {"success": False, "step": "commit", "error": c_res.get("stderr") or c_res.get("stdout")}

    # Step 3: Push to remote
    p_res = run_git_command(["push", "-u", "origin", curr_branch], cwd=cwd)
    if not p_res.get("success"):
        return {"success": False, "step": "push", "error": p_res.get("stderr") or p_res.get("stdout")}

    # Step 4: Create PR with GitHub CLI
    gh_args = ["pr", "create", "--title", title, "--body", body or title]
    if draft:
        gh_args.append("--draft")

    gh_res = run_gh_command(gh_args, cwd=cwd)
    if not gh_res.get("success"):
        return {
            "success": False,
            "step": "gh_pr_create",
            "branch": curr_branch,
            "message": "Pushed to remote successfully, but PR creation failed.",
            "error": gh_res.get("stderr") or gh_res.get("stdout")
        }

    return {
        "success": True,
        "branch": curr_branch,
        "pr_url": gh_res.get("stdout", "").strip(),
        "message": f"Successfully committed, pushed, and opened PR on {curr_branch}."
    }


@mcp.tool()
def issue_start_work(
    issue_number: int,
    branch_prefix: str = "feature",
    repo_path: Optional[str] = None
) -> Dict[str, Any]:
    """
    Issue-Driven Workflow:
    Fetches GitHub Issue details via 'gh issue view', extracts title, creates a clean
    local branch name (e.g. 'feature/42-fix-login-error'), and checks it out.
    
    Args:
        issue_number: GitHub issue number (e.g. 42).
        branch_prefix: Branch category prefix (default 'feature').
        repo_path: Optional repository path or bookmark alias.
    """
    if not is_git_installed():
        return get_git_missing_guidance()
    if not is_gh_installed():
        return get_gh_missing_guidance()

    cwd = resolve_repo_path(repo_path)
    # Fetch issue
    i_res = run_gh_command(["issue", "view", str(issue_number), "--json", "number,title,labels,body,url"], cwd=cwd)
    if not i_res.get("success"):
        return {"success": False, "error": f"Failed to fetch issue #{issue_number}: {i_res.get('stderr')}"}

    try:
        issue = json.loads(i_res.get("stdout", "{}"))
    except Exception as e:
        return {"success": False, "error": f"Invalid JSON from gh issue view: {str(e)}"}

    title = issue.get("title", f"issue-{issue_number}")
    clean_title = re.sub(r"[^\w\s-]", "", title.lower())
    slug = re.sub(r"[\s_-]+", "-", clean_title).strip("-")[:40]
    branch_name = f"{branch_prefix}/{issue_number}-{slug}"

    b_res = run_git_command(["checkout", "-b", branch_name], cwd=cwd)
    if not b_res.get("success"):
        return {"success": False, "error": f"Failed to create branch '{branch_name}': {b_res.get('stderr')}"}

    return {
        "success": True,
        "issue": issue,
        "created_branch": branch_name,
        "message": f"Checked out local branch '{branch_name}' for issue #{issue_number}."
    }


# ==============================================================================
# 3. Local Git Operations (16 Tools)
# ==============================================================================

@mcp.tool()
def git_status(repo_path: Optional[str] = None) -> Dict[str, Any]:
    """
    Structured git status showing staged, unstaged, untracked files, and in-progress states.
    
    Args:
        repo_path: Optional repository path or bookmark alias.
    """
    if not is_git_installed():
        return get_git_missing_guidance()

    cwd = resolve_repo_path(repo_path)
    res = run_git_command(["status", "--porcelain=v1", "-b"], cwd=cwd)
    if not res.get("success"):
        return {"success": False, "error": res.get("stderr") or res.get("stdout")}

    lines = res.get("stdout", "").splitlines()
    branch_line = lines[0] if lines else ""
    staged, unstaged, untracked = [], [], []

    for line in lines[1:]:
        if len(line) < 3:
            continue
        index_code = line[0]
        worktree_code = line[1]
        file_path = line[3:].strip()

        if index_code == "?" and worktree_code == "?":
            untracked.append(file_path)
        else:
            if index_code not in (" ", "?"):
                staged.append({"path": file_path, "status": index_code})
            if worktree_code not in (" ", "?"):
                unstaged.append({"path": file_path, "status": worktree_code})

    return {
        "success": True,
        "branch": branch_line.lstrip("## "),
        "clean": len(staged) == 0 and len(unstaged) == 0 and len(untracked) == 0,
        "staged": staged,
        "unstaged": unstaged,
        "untracked": untracked,
        "counts": {
            "staged": len(staged),
            "unstaged": len(unstaged),
            "untracked": len(untracked)
        }
    }


@mcp.tool()
def git_diff(
    staged: bool = False,
    target: Optional[str] = None,
    path: Optional[str] = None,
    files: Optional[List[str]] = None,
    offset_lines: int = 0,
    max_lines: int = 250,
    repo_path: Optional[str] = None
) -> Dict[str, Any]:
    """
    Token-safe git diff with pagination and line offset chunking.
    Inspect unstaged working tree diffs, staged index diffs, or diffs across commits/branches.
    
    Args:
        staged: If True, inspect staged changes in the index (--staged).
        target: Comparison target (e.g. branch name 'main', commit SHA 'HEAD~1', or 'origin/main...HEAD').
        path: Single file path filter.
        files: Optional list of file paths (relative or absolute) to diff.
        offset_lines: Starting line index for chunked diff inspection of large diffs (default 0).
        max_lines: Maximum number of diff lines to return in this chunk (default 250).
        repo_path: Optional repository path or bookmark alias.
    """
    if not is_git_installed():
        return get_git_missing_guidance()

    cwd = resolve_repo_path(repo_path)
    args = ["diff"]
    if staged:
        args.append("--staged")
    if target:
        args.append(target)
    
    path_filters = []
    if path:
        path_filters.append(path)
    if files:
        path_filters.extend(files)

    if path_filters:
        args += ["--"] + path_filters

    res = run_git_command(args, cwd=cwd)
    if not res.get("success"):
        return {"success": False, "error": res.get("stderr") or res.get("stdout")}

    raw_diff = res.get("stdout", "")
    if not raw_diff:
        return {
            "success": True,
            "diff": "",
            "total_lines": 0,
            "returned_lines": 0,
            "offset_lines": offset_lines,
            "has_more": False,
            "message": "No diff found (working tree clean or matches target)."
        }

    all_lines = raw_diff.splitlines()
    total_lines = len(all_lines)
    
    # Safe chunking
    start_idx = max(0, offset_lines)
    chunk_lines = all_lines[start_idx : start_idx + max_lines]
    returned_lines = len(chunk_lines)
    has_more = (start_idx + returned_lines) < total_lines
    next_offset = (start_idx + returned_lines) if has_more else None

    diff_content = "\n".join(chunk_lines)
    notice = None
    if total_lines > max_lines:
        notice = f"[Diff chunk: showing lines {start_idx + 1} to {start_idx + returned_lines} of {total_lines}. Use offset_lines={next_offset} to view next chunk.]"

    return {
        "success": True,
        "staged": staged,
        "target": target,
        "diff": diff_content,
        "total_lines": total_lines,
        "returned_lines": returned_lines,
        "offset_lines": start_idx,
        "has_more": has_more,
        "next_offset": next_offset,
        "notice": notice
    }


@mcp.tool()
def git_log(
    max_count: int = 20,
    branch: Optional[str] = None,
    path: Optional[str] = None,
    repo_path: Optional[str] = None
) -> Dict[str, Any]:
    """
    Structured commit history with hash, author, relative date, and subject.
    Capped to prevent context window blowout.
    
    Args:
        max_count: Maximum number of commits to retrieve (default 20, max 100).
        branch: Optional branch name or revision range (e.g. 'main', 'feature..main').
        path: Optional file path filter to trace history of a specific file.
        repo_path: Optional repository workspace path or bookmark alias.
    """
    if not is_git_installed():
        return get_git_missing_guidance()

    cwd = resolve_repo_path(repo_path)
    limit = min(max(1, max_count), 100)
    fmt = "%H%x1f%an%x1f%ae%x1f%cr%x1f%s"
    args = ["log", f"-n{limit}", f"--format={fmt}"]
    if branch:
        args.append(branch)
    if path:
        args += ["--", path]

    res = run_git_command(args, cwd=cwd)
    if not res.get("success"):
        return {"success": False, "error": res.get("stderr") or res.get("stdout")}

    commits = []
    for line in res.get("stdout", "").splitlines():
        parts = line.split("\x1f")
        if len(parts) >= 5:
            commits.append({
                "commit": parts[0],
                "short_hash": parts[0][:7],
                "author": parts[1],
                "email": parts[2],
                "date": parts[3],
                "subject": parts[4]
            })

    return {
        "success": True,
        "count": len(commits),
        "commits": commits
    }


@mcp.tool()
def git_commit(
    message: str,
    files: Optional[List[str]] = None,
    all_modified: bool = False,
    include_untracked: bool = False,
    repo_path: Optional[str] = None
) -> Dict[str, Any]:
    """
    Stage files and create a Git commit with a clean descriptive message and author verification.
    
    Args:
        message: Descriptive commit message.
        files: Optional explicit list of file paths (relative to repo root or absolute) to stage and commit.
        all_modified: If True, stages all modified and deleted tracked files (git add -u).
        include_untracked: If True, stages all tracked and untracked files in the working tree (git add -A).
        repo_path: Optional repository workspace path or bookmark alias.
    """
    if not is_git_installed():
        return get_git_missing_guidance()

    cwd = resolve_repo_path(repo_path)

    # Check git author identity
    name_res = run_git_command(["config", "user.name"], cwd=cwd)
    email_res = run_git_command(["config", "user.email"], cwd=cwd)
    if not name_res.get("stdout") or not email_res.get("stdout"):
        return {
            "success": False,
            "error": "Git author identity is not configured.",
            "guidance": "Run: git config --global user.name \"Your Name\" && git config --global user.email \"you@example.com\""
        }

    # Staging
    if include_untracked:
        a_res = run_git_command(["add", "-A"], cwd=cwd)
        if not a_res.get("success"):
            return {"success": False, "step": "stage", "error": a_res.get("stderr")}
    elif files:
        a_res = run_git_command(["add"] + files, cwd=cwd)
        if not a_res.get("success"):
            return {"success": False, "step": "stage", "error": a_res.get("stderr")}
    elif all_modified:
        a_res = run_git_command(["add", "-u"], cwd=cwd)
        if not a_res.get("success"):
            return {"success": False, "step": "stage", "error": a_res.get("stderr")}

    # Check untracked files status
    st_res = run_git_command(["status", "--porcelain"], cwd=cwd)
    untracked_remaining = []
    for line in st_res.get("stdout", "").splitlines():
        if line.startswith("??"):
            untracked_remaining.append(line[3:].strip())

    # Commit
    res = run_git_command(["commit", "-m", message], cwd=cwd)
    if not res.get("success"):
        return {
            "success": False,
            "step": "commit",
            "error": res.get("stderr") or res.get("stdout"),
            "untracked_files_remaining": untracked_remaining
        }

    return {
        "success": True,
        "output": res.get("stdout"),
        "message": "Commit created successfully.",
        "untracked_files_skipped": untracked_remaining if untracked_remaining else None
    }


@mcp.tool()
def git_branch(
    action: Literal["list", "create", "switch", "delete"] = "list",
    branch_name: Optional[str] = None,
    start_point: Optional[str] = None,
    delete: bool = False,
    force: bool = False,
    repo_path: Optional[str] = None
) -> Dict[str, Any]:
    """
    Branch operations: list branches, create, switch, or safely delete branches.
    
    Args:
        action: Branch action ('list', 'create', 'switch', 'delete').
        branch_name: Name of branch to create, switch to, or delete.
        start_point: Optional commit/branch to branch off from (for 'create').
        delete: Deprecated flag. Prefer action='delete'.
        force: If True with action='delete', force deletes unmerged branch (-D).
        repo_path: Optional repository workspace path or bookmark alias.
    """
    if not is_git_installed():
        return get_git_missing_guidance()

    cwd = resolve_repo_path(repo_path)
    act = action.lower()

    if act == "list":
        res = run_git_command(["branch", "-a", "--format=%(refname:short)|%(upstream:short)|%(HEAD)"], cwd=cwd)
        branches = []
        for line in res.get("stdout", "").splitlines():
            parts = line.split("|")
            if len(parts) >= 3:
                branches.append({
                    "name": parts[0],
                    "upstream": parts[1] or None,
                    "is_current": parts[2] == "*"
                })
        return {"success": True, "branches": branches}

    if act == "create":
        if not branch_name:
            return {"success": False, "error": "branch_name is required for creating a branch."}
        args = ["checkout", "-b", branch_name]
        if start_point:
            args.append(start_point)
        res = run_git_command(args, cwd=cwd)
        return {"success": res.get("success"), "output": res.get("stdout") or res.get("stderr")}

    if act == "switch":
        if not branch_name:
            return {"success": False, "error": "branch_name is required for switching branch."}
        res = run_git_command(["checkout", branch_name], cwd=cwd)
        return {"success": res.get("success"), "output": res.get("stdout") or res.get("stderr")}

    if act == "delete" or delete:
        if not branch_name:
            return {"success": False, "error": "branch_name is required for deleting a branch."}
        flag = "-D" if force else "-d"
        res = run_git_command(["branch", flag, branch_name], cwd=cwd)
        return {"success": res.get("success"), "output": res.get("stdout") or res.get("stderr")}

    return {"success": False, "error": f"Unknown branch action: '{action}'. Use list, create, switch, or delete."}


@mcp.tool()
def git_stash(
    action: Literal["list", "save", "pop", "drop", "clear"] = "list",
    message: Optional[str] = None,
    index: int = 0,
    repo_path: Optional[str] = None
) -> Dict[str, Any]:
    """
    Manage the Git stash: 'save', 'pop', 'list', 'drop', 'clear'.
    
    Args:
        action: Stash action ('list', 'save', 'pop', 'drop', 'clear').
        message: Optional description message when saving stash.
        index: Stash index integer for pop/drop (default 0 for stash@{0}).
        repo_path: Optional repository workspace path or bookmark alias.
    """
    if not is_git_installed():
        return get_git_missing_guidance()

    cwd = resolve_repo_path(repo_path)
    act = action.lower()

    if act == "list":
        res = run_git_command(["stash", "list"], cwd=cwd)
        stashes = res.get("stdout", "").splitlines()
        return {"success": True, "count": len(stashes), "stashes": stashes}

    if act in ("save", "push"):
        args = ["stash", "push"]
        if message:
            args += ["-m", message]
        res = run_git_command(args, cwd=cwd)
        return {"success": res.get("success"), "output": res.get("stdout") or res.get("stderr")}

    if act == "pop":
        res = run_git_command(["stash", "pop", f"stash@{{{index}}}"], cwd=cwd)
        return {"success": res.get("success"), "output": res.get("stdout") or res.get("stderr")}

    if act == "drop":
        res = run_git_command(["stash", "drop", f"stash@{{{index}}}"], cwd=cwd)
        return {"success": res.get("success"), "output": res.get("stdout") or res.get("stderr")}

    if act == "clear":
        res = run_git_command(["stash", "clear"], cwd=cwd)
        return {"success": res.get("success"), "output": res.get("stdout") or "Stash cleared."}

    return {"success": False, "error": f"Unknown stash action '{action}'. Use list, save, pop, drop, or clear."}


@mcp.tool()
def git_sync(
    action: Literal["pull", "push", "fetch", "sync"] = "pull",
    remote: str = "origin",
    branch: Optional[str] = None,
    set_upstream: bool = False,
    repo_path: Optional[str] = None
) -> Dict[str, Any]:
    """
    Synchronize with remote repository: 'fetch', 'pull', 'push', or 'sync' (pull then push).
    
    Args:
        action: Sync action ('fetch', 'pull', 'push', 'sync').
        remote: Remote repository name (default 'origin').
        branch: Optional remote branch name to target.
        set_upstream: If True when pushing, sets upstream tracking (-u).
        repo_path: Optional repository workspace path or bookmark alias.
    """
    if not is_git_installed():
        return get_git_missing_guidance()

    cwd = resolve_repo_path(repo_path)
    act = action.lower()

    if act == "fetch":
        res = run_git_command(["fetch", remote], cwd=cwd)
        return {"success": res.get("success"), "output": res.get("stdout") or res.get("stderr")}

    if act == "pull":
        args = ["pull", remote]
        if branch:
            args.append(branch)
        res = run_git_command(args, cwd=cwd)
        return {"success": res.get("success"), "output": res.get("stdout") or res.get("stderr")}

    if act == "push":
        args = ["push"]
        if set_upstream:
            args.append("-u")
        args.append(remote)
        if branch:
            args.append(branch)
        res = run_git_command(args, cwd=cwd)
        return {"success": res.get("success"), "output": res.get("stdout") or res.get("stderr")}

    if act == "sync":
        # Pull then push
        p_res = run_git_command(["pull", remote] + ([branch] if branch else []), cwd=cwd)
        if not p_res.get("success"):
            return {"success": False, "step": "pull", "error": p_res.get("stderr") or p_res.get("stdout")}
        
        push_args = ["push"] + (["-u"] if set_upstream else []) + [remote] + ([branch] if branch else [])
        ps_res = run_git_command(push_args, cwd=cwd)
        return {
            "success": ps_res.get("success"),
            "pull_output": p_res.get("stdout"),
            "push_output": ps_res.get("stdout") or ps_res.get("stderr")
        }

    return {"success": False, "error": f"Unknown sync action: '{action}'. Use fetch, pull, push, or sync."}


@mcp.tool()
def git_blame(
    file_path: str,
    start_line: Optional[int] = None,
    end_line: Optional[int] = None,
    repo_path: Optional[str] = None
) -> Dict[str, Any]:
    """
    View file blame line-by-line with author, date, and commit hash.
    Supports line range filtering (start_line, end_line) to conserve context tokens.
    
    Args:
        file_path: Relative or absolute path to the file.
        start_line: Optional starting line number (1-indexed).
        end_line: Optional ending line number (1-indexed).
        repo_path: Optional repository workspace path or bookmark alias.
    """
    if not is_git_installed():
        return get_git_missing_guidance()

    cwd = resolve_repo_path(repo_path)
    args = ["blame", "--show-email", "-s"]
    if start_line is not None and end_line is not None:
        args += [f"-L{start_line},{end_line}"]
    elif start_line is not None:
        args += [f"-L{start_line},+50"]
    args += ["--", file_path]

    res = run_git_command(args, cwd=cwd)
    if not res.get("success"):
        return {"success": False, "error": res.get("stderr") or res.get("stdout")}

    capped = _truncate_output(res.get("stdout", ""), max_lines=200)
    return {
        "success": True,
        "file": file_path,
        "blame": capped["content"],
        "lines": capped["returned_lines"],
        "truncated": capped["truncated"]
    }


@mcp.tool()
def git_restore(
    files: List[str],
    staged: bool = False,
    source: Optional[str] = None,
    repo_path: Optional[str] = None
) -> Dict[str, Any]:
    """
    Safely restore working tree files or unstage files from the index (git restore).
    
    Args:
        files: List of file paths (relative to repo root or absolute) to restore.
        staged: If True, unstage files from the index (--staged). If False, discard working tree changes.
        source: Optional commit hash or branch to restore files from (e.g. 'HEAD~1', 'main').
        repo_path: Optional repository workspace path or bookmark alias.
    """
    if not is_git_installed():
        return get_git_missing_guidance()

    if not files:
        return {"success": False, "error": "Specify at least one file path to restore."}

    cwd = resolve_repo_path(repo_path)
    args = ["restore"]
    if staged:
        args.append("--staged")
    if source:
        args.append(f"--source={source}")
    args += ["--"] + files

    res = run_git_command(args, cwd=cwd)
    if not res.get("success"):
        return {"success": False, "error": res.get("stderr") or res.get("stdout")}

    action_desc = "unregistered/unstaged from index" if staged else "restored in working tree"
    return {
        "success": True,
        "restored_files": files,
        "staged": staged,
        "source": source or "HEAD",
        "message": f"Successfully {action_desc} {len(files)} file(s)."
    }


@mcp.tool()
def git_reset(
    mode: Literal["restore", "soft", "mixed", "hard"] = "restore",
    target: Optional[str] = None,
    files: Optional[List[str]] = None,
    confirm_destructive: bool = False,
    repo_path: Optional[str] = None
) -> Dict[str, Any]:
    """
    Safe file restore or commit history reset:
    - mode='restore': Safely discards unstaged changes in specific files (git restore <files>).
    - mode='soft': Reset commit history while keeping working tree and index changes intact.
    - mode='mixed': Reset commit history and unstages index while keeping working tree files.
    - mode='hard': Destructive reset. Requires confirm_destructive=True.
    
    Args:
        mode: Reset mode ('restore', 'soft', 'mixed', 'hard').
        target: Target commit (e.g. 'HEAD~1', 'origin/main'). Defaults to 'HEAD~1' for soft/mixed, 'HEAD' for hard.
        files: Specific files to restore (used when mode='restore').
        confirm_destructive: Safety guard required to execute destructive mode='hard'.
        repo_path: Optional repository workspace path or bookmark alias.
    """
    if not is_git_installed():
        return get_git_missing_guidance()

    cwd = resolve_repo_path(repo_path)
    m = mode.lower()

    if m == "restore":
        if not files:
            return {"success": False, "error": "Specify files to restore, or use confirm_destructive=True with mode='hard'."}
        res = run_git_command(["restore"] + files, cwd=cwd)
        return {"success": res.get("success"), "output": res.get("stdout") or res.get("stderr") or "Files restored."}

    if m == "soft":
        tgt = target or "HEAD~1"
        res = run_git_command(["reset", "--soft", tgt], cwd=cwd)
        return {"success": res.get("success"), "output": res.get("stdout") or res.get("stderr")}

    if m == "mixed":
        tgt = target or "HEAD~1"
        res = run_git_command(["reset", "--mixed", tgt], cwd=cwd)
        return {"success": res.get("success"), "output": res.get("stdout") or res.get("stderr")}

    if m == "hard":
        if not confirm_destructive:
            return {
                "success": False,
                "error": "Destructive operation blocked. 'git reset --hard' wipes all uncommitted changes. Pass confirm_destructive=True to proceed."
            }
        tgt = target or "HEAD"
        res = run_git_command(["reset", "--hard", tgt], cwd=cwd)
        return {"success": res.get("success"), "output": res.get("stdout") or res.get("stderr")}

    return {"success": False, "error": f"Unknown reset mode '{mode}'. Use restore, soft, mixed, or hard."}


@mcp.tool()
def git_tag(
    action: Literal["list", "create", "delete"] = "list",
    tag_name: Optional[str] = None,
    message: Optional[str] = None,
    delete: bool = False,
    repo_path: Optional[str] = None
) -> Dict[str, Any]:
    """
    List, create, or delete Git tags.
    
    Args:
        action: Tag action ('list', 'create', 'delete').
        tag_name: Name of the tag to create or delete (e.g. 'v1.0.0').
        message: Optional annotation message when creating tag.
        delete: Deprecated flag. Prefer action='delete'.
        repo_path: Optional repository workspace path or bookmark alias.
    """
    if not is_git_installed():
        return get_git_missing_guidance()

    cwd = resolve_repo_path(repo_path)
    act = action.lower()

    if act == "list":
        res = run_git_command(["tag", "-l", "--sort=-creatordate"], cwd=cwd)
        tags = res.get("stdout", "").splitlines()[:50]
        return {"success": True, "tags": tags, "count": len(tags)}

    if act in ("create", "add"):
        if not tag_name:
            return {"success": False, "error": "tag_name is required to create a tag."}
        args = ["tag", tag_name]
        if message:
            args += ["-a", "-m", message]
        res = run_git_command(args, cwd=cwd)
        return {"success": res.get("success"), "output": res.get("stdout") or res.get("stderr")}

    if act == "delete" or delete:
        if not tag_name:
            return {"success": False, "error": "tag_name is required to delete a tag."}
        res = run_git_command(["tag", "-d", tag_name], cwd=cwd)
        return {"success": res.get("success"), "output": res.get("stdout") or res.get("stderr")}

    return {"success": False, "error": f"Unknown tag action: '{action}'. Use list, create, or delete."}


@mcp.tool()
def git_remote(
    action: Literal["list", "add", "set-url", "remove", "get-url"] = "list",
    name: str = "origin",
    url: Optional[str] = None,
    repo_path: Optional[str] = None
) -> Dict[str, Any]:
    """
    Inspect and configure Git remotes (origin, upstream) without raw git config manipulation.
    
    Args:
        action: Remote action ('list', 'add', 'set-url', 'remove', 'get-url').
        name: Remote name (default 'origin').
        url: Remote repository URL (required for 'add' and 'set-url').
        repo_path: Optional repository workspace path or bookmark alias.
    """
    if not is_git_installed():
        return get_git_missing_guidance()

    cwd = resolve_repo_path(repo_path)
    act = action.lower()

    if act == "list":
        res = run_git_command(["remote", "-v"], cwd=cwd)
        lines = res.get("stdout", "").splitlines()
        remotes: Dict[str, Dict[str, str]] = {}
        for ln in lines:
            parts = ln.split()
            if len(parts) >= 3:
                r_name, r_url, r_type = parts[0], parts[1], parts[2].strip("()")
                if r_name not in remotes:
                    remotes[r_name] = {}
                remotes[r_name][r_type] = r_url
        return {"success": True, "remotes": remotes}

    if act == "get-url":
        res = run_git_command(["remote", "get-url", name], cwd=cwd)
        return {"success": res.get("success"), "remote": name, "url": res.get("stdout", "").strip()}

    if act == "add":
        if not url:
            return {"success": False, "error": "URL is required to add a remote."}
        res = run_git_command(["remote", "add", name, url], cwd=cwd)
        return {"success": res.get("success"), "remote": name, "url": url, "output": res.get("stdout") or res.get("stderr")}

    if act == "set-url":
        if not url:
            return {"success": False, "error": "URL is required to update a remote."}
        res = run_git_command(["remote", "set-url", name, url], cwd=cwd)
        return {"success": res.get("success"), "remote": name, "url": url, "output": res.get("stdout") or res.get("stderr")}

    if act == "remove":
        res = run_git_command(["remote", "remove", name], cwd=cwd)
        return {"success": res.get("success"), "remote": name, "output": res.get("stdout") or res.get("stderr")}

    return {"success": False, "error": f"Unknown remote action: '{action}'. Use list, add, set-url, remove, or get-url."}


@mcp.tool()
def git_grep(
    pattern: str,
    path_spec: Optional[str] = None,
    ignore_case: bool = True,
    max_results: int = 50,
    repo_path: Optional[str] = None
) -> Dict[str, Any]:
    """
    Fast regex pattern search across tracked repository files at commit/branch level.
    
    Args:
        pattern: Regex or literal string pattern to search for.
        path_spec: Optional glob path filter (e.g. '*.py', 'src/').
        ignore_case: Case-insensitive search (default True).
        max_results: Maximum matching lines to return (default 50).
        repo_path: Optional repository workspace path or bookmark alias.
    """
    if not is_git_installed():
        return get_git_missing_guidance()

    cwd = resolve_repo_path(repo_path)
    args = ["grep", "-n", "-E"]
    if ignore_case:
        args.append("-i")
    args.append(pattern)
    if path_spec:
        args += ["--", path_spec]

    res = run_git_command(args, cwd=cwd)
    lines = res.get("stdout", "").splitlines()
    capped = lines[:max_results]

    matches = []
    for ln in capped:
        parts = ln.split(":", 2)
        if len(parts) >= 3:
            matches.append({"file": parts[0], "line": parts[1], "match": parts[2]})
        else:
            matches.append({"raw": ln})

    return {
        "success": True,
        "pattern": pattern,
        "total_found": len(lines),
        "returned": len(matches),
        "matches": matches,
        "truncated": len(lines) > max_results
    }


@mcp.tool()
def git_worktree(
    action: Literal["list", "add", "remove", "prune"] = "list",
    path: Optional[str] = None,
    branch: Optional[str] = None,
    repo_path: Optional[str] = None
) -> Dict[str, Any]:
    """
    Manage Git worktrees: 'list', 'add', 'remove', 'prune'.
    Allows AI agents to work in isolated branch directories without disturbing the user's active editor.
    
    Args:
        action: Worktree action ('list', 'add', 'remove', 'prune').
        path: Worktree directory path (required for 'add' and 'remove').
        branch: Branch to checkout in the new worktree (for 'add').
        repo_path: Optional repository workspace path or bookmark alias.
    """
    if not is_git_installed():
        return get_git_missing_guidance()

    cwd = resolve_repo_path(repo_path)
    act = action.lower()

    if act == "list":
        res = run_git_command(["worktree", "list"], cwd=cwd)
        lines = res.get("stdout", "").splitlines()
        worktrees = []
        for ln in lines:
            parts = ln.split()
            if len(parts) >= 2:
                worktrees.append({
                    "path": parts[0],
                    "commit": parts[1],
                    "branch": parts[2].strip("[]") if len(parts) > 2 else "detached"
                })
        return {"success": True, "worktrees": worktrees}

    if act == "add":
        if not path:
            return {"success": False, "error": "Worktree directory path is required."}
        args = ["worktree", "add", path]
        if branch:
            args.append(branch)
        res = run_git_command(args, cwd=cwd)
        return {"success": res.get("success"), "output": res.get("stdout") or res.get("stderr")}

    if act == "remove":
        if not path:
            return {"success": False, "error": "Worktree path is required to remove."}
        res = run_git_command(["worktree", "remove", path], cwd=cwd)
        return {"success": res.get("success"), "output": res.get("stdout") or res.get("stderr")}

    if act == "prune":
        res = run_git_command(["worktree", "prune"], cwd=cwd)
        return {"success": res.get("success"), "output": res.get("stdout") or res.get("stderr")}

    return {"success": False, "error": f"Unknown worktree action: '{action}'. Use list, add, remove, or prune."}


@mcp.tool()
def git_config(
    action: Literal["get", "set", "unset", "list"] = "get",
    key: Optional[str] = None,
    value: Optional[str] = None,
    scope: Literal["global", "local", "system"] = "global",
    repo_path: Optional[str] = None
) -> Dict[str, Any]:
    """
    Inspect or configure Git identity and settings (e.g. user.name, user.email, core.autocrlf).
    
    Args:
        action: Config action ('get', 'set', 'unset', 'list').
        key: Git configuration key (e.g. 'user.name', 'core.autocrlf').
        value: Value to set (required for 'set').
        scope: Configuration scope ('global', 'local', 'system').
        repo_path: Optional repository workspace path or bookmark alias.
    """
    if not is_git_installed():
        return get_git_missing_guidance()

    cwd = resolve_repo_path(repo_path)
    act = action.lower()
    scope_flag = f"--{scope}"

    if act in ("get", "list") and not key:
        res = run_git_command(["config", "--list", scope_flag], cwd=cwd)
        cfg = dict(line.split("=", 1) for line in res.get("stdout", "").splitlines() if "=" in line)
        return {"success": True, "scope": scope, "config": cfg}

    if act == "get":
        if not key:
            return {"success": False, "error": "Key is required for 'get' action."}
        res = run_git_command(["config", scope_flag, key], cwd=cwd)
        return {"success": res.get("success"), "key": key, "value": res.get("stdout", "").strip(), "scope": scope}

    if act == "set":
        if not key or value is None:
            return {"success": False, "error": "Both key and value are required to set git config."}
        res = run_git_command(["config", scope_flag, key, value], cwd=cwd)
        return {"success": res.get("success"), "key": key, "value": value, "scope": scope}

    if act == "unset":
        if not key:
            return {"success": False, "error": "Key is required to unset git config."}
        res = run_git_command(["config", scope_flag, "--unset", key], cwd=cwd)
        return {"success": res.get("success"), "key": key, "scope": scope}

    return {"success": False, "error": f"Unknown config action: '{action}'. Use get, set, unset, or list."}


@mcp.tool()
def git_conflict_resolve(
    action: Literal["status", "abort", "continue"] = "status",
    mode: Optional[str] = None,
    repo_path: Optional[str] = None
) -> Dict[str, Any]:
    """
    Detect and manage in-progress merge, rebase, or cherry-pick conflicts.
    
    Args:
        action: Conflict action ('status', 'abort', 'continue').
        mode: Optional operation override ('merge', 'rebase', 'cherry-pick').
        repo_path: Optional repository workspace path or bookmark alias.
    """
    if not is_git_installed():
        return get_git_missing_guidance()

    cwd = resolve_repo_path(repo_path)
    is_merging = (cwd / ".git" / "MERGE_HEAD").exists()
    is_rebasing = (cwd / ".git" / "rebase-apply").exists() or (cwd / ".git" / "rebase-merge").exists()
    is_cherry_picking = (cwd / ".git" / "CHERRY_PICK_HEAD").exists()

    act = action.lower()
    if act == "status":
        res = run_git_command(["diff", "--name-only", "--diff-filter=U"], cwd=cwd)
        conflicted = res.get("stdout", "").splitlines()
        return {
            "success": True,
            "in_conflict": len(conflicted) > 0 or is_merging or is_rebasing or is_cherry_picking,
            "merging": is_merging,
            "rebasing": is_rebasing,
            "cherry_picking": is_cherry_picking,
            "conflicted_files": conflicted
        }

    if act == "abort":
        cmd_type = mode or ("merge" if is_merging else ("rebase" if is_rebasing else "cherry-pick"))
        res = run_git_command([cmd_type, "--abort"], cwd=cwd)
        return {"success": res.get("success"), "aborted": cmd_type, "output": res.get("stdout") or res.get("stderr")}

    if act == "continue":
        cmd_type = mode or ("rebase" if is_rebasing else "merge")
        res = run_git_command([cmd_type, "--continue"], cwd=cwd)
        return {"success": res.get("success"), "output": res.get("stdout") or res.get("stderr")}

    return {"success": False, "error": f"Unknown action: '{action}'. Use status, abort, or continue."}


@mcp.tool()
def git_cherry_pick(
    commit_hash: str,
    no_commit: bool = False,
    repo_path: Optional[str] = None
) -> Dict[str, Any]:
    """
    Apply the changes introduced by an existing commit to the current branch.
    Detects cherry-pick conflicts and provides clean resolution guidance.
    
    Args:
        commit_hash: The SHA-1 hash or reference of the commit to cherry-pick.
        no_commit: Apply changes to working tree and index without creating a commit (default False).
        repo_path: Optional repository workspace path or bookmark alias.
    """
    if not is_git_installed():
        return get_git_missing_guidance()

    cwd = resolve_repo_path(repo_path)
    args = ["cherry-pick"]
    if no_commit:
        args.append("-n")
    args.append(commit_hash)

    res = run_git_command(args, cwd=cwd)
    if not res.get("success"):
        err = res.get("stderr") or res.get("stdout") or ""
        is_conflict = "conflict" in err.lower() or (cwd / ".git" / "CHERRY_PICK_HEAD").exists()
        return {
            "success": False,
            "commit_hash": commit_hash,
            "in_conflict": is_conflict,
            "error": err,
            "resolution": "Resolve conflicted files and run 'git_conflict_resolve(action=\"continue\")' or abort with 'git_conflict_resolve(action=\"abort\")'." if is_conflict else None
        }

    return {
        "success": True,
        "commit_hash": commit_hash,
        "output": res.get("stdout") or "Commit cherry-picked successfully.",
        "message": f"Successfully cherry-picked {commit_hash} onto current branch."
    }


@mcp.tool()
def git_clean_untracked(
    dry_run: bool = True,
    remove_directories: bool = True,
    repo_path: Optional[str] = None
) -> Dict[str, Any]:
    """
    Clean untracked files and build artifacts safely.
    Defaults to dry_run=True to prevent accidental loss of uncommitted work.
    
    Args:
        dry_run: If True (default), only lists files that WOULD be removed without deleting anything.
        remove_directories: Also remove untracked directories (-d flag).
        repo_path: Optional repository workspace path or bookmark alias.
    """
    if not is_git_installed():
        return get_git_missing_guidance()

    cwd = resolve_repo_path(repo_path)
    args = ["clean"]
    if dry_run:
        args.append("-n")
    else:
        args.append("-f")

    if remove_directories:
        args.append("-d")

    res = run_git_command(args, cwd=cwd)
    lines = res.get("stdout", "").splitlines()
    capped = lines[:100]

    return {
        "success": res.get("success"),
        "dry_run": dry_run,
        "files_count": len(lines),
        "files": capped,
        "truncated": len(lines) > 100,
        "notice": "Dry run mode: no files were deleted. Pass dry_run=False to delete these files." if dry_run else f"Cleaned {len(lines)} untracked item(s)."
    }


# ==============================================================================
# 4. Remote GitHub Operations via 'gh' CLI (12 Tools)
# ==============================================================================

@mcp.tool()
def gh_auth_status() -> Dict[str, Any]:
    """
    Check GitHub CLI authentication status, active account, and protocol scopes.
    """
    if not is_gh_installed():
        return get_gh_missing_guidance()

    res = run_gh_command(["auth", "status"], cwd=resolve_repo_path())
    out = res.get("stderr") or res.get("stdout")
    return {
        "success": res.get("success"),
        "raw_status": out,
        "is_logged_in": res.get("success") or "Logged in to" in out
    }


@mcp.tool()
def gh_switch_account(username: str) -> Dict[str, Any]:
    """
    Switch active GitHub CLI account if multiple accounts are configured.
    
    Args:
        username: GitHub account username to switch to.
    """
    if not is_gh_installed():
        return get_gh_missing_guidance()

    res = run_gh_command(["auth", "switch", "--user", username], cwd=resolve_repo_path())
    return {
        "success": res.get("success"),
        "output": res.get("stdout") or res.get("stderr")
    }


@mcp.tool()
def gh_pr_list(
    state: Literal["open", "closed", "merged", "all"] = "open",
    limit: int = 20,
    repo_path: Optional[str] = None
) -> Dict[str, Any]:
    """
    List pull requests for the repository with status, branch names, and authors.
    
    Args:
        state: Pull request state ('open', 'closed', 'merged', 'all').
        limit: Maximum number of PRs to return (default 20, max 50).
        repo_path: Optional repository workspace path or bookmark alias.
    """
    if not is_gh_installed():
        return get_gh_missing_guidance()

    cwd = resolve_repo_path(repo_path)
    lim = min(max(1, limit), 50)
    res = run_gh_command([
        "pr", "list",
        "--state", state,
        "--limit", str(lim),
        "--json", "number,title,state,headRefName,baseRefName,author,isDraft,url,updatedAt"
    ], cwd=cwd)

    if not res.get("success"):
        return {"success": False, "error": res.get("stderr") or res.get("stdout")}

    try:
        prs = json.loads(res.get("stdout", "[]"))
        return {"success": True, "count": len(prs), "pull_requests": prs}
    except Exception as e:
        return {"success": False, "error": f"Failed to parse PR list JSON: {str(e)}"}


@mcp.tool()
def gh_pr_view(
    pr_number: int,
    repo_path: Optional[str] = None
) -> Dict[str, Any]:
    """
    View complete details of a pull request (title, body, author, reviews, checks, mergeable status).
    
    Args:
        pr_number: Pull request number.
        repo_path: Optional repository workspace path or bookmark alias.
    """
    if not is_gh_installed():
        return get_gh_missing_guidance()

    cwd = resolve_repo_path(repo_path)
    res = run_gh_command([
        "pr", "view", str(pr_number),
        "--json", "number,title,body,state,author,headRefName,baseRefName,mergeable,reviewDecision,statusCheckRollup,url"
    ], cwd=cwd)

    if not res.get("success"):
        return {"success": False, "error": res.get("stderr") or res.get("stdout")}

    try:
        pr_data = json.loads(res.get("stdout", "{}"))
        return {"success": True, "pull_request": pr_data}
    except Exception as e:
        return {"success": False, "error": f"Failed to parse PR JSON: {str(e)}"}


@mcp.tool()
def gh_pr_diff(
    pr_number: int,
    max_lines: int = 250,
    repo_path: Optional[str] = None
) -> Dict[str, Any]:
    """
    View token-capped diff of a remote GitHub Pull Request.
    
    Args:
        pr_number: Pull request number.
        max_lines: Maximum diff lines to return (default 250).
        repo_path: Optional repository workspace path or bookmark alias.
    """
    if not is_gh_installed():
        return get_gh_missing_guidance()

    cwd = resolve_repo_path(repo_path)
    res = run_gh_command(["pr", "diff", str(pr_number)], cwd=cwd)
    if not res.get("success"):
        return {"success": False, "error": res.get("stderr") or res.get("stdout")}

    capped = _truncate_output(res.get("stdout", ""), max_lines=max_lines)
    return {
        "success": True,
        "pr_number": pr_number,
        "diff": capped["content"],
        "lines": capped["returned_lines"],
        "truncated": capped["truncated"]
    }


@mcp.tool()
def gh_pr_checkout(
    pr_number: int,
    repo_path: Optional[str] = None
) -> Dict[str, Any]:
    """
    Check out a GitHub Pull Request branch locally in the Git repository.
    
    Args:
        pr_number: Pull request number to checkout locally.
        repo_path: Optional repository workspace path or bookmark alias.
    """
    if not is_gh_installed():
        return get_gh_missing_guidance()

    cwd = resolve_repo_path(repo_path)
    res = run_gh_command(["pr", "checkout", str(pr_number)], cwd=cwd)
    return {
        "success": res.get("success"),
        "output": res.get("stdout") or res.get("stderr")
    }


@mcp.tool()
def gh_pr_action(
    pr_number: int,
    action: Literal["approve", "merge", "close", "reopen"],
    comment: Optional[str] = None,
    repo_path: Optional[str] = None
) -> Dict[str, Any]:
    """
    Perform Pull Request lifecycle actions: 'approve', 'merge', 'close', 'reopen'.
    
    Args:
        pr_number: Pull request number.
        action: Lifecycle action ('approve', 'merge', 'close', 'reopen').
        comment: Optional review or closure comment.
        repo_path: Optional repository workspace path or bookmark alias.
    """
    if not is_gh_installed():
        return get_gh_missing_guidance()

    cwd = resolve_repo_path(repo_path)
    act = action.lower()

    if act == "approve":
        args = ["pr", "review", str(pr_number), "--approve"]
        if comment:
            args += ["--body", comment]
        res = run_gh_command(args, cwd=cwd)
        return {"success": res.get("success"), "output": res.get("stdout") or res.get("stderr")}

    if act == "merge":
        res = run_gh_command(["pr", "merge", str(pr_number), "--auto", "--merge"], cwd=cwd)
        return {"success": res.get("success"), "output": res.get("stdout") or res.get("stderr")}

    if act == "close":
        args = ["pr", "close", str(pr_number)]
        if comment:
            args += ["--comment", comment]
        res = run_gh_command(args, cwd=cwd)
        return {"success": res.get("success"), "output": res.get("stdout") or res.get("stderr")}

    if act == "reopen":
        res = run_gh_command(["pr", "reopen", str(pr_number)], cwd=cwd)
        return {"success": res.get("success"), "output": res.get("stdout") or res.get("stderr")}

    return {"success": False, "error": f"Unknown PR action '{action}'. Use approve, merge, close, or reopen."}


@mcp.tool()
def gh_pr_checks(
    pr_number: int,
    watch: bool = False,
    repo_path: Optional[str] = None
) -> Dict[str, Any]:
    """
    Inspect individual GitHub Actions CI/CD step statuses, check runs, and failure logs for a Pull Request.
    
    Args:
        pr_number: Pull request number.
        watch: If True, waits for checks to finish before returning (timeout 30s).
        repo_path: Optional repository workspace path or bookmark alias.
    """
    if not is_gh_installed():
        return get_gh_missing_guidance()

    cwd = resolve_repo_path(repo_path)
    args = ["pr", "checks", str(pr_number), "--json", "name,state,status,workflow,description,link,event,bucket"]
    if watch:
        args.append("--watch")

    res = run_gh_command(args, cwd=cwd)
    if not res.get("success"):
        # Fallback to standard text output if json is unsupported on older gh versions
        raw_res = run_gh_command(["pr", "checks", str(pr_number)], cwd=cwd)
        return {
            "success": raw_res.get("success"),
            "pr_number": pr_number,
            "raw_checks": raw_res.get("stdout") or raw_res.get("stderr")
        }

    try:
        checks_data = json.loads(res.get("stdout", "[]"))
        failed_checks = [c for c in checks_data if c.get("state") in ("FAILURE", "CANCELLED", "ERROR") or c.get("status") == "fail"]
        return {
            "success": True,
            "pr_number": pr_number,
            "checks_count": len(checks_data),
            "failed_count": len(failed_checks),
            "all_passing": len(failed_checks) == 0,
            "checks": checks_data,
            "failed_checks": failed_checks if failed_checks else None
        }
    except Exception as e:
        return {"success": False, "error": f"Failed to parse PR checks JSON: {str(e)}"}


@mcp.tool()
def gh_issue_list(
    state: Literal["open", "closed", "all"] = "open",
    limit: int = 20,
    assignee: Optional[str] = None,
    labels: Optional[List[str]] = None,
    repo_path: Optional[str] = None
) -> Dict[str, Any]:
    """
    Search and list GitHub issues with filters (assignee, label, state).
    
    Args:
        state: Issue state ('open', 'closed', 'all').
        limit: Maximum number of issues to return (default 20, max 50).
        assignee: Optional GitHub username filter.
        labels: Optional list of label names to filter by.
        repo_path: Optional repository workspace path or bookmark alias.
    """
    if not is_gh_installed():
        return get_gh_missing_guidance()

    cwd = resolve_repo_path(repo_path)
    args = [
        "issue", "list",
        "--state", state,
        "--limit", str(min(max(1, limit), 50)),
        "--json", "number,title,state,author,labels,assignees,url,updatedAt"
    ]
    if assignee:
        args += ["--assignee", assignee]
    if labels:
        for lbl in labels:
            args += ["--label", lbl]

    res = run_gh_command(args, cwd=cwd)
    if not res.get("success"):
        return {"success": False, "error": res.get("stderr") or res.get("stdout")}

    try:
        issues = json.loads(res.get("stdout", "[]"))
        return {"success": True, "count": len(issues), "issues": issues}
    except Exception as e:
        return {"success": False, "error": f"Failed to parse issues JSON: {str(e)}"}


@mcp.tool()
def gh_issue_view(
    issue_number: int,
    repo_path: Optional[str] = None
) -> Dict[str, Any]:
    """
    View complete GitHub issue details including body, labels, comments, and assignees.
    
    Args:
        issue_number: GitHub issue number.
        repo_path: Optional repository workspace path or bookmark alias.
    """
    if not is_gh_installed():
        return get_gh_missing_guidance()

    cwd = resolve_repo_path(repo_path)
    res = run_gh_command([
        "issue", "view", str(issue_number),
        "--json", "number,title,body,state,author,labels,assignees,comments,url"
    ], cwd=cwd)

    if not res.get("success"):
        return {"success": False, "error": res.get("stderr") or res.get("stdout")}

    try:
        data = json.loads(res.get("stdout", "{}"))
        return {"success": True, "issue": data}
    except Exception as e:
        return {"success": False, "error": f"Failed to parse issue JSON: {str(e)}"}


@mcp.tool()
def gh_issue_create(
    title: str,
    body: str,
    labels: Optional[List[str]] = None,
    assignees: Optional[List[str]] = None,
    repo_path: Optional[str] = None
) -> Dict[str, Any]:
    """
    Create a new GitHub issue with title, description, labels, and assignees.
    
    Args:
        title: Issue title.
        body: Issue description body.
        labels: Optional list of label strings to attach.
        assignees: Optional list of GitHub usernames to assign.
        repo_path: Optional repository workspace path or bookmark alias.
    """
    if not is_gh_installed():
        return get_gh_missing_guidance()

    cwd = resolve_repo_path(repo_path)
    args = ["issue", "create", "--title", title, "--body", body]
    if labels:
        for lbl in labels:
            args += ["--label", lbl]
    if assignees:
        for a in assignees:
            args += ["--assignee", a]

    res = run_gh_command(args, cwd=cwd)
    if not res.get("success"):
        return {"success": False, "error": res.get("stderr") or res.get("stdout")}

    return {
        "success": True,
        "issue_url": res.get("stdout", "").strip(),
        "message": "Issue created successfully."
    }


@mcp.tool()
def gh_issue_comment(
    issue_number: int,
    comment: str,
    repo_path: Optional[str] = None
) -> Dict[str, Any]:
    """
    Post a comment on a GitHub issue or pull request.
    
    Args:
        issue_number: GitHub issue or PR number.
        comment: Markdown comment content.
        repo_path: Optional repository workspace path or bookmark alias.
    """
    if not is_gh_installed():
        return get_gh_missing_guidance()

    cwd = resolve_repo_path(repo_path)
    res = run_gh_command(["issue", "comment", str(issue_number), "--body", comment], cwd=cwd)
    return {
        "success": res.get("success"),
        "output": res.get("stdout") or res.get("stderr")
    }


@mcp.tool()
def gh_run_status(
    limit: int = 10,
    repo_path: Optional[str] = None
) -> Dict[str, Any]:
    """
    Inspect GitHub Actions CI/CD workflows and recent run outcomes.
    
    Args:
        limit: Maximum number of workflow runs to retrieve (default 10, max 20).
        repo_path: Optional repository workspace path or bookmark alias.
    """
    if not is_gh_installed():
        return get_gh_missing_guidance()

    cwd = resolve_repo_path(repo_path)
    res = run_gh_command([
        "run", "list",
        "--limit", str(min(max(1, limit), 20)),
        "--json", "databaseId,name,status,conclusion,event,headBranch,url,createdAt"
    ], cwd=cwd)

    if not res.get("success"):
        return {"success": False, "error": res.get("stderr") or res.get("stdout")}

    try:
        runs = json.loads(res.get("stdout", "[]"))
        return {"success": True, "count": len(runs), "runs": runs}
    except Exception as e:
        return {"success": False, "error": f"Failed to parse runs JSON: {str(e)}"}


@mcp.tool()
def gh_gist_create(
    description: str,
    files: Dict[str, str],
    public: bool = False
) -> Dict[str, Any]:
    """
    Create a GitHub Gist with multiple files to share snippets, patches, or logs.
    
    Args:
        description: Gist description.
        files: Dictionary mapping filename to string content.
        public: If True, creates public gist (default False / secret).
    """
    if not is_gh_installed():
        return get_gh_missing_guidance()

    import tempfile
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        file_args = []
        for fname, content in files.items():
            f_dest = tmp_path / fname
            f_dest.write_text(content, encoding="utf-8")
            file_args.append(str(f_dest))

        args = ["gist", "create", "--desc", description] + file_args
        if public:
            args.append("--public")

        res = run_gh_command(args, cwd=Path.cwd())
        if not res.get("success"):
            return {"success": False, "error": res.get("stderr") or res.get("stdout")}

        return {
            "success": True,
            "gist_url": res.get("stdout", "").strip(),
            "message": "Gist created successfully."
        }


@mcp.tool()
def gh_search(
    kind: Literal["issues", "prs", "code", "repos"] = "issues",
    query: str = "",
    limit: int = 15,
    repo_path: Optional[str] = None
) -> Dict[str, Any]:
    """
    Search GitHub globally or within the current repository (kind: 'issues', 'prs', 'code', 'repos').
    
    Args:
        kind: Search entity ('issues', 'prs', 'code', 'repos').
        query: Search keywords or query string.
        limit: Maximum results to return (default 15, max 30).
        repo_path: Optional repository workspace path or bookmark alias.
    """
    if not is_gh_installed():
        return get_gh_missing_guidance()

    cwd = resolve_repo_path(repo_path)
    k = kind.lower()
    if k not in ("issues", "prs", "code", "repos"):
        return {"success": False, "error": f"Invalid search kind '{kind}'. Use issues, prs, code, or repos."}

    args = ["search", k, query, "--limit", str(min(max(1, limit), 30))]
    res = run_gh_command(args, cwd=cwd)
    return {
        "success": res.get("success"),
        "results": res.get("stdout") or res.get("stderr")
    }


@mcp.tool()
def gh_release_list(
    limit: int = 10,
    repo_path: Optional[str] = None
) -> Dict[str, Any]:
    """
    List GitHub releases, tags, published dates, and release notes for the repository.
    
    Args:
        limit: Maximum number of releases to return (default 10, max 30).
        repo_path: Optional repository workspace path or bookmark alias.
    """
    if not is_gh_installed():
        return get_gh_missing_guidance()

    cwd = resolve_repo_path(repo_path)
    lim = min(max(1, limit), 30)
    res = run_gh_command([
        "release", "list",
        "--limit", str(lim),
        "--json", "tagName,name,isDraft,isPrerelease,publishedAt,url"
    ], cwd=cwd)

    if not res.get("success"):
        return {"success": False, "error": res.get("stderr") or res.get("stdout")}

    try:
        releases = json.loads(res.get("stdout", "[]"))
        return {
            "success": True,
            "releases_count": len(releases),
            "releases": releases
        }
    except Exception as e:
        return {"success": False, "error": f"Failed to parse release JSON: {str(e)}"}


@mcp.tool()
def gh_release_create(
    tag_name: str,
    title: Optional[str] = None,
    notes: Optional[str] = None,
    generate_notes: bool = False,
    draft: bool = False,
    prerelease: bool = False,
    assets: Optional[List[str]] = None,
    repo_path: Optional[str] = None
) -> Dict[str, Any]:
    """
    Create a new GitHub Release for a tag and optionally upload release binary/wheel assets.
    
    Args:
        tag_name: Git tag for the release (e.g. 'v1.0.0').
        title: Release title (defaults to tag_name if omitted).
        notes: Custom markdown release notes or changelog.
        generate_notes: If True, automatically generate release notes from commits and PRs.
        draft: If True, creates the release as a draft.
        prerelease: If True, marks the release as a pre-release.
        assets: Optional list of local file paths (binaries, wheels, tarballs) to upload to the release.
        repo_path: Optional repository workspace path or bookmark alias.
    """
    if not is_gh_installed():
        return get_gh_missing_guidance()

    cwd = resolve_repo_path(repo_path)
    args = ["release", "create", tag_name]
    if title:
        args += ["--title", title]
    if notes:
        args += ["--notes", notes]
    if generate_notes:
        args.append("--generate-notes")
    if draft:
        args.append("--draft")
    if prerelease:
        args.append("--prerelease")
    if assets:
        args += assets

    res = run_gh_command(args, cwd=cwd)
    if not res.get("success"):
        return {"success": False, "error": res.get("stderr") or res.get("stdout")}

    return {
        "success": True,
        "tag": tag_name,
        "release_url": res.get("stdout", "").strip(),
        "uploaded_assets": assets if assets else None,
        "message": f"Successfully created GitHub Release for {tag_name}."
    }


@mcp.tool()
def gh_pr_review_comments(
    pr_number: int,
    limit: int = 30,
    repo_path: Optional[str] = None
) -> Dict[str, Any]:
    """
    Retrieve inline code review comments and discussion threads on a Pull Request.
    
    Args:
        pr_number: Pull request number.
        limit: Maximum number of review comments to return (default 30, max 60).
        repo_path: Optional repository workspace path or bookmark alias.
    """
    if not is_gh_installed():
        return get_gh_missing_guidance()

    cwd = resolve_repo_path(repo_path)
    lim = min(max(1, limit), 60)

    # Query PR review comments via gh api
    remote_info = get_remote_github_info(cwd)
    if not remote_info or not remote_info.get("owner") or not remote_info.get("repo"):
        return {"success": False, "error": "Could not determine GitHub owner/repo from git remote origin."}

    owner = remote_info["owner"]
    repo = remote_info["repo"]
    endpoint = f"repos/{owner}/{repo}/pulls/{pr_number}/comments?per_page={lim}"

    res = run_gh_command(["api", endpoint], cwd=cwd)
    if not res.get("success"):
        return {"success": False, "error": res.get("stderr") or res.get("stdout")}

    try:
        raw_comments = json.loads(res.get("stdout", "[]"))
        cleaned_comments = []
        for c in raw_comments:
            cleaned_comments.append({
                "id": c.get("id"),
                "path": c.get("path"),
                "line": c.get("line") or c.get("original_line"),
                "author": c.get("user", {}).get("login"),
                "body": (c.get("body") or "")[:500],
                "created_at": c.get("created_at"),
                "url": c.get("html_url")
            })

        return {
            "success": True,
            "pr_number": pr_number,
            "comments_count": len(cleaned_comments),
            "comments": cleaned_comments
        }
    except Exception as e:
        return {"success": False, "error": f"Failed to parse review comments: {str(e)}"}


@mcp.tool()
def gh_api(
    endpoint: str,
    method: str = "GET",
    fields: Optional[Dict[str, Any]] = None,
    max_chars: int = 15000,
    repo_path: Optional[str] = None
) -> Dict[str, Any]:
    """
    Direct GitHub REST/GraphQL API caller via 'gh api' with automatic context window protection.
    
    Args:
        endpoint: GitHub API path (e.g. 'user', 'repos/:owner/:repo/commits').
        method: HTTP method (default 'GET').
        fields: Optional dictionary of query/body parameters.
        max_chars: Maximum character limit on response payload to preserve context (default 15000).
        repo_path: Optional repository workspace path or bookmark alias.
    """
    if not is_gh_installed():
        return get_gh_missing_guidance()

    cwd = resolve_repo_path(repo_path)
    args = ["api", endpoint, "-X", method.upper()]
    if fields:
        for k, v in fields.items():
            args += ["-F", f"{k}={v}"]

    res = run_gh_command(args, cwd=cwd)
    if not res.get("success"):
        return {"success": False, "error": res.get("stderr") or res.get("stdout")}

    raw_out = res.get("stdout", "")
    capped = _truncate_output(raw_out, max_lines=250, max_chars=max_chars)

    try:
        data = json.loads(capped["content"]) if not capped["truncated"] else json.loads(raw_out[:max_chars])
        return {
            "success": True,
            "truncated": capped["truncated"],
            "response": data,
            "notice": capped.get("notice")
        }
    except Exception:
        return {
            "success": True,
            "truncated": capped["truncated"],
            "raw_response": capped["content"],
            "notice": capped.get("notice")
        }


# ==============================================================================
# Standalone execution
# ==============================================================================

if __name__ == "__main__":
    mcp.run()
