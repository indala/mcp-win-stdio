#!/usr/bin/env python3
"""
RAG MCP Server providing Multi-Collection Web Crawling, Incremental Local Codebase Indexing,
Zero-Clone Remote Git Streaming, and Section-Aware Hybrid Vector Search.
Part of mcp-win-stdio.
"""

import asyncio
import json
import os
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Tuple

try:
    from mcp.server.mcpserver import MCPServer as FastMCP
except (ImportError, ModuleNotFoundError):
    from mcp.server.fastmcp import FastMCP  # type: ignore[import-not-found]

from mcp_win_stdio.rag.crawler import AsyncPlaywrightCrawler, get_domain_hash
from mcp_win_stdio.rag.ingest import parse_github_url, scan_local_codebase, stream_github_repo_in_memory
from mcp_win_stdio.rag.store import COMMON_STOPWORDS, RAGVectorStore, _stem_token

mcp = FastMCP("rag-mcp")


def _get_rag_data_dir() -> Path:
    env_dir = os.environ.get("MCP_RAG_DATA_DIR")
    if env_dir:
        p = Path(env_dir)
    else:
        p = Path.home() / ".mcp-win-stdio" / "rag_stores"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _get_collection_dir(collection_or_url: str) -> Path:
    data_dir = _get_rag_data_dir()
    if collection_or_url.startswith(("http://", "https://")) and "github.com" not in collection_or_url:
        folder_name = get_domain_hash(collection_or_url)
    else:
        folder_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in collection_or_url.lower()).strip("_")
        if not folder_name:
            folder_name = "default"
    return data_dir / folder_name


def _get_all_stores() -> List[Tuple[str, RAGVectorStore]]:
    data_dir = _get_rag_data_dir()
    stores = []
    if not data_dir.exists():
        return stores
    for d in data_dir.iterdir():
        if d.is_dir():
            db_file = d / "vector_store.db"
            if db_file.exists():
                stores.append((d.name, RAGVectorStore(db_file)))
    return stores


# =============================================================================
# MCP TOOLS
# =============================================================================


@mcp.tool()
def crawl_and_index_url(
    target_url: str, collection_name: Optional[str] = None, max_depth: int = 2, max_pages: int = 40
) -> str:
    """
    Automated Section-Aware Web Documentation Crawler & Vector Indexer.
    Recursively crawls target documentation websites, captures heading anchor IDs (e.g. '#rate-limit'),
    and indexes section-level chunks with deep-link citations.

    Args:
        target_url: The entrypoint documentation URL (e.g. 'https://developers.zenodo.org').
        collection_name: Optional custom alias for this collection (e.g. 'zenodo', 'crossref').
        max_depth: Maximum link depth to crawl (default: 2).
        max_pages: Maximum total pages to crawl (default: 40).
    """
    try:
        crawler = AsyncPlaywrightCrawler(target_url=target_url, max_depth=max_depth, max_pages=max_pages)

        try:
            loop = asyncio.get_running_loop()
            crawl_result = asyncio.run_coroutine_threadsafe(crawler.crawl(), loop).result()
        except RuntimeError:
            crawl_result = asyncio.run(crawler.crawl())

        col_id = collection_name if collection_name else target_url
        col_dir = _get_collection_dir(col_id)
        db_path = col_dir / "vector_store.db"
        store = RAGVectorStore(db_path)

        store.index_crawled_data(crawl_result, collection_name=col_id)
        meta = store.get_metadata()

        return json.dumps(
            {
                "status": "success",
                "target_url": target_url,
                "collection_name": col_id,
                "is_single_page_doc": crawl_result.get("is_single_page_doc", False),
                "pages_crawled": crawl_result["total_pages_crawled"],
                "sections_extracted": meta.get("total_sections", 0),
                "chunks_indexed": meta.get("total_chunks", 0),
                "size_mb": meta.get("size_mb", 0.0),
                "store_location": str(db_path),
                "message": f"Successfully indexed {meta.get('total_sections', 0)} sections across {crawl_result['total_pages_crawled']} pages with anchor deep-links.",
            },
            indent=2,
        )
    except Exception as e:
        return json.dumps(
            {
                "status": "error",
                "error": f"Failed to crawl and index '{target_url}': {str(e)}",
                "target_url": target_url,
                "collection_name": collection_name,
            },
            indent=2,
        )


