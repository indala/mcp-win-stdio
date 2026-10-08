"""
Interactive and printable guide for the RAG MCP server.
"""

RAG_GUIDE = """
# ================================================================
# RAG MCP (MULTI-COLLECTION EMBEDDINGS & SEARCH) - USER GUIDE
# ================================================================

The RAG MCP server provides 9 specialized tools for multi-collection web crawling,
incremental local codebase indexing, zero-clone remote GitHub repository streaming,
token-compact hybrid search, and on-demand chunk expansion on Windows.

----------------------------------------------------------------
1. TOOL SUMMARY (9 TOOLS)
----------------------------------------------------------------
* Crawling & Ingestion:
  - crawl_and_index_url(target_url, collection_name, max_depth, max_pages):
    Asynchronous headless Playwright web crawler extracting clean markdown into vector collections.
  - index_local_codebase(project_path, collection_name, include_code, extensions, force_reindex):
    Fast AST & chunked indexing of local codebases with SHA-256 incremental cache.
  - index_remote_repo(repo_url, collection_name, subpath, is_temp, auth_token):
    Streams public or private GitHub repository archives directly in-memory without cloning.

* Querying & Knowledge Retrieval (Agent-Friendly & Token-Efficient):
  - query_knowledge_base(query, target_url_or_collection, top_k, max_chars_per_snippet, compact):
    Performs hybrid BM25 + dense semantic vector search with relevance ranking.
    Features compact snippet mode and character limits (default 500 chars) to prevent context window bloat.
  - get_chunk_context(chunk_id, target_url_or_collection, window):
    Retrieves full untruncated content for any chunk, optionally expanding surrounding context window.
  - get_knowledge_tree(target_url_or_collection, filter_path, max_items):
    Returns hierarchical outlines and indexed document paths in a collection with path filtering.

* Collection Lifecycle & Cache Management:
  - list_rag_collections():
    Lists all indexed knowledge collections with document counts, chunk statistics, and sizes.
  - delete_rag_collection(collection_name):
    Permanently deletes a collection and its vector index from disk.
  - prune_rag_cache(max_total_mb, purge_temp_only):
    Frees disk space by deleting outdated crawl artifacts and orphan chunks.
# ================================================================
"""


def print_rag_guide() -> None:
    """Print the formatted RAG MCP guide to stdout."""
    print(RAG_GUIDE.strip())
