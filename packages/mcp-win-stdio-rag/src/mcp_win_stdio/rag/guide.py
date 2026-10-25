"""
Interactive and printable guide for the RAG MCP server.
"""

RAG_GUIDE = """
# ================================================================
# RAG MCP (MULTI-COLLECTION SEARCH) - USER GUIDE
# ================================================================

The RAG MCP server provides 10 specialized tools for multi-collection web crawling,
incremental local codebase indexing, zero-clone remote GitHub repository streaming,
token-compact hybrid search, and on-demand chunk expansion on Windows.

----------------------------------------------------------------
1. TOOL SUMMARY (10 TOOLS)
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
    Performs hybrid SQLite FTS5 BM25 + TF-IDF ranking, with token-overlap fallback.
    Features compact snippet mode and character limits (default 1000 chars) to prevent context window bloat.
  - find_related_chunks(chunk_id, target_url_or_collection, top_k):
    Finds nearby knowledge based on a retrieved chunk so an agent can follow relevant concepts.
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
    Deletes expired temporary collections and optionally removes oldest-modified collections to meet a size limit.

----------------------------------------------------------------
2. AGENT WORKFLOW
----------------------------------------------------------------
1. Index a local project with index_local_codebase() or documentation with crawl_and_index_url().
2. Search with query_knowledge_base(), narrowing with a collection or file-path filter when useful.
3. Pass both chunk_id and collection from a result to get_chunk_context(); use the same collection with find_related_chunks().
4. Use list_rag_collections() to discover sources and get_knowledge_tree() to inspect a collection's structure.
5. Treat confidence and citations as evidence: verify retrieved code/docs before making changes.
   Very weak keyword matches are returned as no-results with suggestions rather than unrelated snippets.
# ================================================================
"""


def print_rag_guide() -> None:
    """Print the formatted RAG MCP guide to stdout."""
    print(RAG_GUIDE.strip())
