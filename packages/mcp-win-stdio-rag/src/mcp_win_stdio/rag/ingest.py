#!/usr/bin/env python3
"""
Universal Ingestion Engine for Local Repositories and Zero-Clone Remote Git Streams.
Supports Next.js-style content-addressable SHA-256 caching and Graphify AST integration.
"""

import hashlib
import io
import json
import os
import re
import urllib.request
import zipfile
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

# File extensions to index by default
DEFAULT_DOC_EXTENSIONS = {".md", ".mdx", ".rst", ".txt", ".adoc"}
DEFAULT_CODE_EXTENSIONS = {
    ".py",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".mjs",
    ".cjs",
    ".go",
    ".rs",
    ".java",
    ".cpp",
    ".c",
    ".h",
    ".hpp",
    ".cs",
    ".rb",
    ".php",
    ".swift",
    ".kt",
    ".sql",
    ".sh",
}
DEFAULT_CONFIG_EXTENSIONS = {".json", ".yaml", ".yml", ".toml", ".prisma", ".graphql"}

IGNORED_DIRS = {
    ".git",
    ".svn",
    ".hg",
    "node_modules",
    "dist",
    "build",
    "out",
    ".next",
    ".nuxt",
    ".output",
    "target",
    "bin",
    "obj",
    "__pycache__",
    ".cache",
    "coverage",
    ".turbo",
    "venv",
    ".venv",
    "env",
    ".env",
    "site-packages",
    ".idea",
    ".vscode",
    ".gemini",
    ".cursor",
    "vendor",
    "vendors",
    "thirdparty",
    "third_party",
    "bower_components",
    "locale",
    "locales",
    "translations",
    "cache",
    "tmp",
    "temp",
    "var",
    "storage",
}

IGNORED_FILE_SUFFIXES = (
    ".min.js",
    ".min.css",
    ".bundle.js",
    ".map",
    ".lock",
    "package-lock.json",
    "composer.lock",
    "yarn.lock",
    "pnpm-lock.yaml",
    ".po",
    ".mo",
    ".pot",
    ".svg",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".ico",
    ".woff",
    ".woff2",
    ".ttf",
    ".eot",
)