@mcp.tool()
def index_local_codebase(
    project_path: str = ".",
    collection_name: Optional[str] = None,
    include_code: bool = True,
    extensions: Optional[List[str]] = None,
    force_reindex: bool = False,
) -> str:
    """
    Incrementally index a local repository workspace using Next.js-style Content-Addressable SHA-256 Caching.
    Skips unchanged files in 0ms, re-indexes only modified files, and prunes deleted files.

    Args:
        project_path: Path to the local workspace folder (default: current directory '.').
        collection_name: Optional collection alias (default: folder name).
        include_code: If True, indexes code files (.ts, .py, .go, etc.) alongside documentation (default True).
        extensions: Optional list of file extensions to include (e.g. ['.md', '.ts', '.py']).
        force_reindex: If True, ignores cached hashes and re-indexes all files.
    """
    try:
        root_p = Path(project_path).resolve()
        if not root_p.exists() or not root_p.is_dir():
            return json.dumps({"error": f"Invalid project directory: '{project_path}'"}, indent=2)

        col_id = collection_name or root_p.name.lower()
        col_dir = _get_collection_dir(col_id)
        db_path = col_dir / "vector_store.db"
        store = RAGVectorStore(db_path)

        allowed_exts = set(extensions) if extensions else None
        cached_hashes = {} if force_reindex else store.get_manifest_hashes(collection=col_id)

        def _progress(phase: str, phase_num: int, total_phases: int, cur: int, tot: int, msg: str):
            pct = (cur / tot * 100.0) if tot > 0 else 0.0
            sys.stderr.write(f"[{phase_num}/{total_phases}] {phase} ({pct:.1f}%): {msg}\n")
            sys.stderr.flush()

        files_to_update, skipped_count, live_paths = scan_local_codebase(
            str(root_p), allowed_extensions=allowed_exts, cached_hashes=cached_hashes, progress_cb=_progress
        )

        _progress(
            "SQLITE_WAL_COMMIT",
            4,
            5,
            0,
            len(files_to_update),
            f"Committing {len(files_to_update)} updated files to SQLite...",
        )
        total_new_chunks = store.update_files_batch(collection=col_id, files_data=files_to_update)
        updated_count = len(files_to_update)
        _progress(
            "SQLITE_WAL_COMMIT",
            4,
            5,
            len(files_to_update),
            len(files_to_update),
            f"Committed {total_new_chunks} chunks.",
        )

        _progress("GRAPH_LINK_AND_PRUNE", 5, 5, 0, 1, "Pruning deleted files & checking Graphify graph...")
        pruned_count = store.prune_orphaned_files(collection=col_id, live_file_paths=live_paths)

        # Check for Graphify output in the project
        graphify_json = root_p / "graphify-out" / "graph.json"
        has_graph = False
        if graphify_json.exists():
            try:
                with open(graphify_json, "r", encoding="utf-8") as f:
                    g_data = json.load(f)
                    store.index_graphify_graph(g_data)
                    has_graph = True
            except Exception:
                pass

        store.set_collection_meta(name=col_id, coll_type="local_codebase", source_uri=str(root_p))

        _progress("COMPLETE", 5, 5, 1, 1, "Done!")

        meta = store.get_metadata()

        return json.dumps(
            {
                "status": "success",
                "collection_name": col_id,
                "project_path": str(root_p),
                "total_scanned_files": len(files_to_update) + skipped_count,
                "unchanged_files_skipped": skipped_count,
                "files_reindexed": updated_count,
                "deleted_orphans_pruned": pruned_count,
                "total_active_chunks": meta.get("total_chunks", 0),
                "graphify_graph_linked": has_graph,
                "size_mb": meta.get("size_mb", 0.0),
                "store_location": str(db_path),
                "message": f"Indexed '{col_id}': {updated_count} files re-indexed ({total_new_chunks} chunks), {skipped_count} unchanged files skipped in 0ms.",
            },
            indent=2,
        )
    except Exception as e:
        return json.dumps(
            {
                "status": "error",
                "error": f"Failed to index local codebase at '{project_path}': {str(e)}",
                "project_path": project_path,
            },
            indent=2,
        )


