#!/usr/bin/env python3
"""
Advanced Section-Aware Hybrid Vector & BM25 Knowledge Store.
Features Next.js-style Content-Addressable SHA-256 Caching, Graphify Topology Integration,
and Automatic Orphan / TTL Eviction.
"""

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import time
from typing import Any, Dict, List, Optional, Set, Tuple

try:
    import numpy as np
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
    _HAS_SKLEARN = True
except Exception:
    _HAS_SKLEARN = False


def extract_code_subwords(text: str) -> List[str]:
    """
    Extract original identifiers and their subwords from code and text.
    Handles camelCase, PascalCase, snake_case, SCREAMING_SNAKE_CASE, and dotted/slashed paths.
    """
    raw_identifiers = re.findall(r"[a-zA-Z_][a-zA-Z0-9_\-\.\:\/]*", text)
    tokens: Set[str] = set()

    for ident in raw_identifiers:
        if len(ident) <= 1:
            continue
        tokens.add(ident.lower())

        # Split on separators (_, -, ., :, /)
        parts = re.split(r"[_.\-\:\/\\]+", ident)
        for part in parts:
            if not part:
                continue
            tokens.add(part.lower())

            # Split camelCase / PascalCase (e.g. DecodeApiToken -> Decode, Api, Token)
            camel_parts = re.findall(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+|[A-Z]+|\d+", part)
            for cp in camel_parts:
                if len(cp) > 1:
                    tokens.add(cp.lower())

    return list(tokens)


def build_fts5_query(query_str: str) -> str:
    """
    Build a robust SQLite FTS5 MATCH query with subword expansion and prefix wildcards.
    """
    cleaned = re.sub(r'["\';]', ' ', query_str)
    raw_tokens = [t.strip() for t in cleaned.split() if len(t.strip()) > 1]
    if not raw_tokens:
        return ""

    subwords = extract_code_subwords(cleaned)
    all_terms = list(dict.fromkeys(raw_tokens + subwords))

    fts_terms = []
    for term in all_terms:
        safe_term = re.sub(r"[^a-zA-Z0-9_]", "", term)
        if len(safe_term) > 1:
            fts_terms.append(f'"{safe_term}"*')

    if not fts_terms:
        return ""

    return " OR ".join(fts_terms)


def chunk_section_text(section_title: str, text: str, max_words: int = 250, overlap: int = 30) -> List[str]:
    """Split section text into overlapping chunks, prepending the section header."""
    words = text.split()
    if not words:
        return []
    if len(words) <= max_words:
        return [text]

    chunks = []
    i = 0
    while i < len(words):
        chunk_words = words[i : i + max_words]
        chunk_body = " ".join(chunk_words)
        if section_title and not chunk_body.startswith(section_title):
            chunk_body = f"### {section_title}\n{chunk_body}"
        chunks.append(chunk_body)
        i += max_words - overlap

    return chunks


class RAGVectorStore:
    """SQLite-backed Vector, Manifest Cache & Hybrid Search Store with Anchor Deep-Links."""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=60.0)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.execute("PRAGMA busy_timeout=60000;")
        return conn

    def _init_db(self):
        with self._get_connection() as conn:
            # 1. Chunks table with line spans and exact anchor URLs
            conn.execute("""
                CREATE TABLE IF NOT EXISTS chunks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    collection TEXT DEFAULT '',
                    file_path TEXT DEFAULT '',
                    url TEXT DEFAULT '',
                    anchor_url TEXT DEFAULT '',
                    section_title TEXT DEFAULT '',
                    anchor_id TEXT DEFAULT '',
                    line_start INTEGER DEFAULT 0,
                    line_end INTEGER DEFAULT 0,
                    chunk_index INTEGER DEFAULT 0,
                    text TEXT,
                    content_hash TEXT UNIQUE,
                    word_count INTEGER DEFAULT 0
                )
            """)

            # Auto-migrate existing older chunks tables
            existing_cols = {row[1] for row in conn.execute("PRAGMA table_info(chunks)").fetchall()}
            for col_name, col_def in [
                ("collection", "TEXT DEFAULT ''"),
                ("file_path", "TEXT DEFAULT ''"),
                ("line_start", "INTEGER DEFAULT 0"),
                ("line_end", "INTEGER DEFAULT 0")
            ]:
                if col_name not in existing_cols:
                    try:
                        conn.execute(f"ALTER TABLE chunks ADD COLUMN {col_name} {col_def}")
                    except Exception:
                        pass

            # 2. Content-Addressable Files Manifest (Next.js style caching)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS files_manifest (
                    file_path TEXT PRIMARY KEY,
                    collection TEXT DEFAULT '',
                    content_hash TEXT,
                    chunk_count INTEGER DEFAULT 0,
                    size_bytes INTEGER DEFAULT 0,
                    last_indexed_at TEXT
                )
            """)

            # 3. Collection Metadata (type, source URI, commit SHA, TTL)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS collections_meta (
                    collection_name TEXT PRIMARY KEY,
                    collection_type TEXT,
                    source_uri TEXT,
                    commit_sha TEXT DEFAULT '',
                    is_temp INTEGER DEFAULT 0,
                    created_at TEXT,
                    updated_at TEXT,
                    expires_at TEXT DEFAULT ''
                )
            """)

            # 4. Graph Nodes & Edges (for Graphify / GraphRAG integration)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS graph_nodes (
                    node_id TEXT PRIMARY KEY,
                    label TEXT,
                    node_type TEXT,
                    community_id INTEGER DEFAULT 0,
                    file_path TEXT DEFAULT '',
                    summary TEXT DEFAULT ''
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS graph_edges (
                    source TEXT,
                    target TEXT,
                    relation TEXT DEFAULT '',
                    weight REAL DEFAULT 1.0,
                    PRIMARY KEY (source, target, relation)
                )
            """)

            # 5. Legacy site_meta table for backwards compatibility
            conn.execute("""
                CREATE TABLE IF NOT EXISTS site_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            """)

            # 6. Full-Text Search 5 (FTS5) table with subword code tokens and BM25 ranking
            conn.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
                    chunk_id UNINDEXED,
                    collection,
                    file_path,
                    section_title,
                    text,
                    tokens,
                    tokenize='unicode61 remove_diacritics 2'
                )
            """)

            # Auto-backfill FTS5 if chunks exist but chunks_fts is empty
            try:
                c_cnt = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
                fts_cnt = conn.execute("SELECT COUNT(*) FROM chunks_fts").fetchone()[0]
                if c_cnt > 0 and fts_cnt == 0:
                    rows = conn.execute("SELECT id, collection, file_path, section_title, text FROM chunks").fetchall()
                    fts_records = []
                    for cid, coll, fp, st, txt in rows:
                        toks = " ".join(extract_code_subwords(f"{fp} {st} {txt}"))
                        fts_records.append((cid, coll or "", fp or "", st or "", txt or "", toks))
                    conn.executemany("""
                        INSERT INTO chunks_fts (chunk_id, collection, file_path, section_title, text, tokens)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, fts_records)
            except Exception:
                pass

            conn.commit()

    # =========================================================================
    # Manifest & Content-Addressable Cache Methods
    # =========================================================================

    def get_manifest_hashes(self, collection: str = "") -> Dict[str, str]:
        """Get mapping of {file_path: content_hash} to perform 0ms skips on unchanged files."""
        with self._get_connection() as conn:
            cur = conn.execute("SELECT file_path, content_hash FROM files_manifest WHERE collection = ?", (collection,))
            return dict(cur.fetchall())

    def update_file_chunks(
        self,
        collection: str,
        file_path: str,
        content_hash: str,
        chunks: List[Dict[str, Any]],
        size_bytes: int = 0
    ) -> int:
        """
        Incrementally index chunks for a single modified/new file, removing any old chunks.
        """
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            # Delete old chunks for this file
            conn.execute("DELETE FROM chunks WHERE collection = ? AND file_path = ?", (collection, file_path))
            try:
                conn.execute("DELETE FROM chunks_fts WHERE collection = ? AND file_path = ?", (collection, file_path))
            except Exception:
                pass

            chunk_records = []
            for idx, c in enumerate(chunks):
                text = c.get("text", "")
                c_hash = hashlib.sha256(f"{file_path}:{idx}:{text}".encode("utf-8")).hexdigest()
                chunk_records.append((
                    collection,
                    file_path,
                    c.get("page_url", ""),
                    c.get("anchor_url", ""),
                    c.get("section_title", ""),
                    c.get("anchor_id", ""),
                    c.get("line_start", 0),
                    c.get("line_end", 0),
                    idx,
                    text,
                    c_hash,
                    c.get("word_count", len(text.split()))
                ))

            conn.executemany("""
                INSERT OR IGNORE INTO chunks (
                    collection, file_path, url, anchor_url, section_title, anchor_id,
                    line_start, line_end, chunk_index, text, content_hash, word_count
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, chunk_records)

            # Update FTS5 virtual table with subword code tokens
            try:
                cur = conn.execute("SELECT id, section_title, text FROM chunks WHERE collection = ? AND file_path = ?", (collection, file_path))
                fts_records = []
                for cid, st, txt in cur.fetchall():
                    toks = " ".join(extract_code_subwords(f"{file_path} {st} {txt}"))
                    fts_records.append((cid, collection, file_path, st, txt, toks))
                if fts_records:
                    conn.executemany("""
                        INSERT INTO chunks_fts (chunk_id, collection, file_path, section_title, text, tokens)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, fts_records)
            except Exception:
                pass

            # Update manifest
            conn.execute("""
                INSERT OR REPLACE INTO files_manifest (
                    file_path, collection, content_hash, chunk_count, size_bytes, last_indexed_at
                ) VALUES (?, ?, ?, ?, ?, ?)
            """, (file_path, collection, content_hash, len(chunk_records), size_bytes, now_iso))

            conn.commit()
            return len(chunk_records)

    def update_files_batch(
        self,
        collection: str,
        files_data: List[Dict[str, Any]]
    ) -> int:
        """
        Batch incrementally index chunks for multiple files in a single high-speed SQLite transaction.
        """
        if not files_data:
            return 0
        now_iso = datetime.now(timezone.utc).isoformat()
        total_chunks = 0
        with self._get_connection() as conn:
            chunk_records = []
            manifest_records = []
            all_fps = [fd["file_path"] for fd in files_data]

            # Delete old chunks for these files
            conn.executemany("DELETE FROM chunks WHERE collection = ? AND file_path = ?", [(collection, fp) for fp in all_fps])
            try:
                conn.executemany("DELETE FROM chunks_fts WHERE collection = ? AND file_path = ?", [(collection, fp) for fp in all_fps])
            except Exception:
                pass

            for fd in files_data:
                f_path = fd["file_path"]
                f_hash = fd["content_hash"]
                f_chunks = fd.get("chunks", [])
                s_bytes = fd.get("size_bytes", 0)

                for idx, c in enumerate(f_chunks):
                    text = c.get("text", "")
                    c_hash = hashlib.sha256(f"{f_path}:{idx}:{text}".encode("utf-8")).hexdigest()
                    chunk_records.append((
                        collection,
                        f_path,
                        c.get("page_url", ""),
                        c.get("anchor_url", ""),
                        c.get("section_title", ""),
                        c.get("anchor_id", ""),
                        c.get("line_start", 0),
                        c.get("line_end", 0),
                        idx,
                        text,
                        c_hash,
                        c.get("word_count", len(text.split()))
                    ))

                manifest_records.append((
                    f_path, collection, f_hash, len(f_chunks), s_bytes, now_iso
                ))
                total_chunks += len(f_chunks)

            if chunk_records:
                conn.executemany("""
                    INSERT OR IGNORE INTO chunks (
                        collection, file_path, url, anchor_url, section_title, anchor_id,
                        line_start, line_end, chunk_index, text, content_hash, word_count
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, chunk_records)

                # Batch sync FTS5 table with subword tokens
                try:
                    for i in range(0, len(all_fps), 400):
                        batch_paths = all_fps[i : i + 400]
                        q_marks = ",".join("?" for _ in batch_paths)
                        cur = conn.execute(f"SELECT id, file_path, section_title, text FROM chunks WHERE collection = ? AND file_path IN ({q_marks})", [collection] + batch_paths)
                        fts_records = []
                        for cid, fp, st, txt in cur.fetchall():
                            toks = " ".join(extract_code_subwords(f"{fp} {st} {txt}"))
                            fts_records.append((cid, collection, fp, st, txt, toks))
                        if fts_records:
                            conn.executemany("""
                                INSERT INTO chunks_fts (chunk_id, collection, file_path, section_title, text, tokens)
                                VALUES (?, ?, ?, ?, ?, ?)
                            """, fts_records)
                except Exception:
                    pass

            if manifest_records:
                conn.executemany("""
                    INSERT OR REPLACE INTO files_manifest (
                        file_path, collection, content_hash, chunk_count, size_bytes, last_indexed_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                """, manifest_records)

            conn.commit()
        return total_chunks

    def prune_orphaned_files(self, collection: str, live_file_paths: Set[str]) -> int:
        """Prune chunks and manifest entries for files that no longer exist in the repo."""
        with self._get_connection() as conn:
            cur = conn.execute("SELECT file_path FROM files_manifest WHERE collection = ?", (collection,))
            stored_paths = {row[0] for row in cur.fetchall()}

            orphans = list(stored_paths - live_file_paths)
            if not orphans:
                return 0

            conn.executemany("DELETE FROM chunks WHERE collection = ? AND file_path = ?", [(collection, op) for op in orphans])
            try:
                conn.executemany("DELETE FROM chunks_fts WHERE collection = ? AND file_path = ?", [(collection, op) for op in orphans])
            except Exception:
                pass
            conn.executemany("DELETE FROM files_manifest WHERE collection = ? AND file_path = ?", [(collection, op) for op in orphans])
            conn.commit()
            return len(orphans)

    def set_collection_meta(
        self,
        name: str,
        coll_type: str,
        source_uri: str,
        commit_sha: str = "",
        is_temp: bool = False,
        ttl_hours: Optional[int] = None
    ):
        """Set or update collection metadata and expiration TTL."""
        now_iso = datetime.now(timezone.utc).isoformat()
        expires_at = ""
        if is_temp or ttl_hours:
            hours = ttl_hours if ttl_hours else 24
            expires_at = datetime.fromtimestamp(time.time() + (hours * 3600), tz=timezone.utc).isoformat()

        with self._get_connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO collections_meta (
                    collection_name, collection_type, source_uri, commit_sha, is_temp, created_at, updated_at, expires_at
                ) VALUES (?, ?, ?, ?, ?, COALESCE((SELECT created_at FROM collections_meta WHERE collection_name = ?), ?), ?, ?)
            """, (name, coll_type, source_uri, commit_sha, 1 if is_temp else 0, name, now_iso, now_iso, expires_at))
            conn.commit()

    # =========================================================================
    # Graphify Knowledge Graph Ingestion
    # =========================================================================

    def index_graphify_graph(self, graph_data: Dict[str, Any]):
        """Index Graphify nodes, communities, and relationships into SQLite tables."""
        nodes = graph_data.get("nodes", [])
        edges = graph_data.get("edges", [])

        with self._get_connection() as conn:
            conn.execute("DELETE FROM graph_nodes")
            conn.execute("DELETE FROM graph_edges")

            node_records = [
                (
                    n.get("id") or n.get("name", ""),
                    n.get("label") or n.get("name", ""),
                    n.get("type", "entity"),
                    n.get("community", 0),
                    n.get("file", ""),
                    n.get("summary", "")
                )
                for n in nodes if n.get("id") or n.get("name")
            ]
            conn.executemany("""
                INSERT OR REPLACE INTO graph_nodes (
                    node_id, label, node_type, community_id, file_path, summary
                ) VALUES (?, ?, ?, ?, ?, ?)
            """, node_records)

            edge_records = [
                (
                    e.get("source", ""),
                    e.get("target", ""),
                    e.get("relation", "connected_to"),
                    float(e.get("weight", 1.0))
                )
                for e in edges if e.get("source") and e.get("target")
            ]
            conn.executemany("""
                INSERT OR IGNORE INTO graph_edges (
                    source, target, relation, weight
                ) VALUES (?, ?, ?, ?)
            """, edge_records)

            conn.commit()

    # =========================================================================
    # Web Crawl Ingestion (Backwards-compatible)
    # =========================================================================

    def index_crawled_data(self, crawl_result: Dict[str, Any], collection_name: str = ""):
        """Index section-aware crawled pages and anchor URLs into the SQLite store."""
        pages = crawl_result.get("pages", [])
        site_graph = crawl_result.get("site_graph", {})
        target_url = crawl_result.get("target_url", "")
        is_single_page = crawl_result.get("is_single_page_doc", False)

        with self._get_connection() as conn:
            conn.execute("DELETE FROM chunks WHERE collection = ?", (collection_name or target_url,))

            chunk_records = []
            seen_hashes = set()

            for page in pages:
                page_url = page.get("url", "")
                page_title = page.get("title", "")
                sections = page.get("sections", [])

                for sec in sections:
                    anchor_id = sec.get("anchor_id", "")
                    sec_title = sec.get("section_title") or page_title
                    sec_text = sec.get("text", "")

                    if not sec_text:
                        continue

                    anchor_url = f"{page_url}#{anchor_id}" if anchor_id else page_url
                    chunks = chunk_section_text(sec_title, sec_text)

                    for chunk_idx, chunk in enumerate(chunks):
                        c_hash = hashlib.sha256(chunk.encode("utf-8")).hexdigest()
                        if c_hash in seen_hashes:
                            continue
                        seen_hashes.add(c_hash)

                        chunk_records.append((
                            collection_name or target_url,
                            page_url,
                            page_url,
                            anchor_url,
                            sec_title,
                            anchor_id,
                            0,
                            0,
                            chunk_idx,
                            chunk,
                            c_hash,
                            len(chunk.split())
                        ))

            conn.executemany("""
                INSERT OR IGNORE INTO chunks (
                    collection, file_path, url, anchor_url, section_title, anchor_id,
                    line_start, line_end, chunk_index, text, content_hash, word_count
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, chunk_records)

            conn.execute(
                "INSERT OR REPLACE INTO site_meta (key, value) VALUES (?, ?)",
                ("site_graph", json.dumps(site_graph))
            )
            conn.execute(
                "INSERT OR REPLACE INTO site_meta (key, value) VALUES (?, ?)",
                ("target_url", target_url)
            )
            conn.execute(
                "INSERT OR REPLACE INTO site_meta (key, value) VALUES (?, ?)",
                ("is_single_page_doc", "true" if is_single_page else "false")
            )
            conn.commit()

        self.set_collection_meta(
            name=collection_name or target_url,
            coll_type="web_docs",
            source_uri=target_url
        )

    # =========================================================================
    # Search & Diagnostic Methods
    # =========================================================================

    def search(
        self,
        query: str,
        top_k: int = 8,
        collection: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Next-Gen Hybrid Search:
        1. SQLite FTS5 BM25 with column-weighted subword matching (< 1ms)
        2. High-capacity subword & char n-gram TF-IDF vector ranking (25,000 features)
        3. Reciprocal Rank Fusion (RRF) combining lexical precision & conceptual semantic similarity.
        """
        fts_query = build_fts5_query(query)
        bm25_results: List[Dict[str, Any]] = []

        with self._get_connection() as conn:
            # 1. High-Speed SQLite FTS5 BM25 Lookup
            if fts_query:
                try:
                    # Column weights: (w_collection=0, w_file_path=12, w_section_title=8, w_text=3, w_tokens=6)
                    if collection:
                        cur = conn.execute("""
                            SELECT
                                c.id, c.url, c.anchor_url, c.file_path, c.section_title,
                                c.line_start, c.line_end, c.chunk_index, c.text,
                                bm25(chunks_fts, 0.0, 15.0, 10.0, 2.0, 8.0) as bm25_rank
                            FROM chunks_fts f
                            JOIN chunks c ON c.id = f.chunk_id
                            WHERE chunks_fts MATCH ? AND (c.collection = ?)
                            ORDER BY bm25_rank ASC
                            LIMIT ?
                        """, (fts_query, collection, max(top_k * 4, 40)))
                    else:
                        cur = conn.execute("""
                            SELECT
                                c.id, c.url, c.anchor_url, c.file_path, c.section_title,
                                c.line_start, c.line_end, c.chunk_index, c.text,
                                bm25(chunks_fts, 0.0, 15.0, 10.0, 2.0, 8.0) as bm25_rank
                            FROM chunks_fts f
                            JOIN chunks c ON c.id = f.chunk_id
                            WHERE chunks_fts MATCH ?
                            ORDER BY bm25_rank ASC
                            LIMIT ?
                        """, (fts_query, max(top_k * 4, 40)))

                    for row in cur.fetchall():
                        cid, url, anchor_url, fp, st, ls, le, cidx, txt, bm_score = row
                        bm25_results.append({
                            "id": cid,
                            "url": url,
                            "anchor_url": anchor_url,
                            "file_path": fp,
                            "section_title": st,
                            "line_start": ls,
                            "line_end": le,
                            "chunk_index": cidx,
                            "text": txt,
                            "bm25_score": float(bm_score)
                        })
                except Exception:
                    pass

            # 2. Fetch candidate set for vector/subword re-ranking
            if not bm25_results:
                if collection:
                    cur = conn.execute("""
                        SELECT id, url, anchor_url, file_path, section_title, line_start, line_end, chunk_index, text
                        FROM chunks WHERE collection = ? LIMIT 500
                    """, (collection,))
                else:
                    cur = conn.execute("""
                        SELECT id, url, anchor_url, file_path, section_title, line_start, line_end, chunk_index, text
                        FROM chunks LIMIT 500
                    """)
                candidate_rows = cur.fetchall()
            else:
                candidate_rows = [
                    (r["id"], r["url"], r["anchor_url"], r["file_path"], r["section_title"], r["line_start"], r["line_end"], r["chunk_index"], r["text"])
                    for r in bm25_results
                ]

        if not candidate_rows:
            return []

        c_ids, urls, anchor_urls, file_paths, section_titles, line_starts, line_ends, chunk_indices, texts = zip(*candidate_rows)

        # 3. Dense / Subword N-gram Vector Similarity Ranking
        vector_ranked_ids: List[int] = []
        if _HAS_SKLEARN:
            try:
                vectorizer = TfidfVectorizer(
                    analyzer='word',
                    token_pattern=r'(?u)\b\w+\b',
                    ngram_range=(1, 2),
                    max_features=25000,
                    sublinear_tf=True
                )
                tfidf_matrix = vectorizer.fit_transform(texts)
                query_vec = vectorizer.transform([query])
                scores = cosine_similarity(query_vec, tfidf_matrix).flatten()
                sorted_vec_idx = np.argsort(scores)[::-1]
                vector_ranked_ids = [c_ids[i] for i in sorted_vec_idx if scores[i] > 0.001]
            except Exception:
                vector_ranked_ids = list(c_ids)
        else:
            try:
                q_tokens = set(extract_code_subwords(query))
                scores_list = []
                for i, txt in enumerate(texts):
                    txt_tokens = set(extract_code_subwords(txt))
                    overlap = len(q_tokens & txt_tokens)
                    scores_list.append((c_ids[i], overlap))
                scores_list.sort(key=lambda x: x[1], reverse=True)
                vector_ranked_ids = [cid for cid, score in scores_list if score > 0] or list(c_ids)
            except Exception:
                vector_ranked_ids = list(c_ids)

        # 4. Reciprocal Rank Fusion (RRF)
        # RRF formula: Score(d) = 1/(60 + rank_bm25) + 1/(60 + rank_vector)
        rrf_scores: Dict[int, float] = {}
        bm25_ranked_ids = [r["id"] for r in bm25_results]

        for rank, cid in enumerate(bm25_ranked_ids, start=1):
            rrf_scores[cid] = rrf_scores.get(cid, 0.0) + (1.0 / (60.0 + rank))

        for rank, cid in enumerate(vector_ranked_ids, start=1):
            rrf_scores[cid] = rrf_scores.get(cid, 0.0) + (1.0 / (60.0 + rank))

        # Build candidate lookup
        cand_map = {
            c_ids[i]: {
                "section": section_titles[i],
                "citation_url": anchor_urls[i] or urls[i] or file_paths[i],
                "file_path": file_paths[i],
                "line_start": line_starts[i],
                "line_end": line_ends[i],
                "chunk_index": chunk_indices[i],
                "snippet": texts[i]
            }
            for i in range(len(c_ids))
        }

        # Sort by RRF score descending
        sorted_candidates = sorted(rrf_scores.keys(), key=lambda cid: rrf_scores[cid], reverse=True)

        final_results = []
        for cid in sorted_candidates[:top_k]:
            if cid in cand_map:
                item = cand_map[cid]
                item["similarity_score"] = round(rrf_scores[cid] * 100, 4)
                final_results.append(item)

        return final_results

    def get_metadata(self) -> Dict[str, Any]:
        """Retrieve stored metadata and stats for this store."""
        with self._get_connection() as conn:
            cur = conn.execute("SELECT key, value FROM site_meta")
            meta = dict(cur.fetchall())

            cols = {row[1] for row in conn.execute("PRAGMA table_info(chunks)").fetchall()}
            if not cols:
                meta["total_chunks"] = 0
                meta["total_files"] = 0
                meta["total_sections"] = 0
                meta["size_bytes"] = 0
                meta["size_mb"] = 0.0
                return meta

            fp_expr = "file_path" if "file_path" in cols else ("url" if "url" in cols else "id")
            au_expr = "anchor_url" if "anchor_url" in cols else ("url" if "url" in cols else "id")
            count_cur = conn.execute(f"""
                SELECT COUNT(*), COUNT(DISTINCT {fp_expr}), COUNT(DISTINCT {au_expr}) FROM chunks
            """)
            total_chunks, total_files, total_sections = count_cur.fetchone()

            meta["total_chunks"] = total_chunks
            meta["total_files"] = total_files
            meta["total_sections"] = total_sections

            # Get size on disk
            try:
                meta["size_bytes"] = self.db_path.stat().st_size
                meta["size_mb"] = round(meta["size_bytes"] / (1024 * 1024), 2)
            except Exception:
                meta["size_bytes"] = 0
                meta["size_mb"] = 0.0

            return meta

    def get_site_tree(self) -> Dict[str, Any]:
        """Retrieve stored site or codebase hierarchy tree."""
        with self._get_connection() as conn:
            cur = conn.execute("SELECT value FROM site_meta WHERE key = 'site_graph'")
            row = cur.fetchone()
            if row:
                return json.loads(row[0])

            # Generate hierarchical tree from distinct files and sections
            tree_cur = conn.execute("SELECT DISTINCT file_path, section_title, anchor_url FROM chunks")
            tree: Dict[str, List[Dict[str, str]]] = {}
            for fp, st, au in tree_cur.fetchall():
                key = fp or "documentation"
                if key not in tree:
                    tree[key] = []
                tree[key].append({"section": st, "anchor_url": au})
            return tree