def compute_sha256(content: str) -> str:
    """Compute deterministic SHA-256 hash of text content."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def is_stub_chunk(title: str, text: str) -> bool:
    """Detect if chunk is pure frontmatter or redirect stub with no meaningful content."""
    t_lower = title.strip().lower()
    if t_lower in ("prettier-ignore", "frontmatter", "metadata"):
        return True
    words = text.split()
    if len(words) < 25:
        txt_lower = text.lower()
        if "deprecation_redirects:" in txt_lower or "permalink:" in txt_lower or "layout:" in txt_lower:
            return True
        if "redirect" in t_lower and ("redirect" in txt_lower or "moved to" in txt_lower):
            return True
    return False


def strip_frontmatter(content: str) -> Tuple[str, int]:
    """Strip YAML frontmatter at the beginning of markdown, returning content and line offset."""
    lines = content.splitlines()
    if lines and lines[0].strip() == "---":
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                return "\n".join(lines[i + 1 :]).lstrip("\n"), i + 1
    return content, 0


def chunk_markdown_by_headings(content: str, rel_path: str, base_url_prefix: str = "") -> List[Dict[str, Any]]:
    """
    Split markdown document into section-aware chunks respecting #, ##, ### headers.
    Generates anchor links for each section and filters out frontmatter stubs.
    """
    cleaned_content, offset = strip_frontmatter(content)
    lines = cleaned_content.splitlines()
    chunks: List[Dict[str, Any]] = []

    current_title = Path(rel_path).stem.replace("-", " ").replace("_", " ").title()
    current_anchor = ""
    current_lines: List[str] = []
    start_line = offset + 1

    header_regex = re.compile(r"^(#{1,4})\s+(.+)$")

    for idx, line in enumerate(lines, start=offset + 1):
        match = header_regex.match(line)
        if match:
            # Flush previous section
            if current_lines:
                sec_text = "\n".join(current_lines).strip()
                if sec_text and not is_stub_chunk(current_title, sec_text):
                    anchor_url = (
                        f"{base_url_prefix}#{current_anchor}"
                        if (base_url_prefix and current_anchor)
                        else (
                            f"{base_url_prefix}#L{start_line}-L{idx - 1}"
                            if base_url_prefix
                            else f"{rel_path}#L{start_line}-L{idx - 1}"
                        )
                    )
                    chunks.append(
                        {
                            "section_title": current_title,
                            "anchor_id": current_anchor,
                            "anchor_url": anchor_url,
                            "file_path": rel_path,
                            "line_start": start_line,
                            "line_end": idx - 1,
                            "text": f"## {current_title}\n{sec_text}",
                            "word_count": len(sec_text.split()),
                        }
                    )

            # Start new section
            heading_text = match.group(2).strip()
            current_title = heading_text
            current_anchor = re.sub(r"[^a-zA-Z0-9_-]+", "-", heading_text.lower()).strip("-")
            current_lines = [line]
            start_line = idx
        else:
            current_lines.append(line)

    # Flush final section
    if current_lines:
        sec_text = "\n".join(current_lines).strip()
        if sec_text and not is_stub_chunk(current_title, sec_text):
            anchor_url = (
                f"{base_url_prefix}#{current_anchor}"
                if (base_url_prefix and current_anchor)
                else (
                    f"{base_url_prefix}#L{start_line}-L{len(lines) + offset}"
                    if base_url_prefix
                    else f"{rel_path}#L{start_line}-L{len(lines) + offset}"
                )
            )
            chunks.append(
                {
                    "section_title": current_title,
                    "anchor_id": current_anchor,
                    "anchor_url": anchor_url,
                    "file_path": rel_path,
                    "line_start": start_line,
                    "line_end": len(lines) + offset,
                    "text": f"## {current_title}\n{sec_text}" if not sec_text.startswith("#") else sec_text,
                    "word_count": len(sec_text.split()),
                }
            )

    return chunks


def chunk_code_by_definitions(
    content: str, rel_path: str, base_url_prefix: str = "", max_chunk_lines: int = 60
) -> List[Dict[str, Any]]:
    """
    Split code files into logical chunks by classes, functions, traits, routes, or line windows with exact line spans.
    Preserves docblock comments and class/function context.
    """
    lines = content.splitlines()
    if not lines:
        return []

    # Regex for standard definitions across Python, JS/TS, PHP, Go, Rust, Java, C#
    def_regex = re.compile(
        r"^(?:async\s+)?(?:export\s+)?(?:default\s+)?(?:public\s+|private\s+|protected\s+|static\s+|abstract\s+|final\s+)*"
        r"(?:def\s+|class\s+|function\s+|interface\s+|trait\s+|type\s+|struct\s+|fn\s+|func\s+|enum\s+|namespace\s+|const\s+|Route::[a-zA-Z0-9_]+\s*\()"
        r"([a-zA-Z0-9_]+)?"
    )

    chunks: List[Dict[str, Any]] = []
    current_symbol = Path(rel_path).name
    current_lines: List[str] = []
    start_line = 1

    for idx, line in enumerate(lines, start=1):
        stripped = line.strip()
        match = def_regex.match(stripped)
        is_split_point = (match is not None and not stripped.startswith("const ") and len(current_lines) >= 12) or (
            len(current_lines) >= max_chunk_lines
        )

        if is_split_point and len(current_lines) >= 10:
            code_text = "\n".join(current_lines).strip()
            if code_text:
                anchor_url = (
                    f"{base_url_prefix}#L{start_line}-L{idx - 1}"
                    if base_url_prefix
                    else f"{rel_path}#L{start_line}-L{idx - 1}"
                )
                chunks.append(
                    {
                        "section_title": f"{current_symbol} ({rel_path}:{start_line})",
                        "anchor_id": f"L{start_line}-L{idx - 1}",
                        "anchor_url": anchor_url,
                        "file_path": rel_path,
                        "line_start": start_line,
                        "line_end": idx - 1,
                        "text": f"// File: {rel_path} (Lines {start_line}-{idx - 1})\n{code_text}",
                        "word_count": len(code_text.split()),
                    }
                )
            current_lines = [line]
            start_line = idx
            if match and match.group(1):
                current_symbol = match.group(1)
        else:
            current_lines.append(line)
            if match and match.group(1) and len(current_lines) == 1:
                current_symbol = match.group(1)

    # Flush remainder
    if current_lines:
        code_text = "\n".join(current_lines).strip()
        if code_text:
            anchor_url = (
                f"{base_url_prefix}#L{start_line}-L{len(lines)}"
                if base_url_prefix
                else f"{rel_path}#L{start_line}-L{len(lines)}"
            )
            chunks.append(
                {
                    "section_title": f"{current_symbol} ({rel_path}:{start_line})",
                    "anchor_id": f"L{start_line}-L{len(lines)}",
                    "anchor_url": anchor_url,
                    "file_path": rel_path,
                    "line_start": start_line,
                    "line_end": len(lines),
                    "text": f"// File: {rel_path} (Lines {start_line}-{len(lines)})\n{code_text}",
                    "word_count": len(code_text.split()),
                }
            )

    return chunks


def parse_github_url(url: str) -> Dict[str, str]:
    """Parse GitHub URL into owner, repo, branch, and subpath."""
    clean = url.strip().rstrip("/")
    # Match: https://github.com/owner/repo or https://github.com/owner/repo/tree/branch/subpath
    pattern = r"^https?://github\.com/([^/]+)/([^/]+)(?:/tree/([^/]+)(?:/(.+))?)?$"
    match = re.match(pattern, clean)
    if not match:
        raise ValueError(f"Invalid GitHub repository URL: '{url}'. Expected format 'https://github.com/owner/repo'")

    owner = match.group(1)
    repo = match.group(2).removesuffix(".git")
    branch = match.group(3) or ""
    subpath = match.group(4) or ""

    return {
        "owner": owner,
        "repo": repo,
        "branch": branch,
        "subpath": subpath.rstrip("/"),
        "full_name": f"{owner}/{repo}",
    }


def stream_github_repo_in_memory(
    repo_url: str,
    subpath: Optional[str] = None,
    allowed_extensions: Optional[Set[str]] = None,
    auth_token: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Stream and extract files from a GitHub repository in-memory via zipball without local git clone.
    Returns parsed files, commit SHA, and repository metadata.
    """
    meta = parse_github_url(repo_url)
    owner = meta["owner"]
    repo = meta["repo"]
    branch = meta["branch"]
    effective_subpath = (subpath or meta["subpath"] or "").strip("/")

    if allowed_extensions is None:
        allowed_extensions = DEFAULT_DOC_EXTENSIONS | DEFAULT_CODE_EXTENSIONS | DEFAULT_CONFIG_EXTENSIONS

    # 1. Fetch latest commit SHA for content caching
    commit_api_url = (
        f"https://api.github.com/repos/{owner}/{repo}/commits/{branch}"
        if branch
        else f"https://api.github.com/repos/{owner}/{repo}/commits/HEAD"
    )
    req_commit = urllib.request.Request(commit_api_url, headers={"User-Agent": "mws-rag-crawler/1.0"})
    if auth_token:
        req_commit.add_header("Authorization", f"token {auth_token}")

    latest_sha = ""
    try:
        with urllib.request.urlopen(req_commit, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            latest_sha = data.get("sha", "")
    except Exception:
        pass

    # 2. Stream zipball archive into memory
    zip_url = (
        f"https://api.github.com/repos/{owner}/{repo}/zipball/{branch}"
        if branch
        else f"https://api.github.com/repos/{owner}/{repo}/zipball"
    )
    req_zip = urllib.request.Request(zip_url, headers={"User-Agent": "mws-rag-crawler/1.0"})
    if auth_token:
        req_zip.add_header("Authorization", f"token {auth_token}")

    try:
        with urllib.request.urlopen(req_zip, timeout=60) as resp:
            final_url = resp.geturl()
            # If branch was not explicitly provided in URL, extract resolved branch from redirect URL
            if not branch:
                m = re.search(r"/refs/heads/(.+)$", final_url)
                if m:
                    branch = m.group(1)
                else:
                    branch = "main"
                meta["branch"] = branch
            zip_bytes = resp.read()
    except urllib.error.HTTPError as he:
        if he.code == 404:
            raise RuntimeError(
                f"GitHub repository or archive not found at '{zip_url}'. Verify the repository is public (or auth_token is supplied) and that the branch exists."
            ) from he
        elif he.code in (401, 403):
            raise RuntimeError(
                f"GitHub access denied ({he.code}) for '{zip_url}'. API rate limits may have been reached, or a private repo requires an auth_token."
            ) from he
        else:
            raise RuntimeError(f"HTTP error {he.code} while streaming repository from '{zip_url}': {he.reason}") from he
    except Exception as e:
        raise RuntimeError(f"Failed to stream GitHub repository from '{zip_url}': {e}") from e

    files_data: List[Dict[str, Any]] = []

    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
        for entry in z.infolist():
            if entry.is_dir() or entry.file_size == 0 or entry.file_size > 1_500_000:  # Skip files > 1.5MB
                continue

            # Zip root contains an outer prefix: owner-repo-sha/...
            parts = entry.filename.split("/", 1)
            if len(parts) < 2:
                continue
            rel_file_path = parts[1]

            # Filter by subpath if requested
            if effective_subpath and not rel_file_path.startswith(effective_subpath):
                continue

            ext = Path(rel_file_path).suffix.lower()
            if ext not in allowed_extensions:
                continue

            # Check ignored directories
            path_parts = set(rel_file_path.lower().replace("\\", "/").split("/"))
            if path_parts & IGNORED_DIRS:
                continue

            try:
                raw_bytes = z.read(entry)
                text_content = raw_bytes.decode("utf-8", errors="replace")
            except Exception:
                continue

            content_hash = compute_sha256(text_content)
            github_blob_url = f"https://github.com/{owner}/{repo}/blob/{branch}/{rel_file_path}"

            # Chunk document or code
            if ext in DEFAULT_DOC_EXTENSIONS:
                chunks = chunk_markdown_by_headings(text_content, rel_file_path, base_url_prefix=github_blob_url)
            else:
                chunks = chunk_code_by_definitions(text_content, rel_file_path, base_url_prefix=github_blob_url)

            files_data.append(
                {
                    "file_path": rel_file_path,
                    "content_hash": content_hash,
                    "github_url": github_blob_url,
                    "chunks": chunks,
                    "size_bytes": len(raw_bytes),
                    "is_doc": ext in DEFAULT_DOC_EXTENSIONS,
                }
            )

    return {"repo_meta": meta, "commit_sha": latest_sha, "total_files": len(files_data), "files": files_data}


ProgressCallback = Optional[Callable[[str, int, int, int, int, str], None]]


def scan_local_codebase(
    project_path: str,
    allowed_extensions: Optional[Set[str]] = None,
    cached_hashes: Optional[Dict[str, str]] = None,
    max_file_size: int = 1_000_000,
    progress_cb: ProgressCallback = None,
) -> Tuple[List[Dict[str, Any]], int, Set[str]]:
    """
    High-performance 5-phase scan of local directory tree with live phase & percentage telemetry.
    Returns: (files_to_update, unchanged_skipped_count, all_live_paths)
    """
    root_p = Path(project_path).resolve()
    if not root_p.exists():
        raise FileNotFoundError(f"Project directory not found: '{project_path}'")

    if allowed_extensions is None:
        allowed_extensions = DEFAULT_DOC_EXTENSIONS | DEFAULT_CODE_EXTENSIONS | DEFAULT_CONFIG_EXTENSIONS

    if cached_hashes is None:
        cached_hashes = {}

    # ---------------------------------------------------------
    # PHASE 1: DISCOVERY & DIRECTORY PRUNING
    # ---------------------------------------------------------
    if progress_cb:
        progress_cb("DISCOVERY", 1, 5, 0, 0, f"Scanning directory tree at {root_p.name}...")

    discovered_files: List[Tuple[Path, str, os.stat_result]] = []
    live_paths: Set[str] = set()

    for current_root, dirs, files in os.walk(root_p):
        # In-place directory pruning
        dirs[:] = [d for d in dirs if d.lower() not in IGNORED_DIRS and not d.startswith(".")]

        for fname in files:
            lower_fname = fname.lower()
            if any(lower_fname.endswith(suf) for suf in IGNORED_FILE_SUFFIXES):
                continue

            file_p = Path(current_root) / fname
            ext = file_p.suffix.lower()
            if ext not in allowed_extensions:
                continue

            try:
                st = file_p.stat()
                if st.st_size > max_file_size or st.st_size == 0:
                    continue
                rel_path = str(file_p.relative_to(root_p)).replace("\\", "/")
                live_paths.add(rel_path)
                discovered_files.append((file_p, rel_path, st))
            except Exception:
                continue

    total_discovered = len(discovered_files)
    if progress_cb:
        progress_cb(
            "DISCOVERY", 1, 5, total_discovered, total_discovered, f"Discovered {total_discovered} eligible files"
        )

    # ---------------------------------------------------------
    # PHASE 2: CACHE DIFF & NEXT.JS 0ms SKIP CHECK
    # ---------------------------------------------------------
    if progress_cb:
        progress_cb("CACHE_DIFF", 2, 5, 0, total_discovered, "Diffing content hashes against SQLite manifest...")

    pending_chunk_files: List[Tuple[str, str, str, int, bool]] = []
    unchanged_skipped = 0

    for idx, (file_p, rel_path, st) in enumerate(discovered_files, start=1):
        try:
            content = file_p.read_text(encoding="utf-8", errors="replace")
            content_hash = compute_sha256(content)

            if cached_hashes.get(rel_path) == content_hash:
                unchanged_skipped += 1
                continue

            ext = file_p.suffix.lower()
            is_doc = ext in DEFAULT_DOC_EXTENSIONS
            pending_chunk_files.append((rel_path, content, content_hash, st.st_size, is_doc))
        except Exception:
            continue

        if progress_cb and idx % 200 == 0:
            progress_cb("CACHE_DIFF", 2, 5, idx, total_discovered, f"Checked {idx}/{total_discovered} file hashes")

    if progress_cb:
        progress_cb(
            "CACHE_DIFF",
            2,
            5,
            total_discovered,
            total_discovered,
            f"Cache Diff: {unchanged_skipped} unchanged (0ms skip), {len(pending_chunk_files)} modified/new",
        )

    # ---------------------------------------------------------
    # PHASE 3: SEMANTIC DEFINITION CHUNKING
    # ---------------------------------------------------------
    total_to_chunk = len(pending_chunk_files)
    if progress_cb:
        progress_cb("SEMANTIC_CHUNKING", 3, 5, 0, total_to_chunk, f"Chunking {total_to_chunk} files...")

    files_to_update: List[Dict[str, Any]] = []
    for idx, (rel_path, content, content_hash, s_size, is_doc) in enumerate(pending_chunk_files, start=1):
        try:
            if is_doc:
                chunks = chunk_markdown_by_headings(content, rel_path)
            else:
                chunks = chunk_code_by_definitions(content, rel_path)

            files_to_update.append(
                {
                    "file_path": rel_path,
                    "content_hash": content_hash,
                    "chunks": chunks,
                    "size_bytes": s_size,
                    "is_doc": is_doc,
                }
            )
        except Exception:
            continue

        if progress_cb and (idx % 50 == 0 or idx == total_to_chunk):
            progress_cb(
                "SEMANTIC_CHUNKING", 3, 5, idx, total_to_chunk, f"Parsed {idx}/{total_to_chunk} files ({rel_path})"
            )

    return files_to_update, unchanged_skipped, live_paths