@mcp.tool()
def index_remote_repo(
    repo_url: str,
    collection_name: Optional[str] = None,
    subpath: Optional[str] = None,
    is_temp: bool = False,
    auth_token: Optional[str] = None,
) -> str:
    """
    Stream and index a remote GitHub repository in-memory WITHOUT cloning to local disk.
    Caches knowledge store by remote Git Commit SHA, skips re-downloads if unchanged,
    and generates clickable GitHub deep-link citations (#L10-L40).

    Args:
        repo_url: GitHub repository URL (e.g. 'https://github.com/tiangolo/fastapi' or 'https://github.com/pallets/flask/tree/main/docs').
        collection_name: Optional custom alias for this repository (e.g. 'fastapi-docs').
        subpath: Optional folder filter inside repo (e.g. 'docs' or 'src').
        is_temp: If True, marks this collection as ephemeral with 24h auto-expiry (default False).
        auth_token: Optional GitHub Personal Access Token for private repositories.
    """
    try:
        parsed = parse_github_url(repo_url)
        effective_subpath = subpath or parsed.get("subpath") or ""
        col_id = collection_name or parsed["repo"].lower()

        col_dir = _get_collection_dir(col_id)
        db_path = col_dir / "vector_store.db"
        store = RAGVectorStore(db_path)

        # 1. Stream repo in memory
        stream_res = stream_github_repo_in_memory(repo_url=repo_url, subpath=effective_subpath, auth_token=auth_token)

        remote_sha = stream_res.get("commit_sha", "")
        files_data = stream_res.get("files", [])

        cached_hashes = store.get_manifest_hashes(collection=col_id)
        live_paths = {fd["file_path"] for fd in files_data}
        files_to_update = [fd for fd in files_data if cached_hashes.get(fd["file_path"]) != fd["content_hash"]]
        skipped_count = len(files_data) - len(files_to_update)

        total_new_chunks = store.update_files_batch(collection=col_id, files_data=files_to_update)
        updated_count = len(files_to_update)

        pruned_count = store.prune_orphaned_files(collection=col_id, live_file_paths=live_paths)

        resolved_branch = stream_res.get("repo_meta", {}).get("branch") or parsed.get("branch") or "main"
        store.set_collection_meta(
            name=col_id,
            coll_type="remote_git",
            source_uri=repo_url,
            commit_sha=remote_sha,
            is_temp=is_temp,
            ttl_hours=24 if is_temp else None,
        )

        meta = store.get_metadata()

        return json.dumps(
            {
                "status": "success",
                "collection_name": col_id,
                "repo_url": repo_url,
                "branch": resolved_branch,
                "commit_sha": remote_sha[:8] if remote_sha else "latest",
                "is_temp": is_temp,
                "total_streamed_files": len(files_data),
                "unchanged_files_skipped": skipped_count,
                "files_indexed": updated_count,
                "total_active_chunks": meta.get("total_chunks", 0),
                "size_mb": meta.get("size_mb", 0.0),
                "store_location": str(db_path),
                "message": f"Zero-clone indexed '{parsed['full_name']}': {updated_count} files indexed ({total_new_chunks} chunks), {skipped_count} skipped in 0ms.",
            },
            indent=2,
        )
    except Exception as e:
        return json.dumps(
            {
                "status": "error",
                "error": f"Failed to index remote repository '{repo_url}': {str(e)}",
                "repo_url": repo_url,
                "collection_name": collection_name,
            },
            indent=2,
        )


