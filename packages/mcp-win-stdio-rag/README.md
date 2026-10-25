# mcp-win-stdio-rag

Windows-optimized RAG MCP server for indexing documentation and repositories, then retrieving cited, bounded context for coding agents.

## Tools

The server exposes 10 tools:

| Workflow | Tools |
| --- | --- |
| Indexing | `crawl_and_index_url`, `index_local_codebase`, `index_remote_repo` |
| Retrieval | `query_knowledge_base`, `get_chunk_context`, `find_related_chunks`, `get_knowledge_tree` |
| Collection management | `list_rag_collections`, `delete_rag_collection`, `prune_rag_cache` |

## Agent workflow

1. Index a local workspace with `index_local_codebase` or documentation with `crawl_and_index_url`; use `index_remote_repo` for GitHub sources.
2. Call `list_rag_collections` to discover available sources, then search with `query_knowledge_base`. Omit the collection to search all indexed sources.
3. Follow citations and pass both the result's `chunk_id` and `collection` to `get_chunk_context` and `find_related_chunks`; chunk IDs can repeat across collections. Use `get_knowledge_tree` to browse a collection.
4. Treat retrieval confidence as a relevance signal, not proof; confirm cited material before relying on it.

## Search and storage

Search combines SQLite FTS5 BM25 with TF-IDF ranking when scikit-learn is installed, and falls back to token overlap when it is not. Confidence uses normalized whole-term overlap rather than substring matches, ignores common question filler, and abstains when fewer than one quarter of meaningful query terms are covered by the top results. Indexes are stored locally under `%USERPROFILE%\\.mcp-win-stdio\\rag_stores` by default; set `MCP_RAG_DATA_DIR` to choose another location.

`prune_rag_cache` removes expired temporary collections first. Unless `purge_temp_only` is enabled, it then removes oldest-modified collections until storage is within `max_total_mb`. `delete_rag_collection` permanently removes one selected collection.
