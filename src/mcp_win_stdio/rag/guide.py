"""
Interactive and printable guide for the RAG MCP server.
"""

RAG_GUIDE = """
# ================================================================
# RAG MCP (MULTI-COLLECTION EMBEDDINGS & SEARCH) - USER GUIDE
# ================================================================

The RAG MCP server provides 8 specialized tools for multi-collection web crawling,
incremental local codebase indexing, zero-clone remote GitHub repository streaming,
and section-aware hybrid vector semantic search on Windows.

----------------------------------------------------------------
1. TOOL SUMMARY (8 TOOLS)
----------------------------------------------------------------
* Crawling & Ingestion:
  - crawl_and_index_url(start_url, max_pages, max_depth, follow_external, ...):
    Asynchronous headless Playwright web crawler extracting clean markdown into vector collections.
  - index_local_codebase(root_path, collection_name, extensions, max_file_size_kb, ...):
    Fast AST & chunked indexing of local codebases with SHA-256 incremental cache.
  - index_remote_repo(repo_url, branch, auth_token, ...):
    Streams public or private GitHub repository archives directly in-memory without cloning.

* Querying & Knowledge Retrieval:
  - query_knowledge_base(query, collection_name, top_k, threshold, ...):
    Performs hybrid BM25 + dense semantic vector search with relevance ranking.
  - get_knowledge_tree(collection_name):
    Returns hierarchical outlines and indexed document paths in a collection.

* Collection Lifecycle & Cache Management:
  - list_rag_collections():
    Lists all indexed knowledge collections with document counts, chunk statistics, and sizes.
  - delete_rag_collection(collection_name):
    Permanently deletes a collection and its vector index from disk.
  - prune_rag_cache(older_than_days):
    Frees disk space by deleting outdated crawl artifacts and orphan chunks.
# ================================================================
"""


def print_rag_guide() -> None:
    """Print the formatted RAG MCP guide to stdout."""
    print(RAG_GUIDE.strip())