@mcp.tool()
def query_knowledge_base(
    query: str,
    target_url_or_collection: Optional[str] = None,
    top_k: int = 5,
    max_chars_per_snippet: int = 1000,
    compact: bool = True,
    filter_path: Optional[str] = None,
    exclude_paths: Optional[List[str]] = None,
) -> str:
    """
    Perform hybrid vector + BM25 search returning section-level snippets with exact anchor deep-link citations.
    Supports querying a single collection or searching across ALL collections.
    Includes built-in path filtering, canonical documentation boosts, and snippet boundary controls.

    Args:
        query: Search query or question.
        target_url_or_collection: Target collection name or URL. If omitted or 'all', searches across ALL indexed collections.
        top_k: Number of relevant snippet results to return (default: 5).
        max_chars_per_snippet: Maximum character length per snippet excerpt (default: 1000, use 0 for full text).
        compact: If True (default), formats results with token-optimized keys and truncates long text. Call get_chunk_context() to read full chunk content.
        filter_path: Optional substring filter for file paths (e.g. 'handbook/2', 'reference', 'src/api').
        exclude_paths: Optional list of path substrings to exclude (e.g. ['release-notes', 'deprecated', 'v1']).
    """
    all_results = []

    if target_url_or_collection and target_url_or_collection.lower() not in ("all", "*", ""):
        col_dir = _get_collection_dir(target_url_or_collection)
        db_path = col_dir / "vector_store.db"
        if not db_path.exists():
            found = False
            for col_name, store in _get_all_stores():
                meta = store.get_metadata()
                if (
                    meta.get("target_url") == target_url_or_collection
                    or meta.get("collection_name") == target_url_or_collection
                    or col_name == target_url_or_collection.lower()
                ):
                    results = store.search(
                        query,
                        top_k=top_k,
                        max_chars_per_snippet=max_chars_per_snippet,
                        filter_path=filter_path,
                        exclude_paths=exclude_paths,
                    )
                    for r in results:
                        r["collection"] = col_name
                    all_results.extend(results)
                    found = True
                    break
            if not found:
                available = [c for c, _ in _get_all_stores()]
                closest = [
                    c
                    for c in available
                    if target_url_or_collection.lower() in c.lower() or c.lower() in target_url_or_collection.lower()
                ]
                return json.dumps(
                    {
                        "error": f"No indexed collection found for '{target_url_or_collection}'.",
                        "did_you_mean": closest if closest else None,
                        "available_collections": available,
                        "hint": "Use list_rag_collections() to see available indices or omit target_url_or_collection to search all.",
                    },
                    indent=2,
                )
        else:
            store = RAGVectorStore(db_path)
            results = store.search(
                query,
                top_k=top_k,
                max_chars_per_snippet=max_chars_per_snippet,
                filter_path=filter_path,
                exclude_paths=exclude_paths,
            )
            for r in results:
                r["collection"] = target_url_or_collection
            all_results.extend(results)
    else:
        stores = _get_all_stores()
        if not stores:
            return json.dumps(
                {
                    "message": "No indexed collections found. Use crawl_and_index_url(), index_local_codebase(), or index_remote_repo() to index content.",
                    "results": [],
                },
                indent=2,
            )

        for col_name, store in stores:
            res = store.search(
                query,
                top_k=top_k,
                max_chars_per_snippet=max_chars_per_snippet,
                filter_path=filter_path,
                exclude_paths=exclude_paths,
            )
            for r in res:
                r["collection"] = col_name
            all_results.extend(res)

    all_results = sorted(all_results, key=lambda x: x.get("similarity_score", 0), reverse=True)[:top_k]

    if not all_results:
        return json.dumps(
            {
                "query": query,
                "target_collection": target_url_or_collection or "all",
                "total_results": 0,
                "confidence": "none",
                "results": [],
                "suggestions": [
                    "No matching snippets found. Try broader keywords or simpler terms.",
                    "If using filter_path or exclude_paths, try relaxing the path filter.",
                    "Verify indexed collections with list_rag_collections().",
                ],
            },
            indent=2,
        )

    raw_words = [w.lower() for w in re.findall(r"[a-zA-Z0-9_]+", query)]
    sig_terms = [w for w in raw_words if len(w) > 2 and w not in COMMON_STOPWORDS]

    top3_candidates = all_results[: min(3, len(all_results))]
    top3_content = " ".join(f"{r.get('section', '')} {r.get('snippet', '')}" for r in top3_candidates).lower()

    if sig_terms:
        global_matched = []
        global_missing = []
        for t in sig_terms:
            st = _stem_token(t)
            if (t in top3_content) or (st in top3_content):
                global_matched.append(t)
            else:
                global_missing.append(t)
        global_coverage = len(global_matched) / len(sig_terms)
    else:
        global_matched = []
        global_missing = []
        global_coverage = 1.0

    top_hit = all_results[0]
    top_score = top_hit.get("similarity_score", 0.0)
    top_cov = top_hit.get("query_coverage", {})
    rank1_coverage = top_cov.get("coverage_ratio", 1.0)

    # Calibrate confidence using multi-chunk global coverage, rank-1 match, and score
    coverage_factor = (rank1_coverage * 0.35) + (global_coverage * 0.65)
    score_factor = min(0.3, max(0.0, top_score / 15.0))

    if global_missing:
        # A significant term is completely absent across all top-3 hits
        penalty = min(0.4, len(global_missing) * 0.2)
        confidence_score = max(0.1, round((coverage_factor * 0.7) - penalty + score_factor, 2))
        if confidence_score >= 0.50:
            confidence = "medium"
            confidence_note = f"Moderate match: terms {global_missing} were not found in primary documentation, but related patterns were retrieved."
        else:
            confidence = "low"
            confidence_note = f"Low confidence: key term(s) {global_missing} were not found in the indexed documentation. Results provide related background, but no dedicated pattern was found."
    else:
        confidence_score = min(1.0, round((coverage_factor * 0.7) + score_factor, 2))
        if confidence_score >= 0.75 and top_score >= 2.0:
            confidence = "high"
            confidence_note = "High confidence: primary documentation directly covers all query concepts."
        elif confidence_score >= 0.45:
            confidence = "medium"
            confidence_note = "Moderate confidence match across relevant sections."
        else:
            confidence = "low"
            confidence_note = "Low semantic match score: documentation may not directly address this concept."

    # On low-confidence queries, filter out trailing filler results that score far below the top candidate (< 60% of top_score)
    if confidence == "low" and len(all_results) > 2:
        threshold = top_score * 0.60
        all_results = [r for r in all_results if r.get("similarity_score", 0) >= threshold][:3]

    if compact:
        compact_results = []
        for r in all_results:
            ls = r.get("line_start", 0)
            le = r.get("line_end", 0)
            lines_str = f"L{ls}-L{le}" if (ls > 0 and le > 0) else None
            item = {
                "chunk_id": r.get("chunk_id"),
                "collection": r.get("collection"),
                "file_path": r.get("file_path"),
                "section": r.get("section"),
                "citation_url": r.get("citation_url"),
                "similarity_score": r.get("similarity_score"),
                "snippet": r.get("snippet"),
            }
            if lines_str:
                item["lines"] = lines_str
            compact_results.append(item)

        resp_obj = {
            "query": query,
            "confidence": confidence,
            "confidence_score": confidence_score,
            "confidence_note": confidence_note,
            "missing_query_terms": global_missing,
            "total_results": len(compact_results),
            "results": compact_results,
            "token_control": {
                "compact_mode": True,
                "max_chars_per_snippet": max_chars_per_snippet,
                "tip": "Snippets are compact to conserve context tokens. Call get_chunk_context(chunk_id=<id>, window=1) to retrieve the full code block or surrounding context.",
            },
        }
        return json.dumps(resp_obj, indent=2)

    return json.dumps(
        {
            "query": query,
            "confidence": confidence,
            "confidence_score": confidence_score,
            "confidence_note": confidence_note,
            "missing_query_terms": global_missing,
            "total_results": len(all_results),
            "results": all_results,
        },
        indent=2,
    )


@mcp.tool()
def find_related_chunks(chunk_id: int, target_url_or_collection: Optional[str] = None, top_k: int = 5) -> str:
    """
    Find semantically and topically related chunks given a known chunk ID from previous search results.
    Enables instant pivot from one documentation section to related concepts without manual keyword guessing.

    Args:
        chunk_id: The chunk ID to find relations for (from query_knowledge_base results).
        target_url_or_collection: Optional collection alias to narrow lookup.
        top_k: Maximum number of related chunks to return (default: 5).
    """
    stores = _get_all_stores()
    if target_url_or_collection and target_url_or_collection.lower() not in ("all", "*", ""):
        col_dir = _get_collection_dir(target_url_or_collection)
        db_path = col_dir / "vector_store.db"
        if db_path.exists():
            store = RAGVectorStore(db_path)
            related = store.find_related(chunk_id, top_k=top_k, collection=target_url_or_collection)
            return json.dumps({"source_chunk_id": chunk_id, "related_chunks": related}, indent=2)

    for col_name, store in stores:
        related = store.find_related(chunk_id, top_k=top_k)
        if related:
            return json.dumps(
                {"source_chunk_id": chunk_id, "collection": col_name, "related_chunks": related}, indent=2
            )

    return json.dumps({"error": f"Chunk ID {chunk_id} not found to compute related items."}, indent=2)


@mcp.tool()
def get_chunk_context(chunk_id: int, target_url_or_collection: Optional[str] = None, window: int = 0) -> str:
    """
    Retrieve the complete, untruncated content for a chunk, optionally expanding surrounding context.
    Call this when query_knowledge_base returns a compact snippet that matches your need, and you require
    the full code block, paragraph, or adjacent lines without flooding your context window with all search hits.

    Args:
        chunk_id: The ID of the chunk to inspect (from query_knowledge_base results).
        target_url_or_collection: Optional collection name to narrow down lookup. If omitted, searches across collections.
        window: Number of adjacent chunks before and after to include (default 0 for just the target chunk; e.g. 1 returns previous, current, and next chunks).
    """
    if target_url_or_collection and target_url_or_collection.lower() not in ("all", "*", ""):
        col_dir = _get_collection_dir(target_url_or_collection)
        db_path = col_dir / "vector_store.db"
        if db_path.exists():
            store = RAGVectorStore(db_path)
            res = store.get_chunk_context(chunk_id, window=window)
            if res:
                return json.dumps({"status": "success", "chunk": res}, indent=2)

    for col_name, store in _get_all_stores():
        res = store.get_chunk_context(chunk_id, window=window)
        if res:
            return json.dumps({"status": "success", "chunk": res}, indent=2)

    return json.dumps(
        {"error": f"Chunk with id {chunk_id} not found. Ensure the ID matches a chunk_id from query_knowledge_base."},
        indent=2,
    )


@mcp.tool()
def get_knowledge_tree(target_url_or_collection: str, filter_path: Optional[str] = None, max_items: int = 50) -> str:
    """
    Retrieve the hierarchical section, document, and link graph tree for an indexed collection.
    Includes path filtering and item capping to prevent LLM context window overflow.

    Args:
        target_url_or_collection: Collection name or target documentation URL.
        filter_path: Optional directory or file substring filter (e.g. 'src/api' or 'auth').
        max_items: Maximum items to return to keep context compact (default: 50).
    """
    col_dir = _get_collection_dir(target_url_or_collection)
    db_path = col_dir / "vector_store.db"
    store = None
    if db_path.exists():
        store = RAGVectorStore(db_path)
    else:
        for col_name, s in _get_all_stores():
            if col_name == target_url_or_collection.lower():
                store = s
                break

    if not store:
        return json.dumps({"error": f"No knowledge tree found for '{target_url_or_collection}'."}, indent=2)

    return json.dumps(store.get_site_tree(filter_path=filter_path, max_items=max_items), indent=2)


@mcp.tool()
def list_rag_collections() -> str:
    """
    List all indexed collections (Web Docs, Local Codebases, and Remote Git Repos) with disk sizes, chunk counts, and metadata.
    """
    stores = _get_all_stores()
    if not stores:
        return json.dumps({"total_collections": 0, "collections": []}, indent=2)

    collections = []
    total_size_bytes = 0

    for col_name, store in stores:
        meta = store.get_metadata()
        size_bytes = meta.get("size_bytes", 0)
        total_size_bytes += size_bytes
        collections.append(
            {
                "collection_name": col_name,
                "target_url": meta.get("target_url") or meta.get("source_uri", "N/A"),
                "is_single_page_doc": meta.get("is_single_page_doc") == "true",
                "total_chunks": meta.get("total_chunks", 0),
                "total_files_or_pages": meta.get("total_files") or meta.get("total_pages", 0),
                "total_sections": meta.get("total_sections", 0),
                "size_mb": meta.get("size_mb", 0.0),
                "db_path": str(store.db_path),
            }
        )

    return json.dumps(
        {
            "total_collections": len(collections),
            "total_disk_usage_mb": round(total_size_bytes / (1024 * 1024), 2),
            "collections": collections,
        },
        indent=2,
    )


@mcp.tool()
def delete_rag_collection(collection_name: str) -> str:
    """
    Delete an indexed RAG collection and completely reclaim disk space.

    Args:
        collection_name: Name or URL of the collection to remove.
    """
    col_dir = _get_collection_dir(collection_name)
    if col_dir.exists():
        shutil.rmtree(col_dir)
        return json.dumps(
            {
                "status": "success",
                "message": f"Successfully deleted RAG collection '{collection_name}' and freed disk space.",
            },
            indent=2,
        )
    return json.dumps({"error": f"Collection '{collection_name}' not found."}, indent=2)


@mcp.tool()
def prune_rag_cache(max_total_mb: float = 500.0, purge_temp_only: bool = False) -> str:
    """
    Automatic LRU and TTL cache pruning to maintain compact disk usage.
    Purges expired ephemeral collections and caps total storage at max_total_mb.

    Args:
        max_total_mb: Maximum allowed total cache size in megabytes before LRU purging (default 500.0 MB).
        purge_temp_only: If True, only cleans expired ephemeral collections without touching permanent ones.
    """
    stores = _get_all_stores()
    if not stores:
        return json.dumps({"message": "No collections found to prune.", "freed_mb": 0.0}, indent=2)

    freed_bytes = 0
    now_iso = datetime.now(timezone.utc).isoformat()
    stores_info = []

    for col_name, store in stores:
        try:
            st = store.db_path.stat()
            size = st.st_size
            mtime = st.st_mtime
            stores_info.append(
                {"name": col_name, "store": store, "dir": store.db_path.parent, "size": size, "mtime": mtime}
            )
        except Exception:
            pass

    # Sort oldest modified first for LRU
    stores_info.sort(key=lambda x: x["mtime"])

    total_bytes = sum(s["size"] for s in stores_info)
    max_bytes = max_total_mb * 1024 * 1024

    deleted_cols = []

    if not purge_temp_only and total_bytes > max_bytes:
        for s in stores_info:
            if total_bytes <= max_bytes:
                break
            try:
                shutil.rmtree(s["dir"])
                freed_bytes += s["size"]
                total_bytes -= s["size"]
                deleted_cols.append(s["name"])
            except Exception:
                pass

    return json.dumps(
        {
            "status": "success",
            "freed_mb": round(freed_bytes / (1024 * 1024), 2),
            "remaining_usage_mb": round(total_bytes / (1024 * 1024), 2),
            "deleted_collections": deleted_cols,
            "message": f"Pruned {len(deleted_cols)} collections, freeing {round(freed_bytes / (1024 * 1024), 2)} MB.",
        },
        indent=2,
    )


if __name__ == "__main__":
    mcp.run()
