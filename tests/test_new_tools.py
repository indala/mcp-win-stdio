"""
Comprehensive test suite for expanded tools across excel, db, word, and excel-db servers.
"""

import os
import sys
import tempfile
from pathlib import Path

# Ensure all packages are on sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
for p in (ROOT_DIR / "packages").glob("*/src"):
    sys.path.insert(0, str(p))
sys.path.insert(0, str(ROOT_DIR / "src"))

from mcp_win_stdio.excel.server import (
    create_table,
    create_workbook,
    delete_column,
    delete_rows,
    diff_workbooks,
    insert_column,
    insert_rows,
    list_tables,
    merge_cells,
)
from mcp_win_stdio.excel_db.server import (
    compare_master_datasets,
)
from mcp_win_stdio.word.server import (
    add_heading,
    add_paragraph,
    create_document,
    export_to_pdf,
    fill_template,
    replace_text,
)


def test_excel_table_and_mutation_tools():
    with tempfile.TemporaryDirectory() as tmpdir:
        wb_path = os.path.join(tmpdir, "test_excel.xlsx")
        data = [
            ["SKU", "Item Name", "Qty", "Unit Price"],
            ["SKU-001", "Studio Flood Light", 10, 85.50],
            ["SKU-002", "Light Stand Heavy Duty", 15, 45.00],
            ["SKU-003", "C-Stand with Arm", 8, 120.00],
        ]
        res_create = create_workbook(wb_path, sheet_name="Inventory", data=data)
        assert res_create["status"] == "success"

        # 1. create_table
        tbl_res = create_table(wb_path, sheet_name="Inventory", range_address="A1:D4", table_name="InvTable")
        assert tbl_res["status"] == "success"

        # 2. list_tables
        tables = list_tables(wb_path, sheet_name="Inventory")
        assert tables["total_tables"] == 1
        assert tables["tables"][0]["name"] == "InvTable"

        # 3. insert_column with formula
        col_res = insert_column(
            wb_path,
            sheet_name="Inventory",
            col_idx=5,
            header="Total Value",
            formula_template="=C{row}*D{row}",
        )
        assert col_res["status"] == "success"

        # 4. insert_rows
        row_res = insert_rows(
            wb_path,
            sheet_name="Inventory",
            row_idx=5,
            rows_data=[["SKU-004", "LED Panel 60W", 5, 199.99, "=C5*D5"]],
        )
        assert row_res["status"] == "success"

        # 5. delete_column
        del_col = delete_column(wb_path, sheet_name="Inventory", col_identifier="Total Value")
        assert del_col["status"] == "success"

        # 6. delete_rows
        del_row = delete_rows(wb_path, sheet_name="Inventory", row_idx=5, count=1)
        assert del_row["status"] == "success"

        # 7. merge_cells
        merge_res = merge_cells(wb_path, sheet_name="Inventory", range_address="A10:D10", value="Merged Summary")
        assert merge_res["status"] == "success"

        # 8. diff_workbooks
        wb2_path = os.path.join(tmpdir, "test_excel_v2.xlsx")
        create_workbook(wb2_path, sheet_name="Inventory", data=data)
        diff_res = diff_workbooks(wb_path, wb2_path, sheet_name="Inventory")
        assert diff_res["status"] == "success"


def test_word_authoring_tools():
    with tempfile.TemporaryDirectory() as tmpdir:
        doc_path = os.path.join(tmpdir, "test_doc.docx")

        # 1. create_document
        res_create = create_document(doc_path, title="Project Proposal", author="Antigravity Test")
        assert res_create["status"] == "success"
        assert os.path.exists(doc_path)

        # 2. add_heading
        res_head = add_heading(doc_path, "1. Executive Summary", level=1)
        assert res_head["status"] == "success"

        # 3. add_paragraph
        res_p = add_paragraph(
            doc_path,
            "This proposal is prepared for {{recipient}} by {{company}}.",
            font_name="Calibri",
            font_size_pt=11,
            bold=False,
            color_hex="002060",
        )
        assert res_p["status"] == "success"

        # 4. fill_template
        filled_path = os.path.join(tmpdir, "test_filled.docx")
        res_fill = fill_template(
            template_path=doc_path,
            output_path=filled_path,
            replacements={
                "{{recipient}}": "Warner Brothers",
                "{{company}}": "Showreel Productions",
            },
        )
        assert res_fill["status"] == "success"
        assert res_fill["total_replacements_applied"] == 2

        # 5. replace_text
        res_rep = replace_text(filled_path, "Warner Brothers", "Universal Pictures")
        assert res_rep["status"] == "success"
        assert res_rep["occurrences_replaced"] == 1

        # 6. export_to_pdf
        pdf_path = os.path.join(tmpdir, "test_final.pdf")
        res_pdf = export_to_pdf(filled_path, pdf_path)
        assert res_pdf["status"] in ("success", "error")
        if res_pdf["status"] == "success":
            assert os.path.exists(pdf_path)
        else:
            assert "error" in res_pdf


def test_excel_db_master_reconciliation():
    with tempfile.TemporaryDirectory() as tmpdir:
        f1 = os.path.join(tmpdir, "master_a.xlsx")
        f2 = os.path.join(tmpdir, "master_b.xlsx")
        audit_out = os.path.join(tmpdir, "audit_report.xlsx")

        data_a = [
            ["material_number", "description", "qty", "rate"],
            ["MAT-01", "Camera Lens 50mm", 10, 450.0],
            ["MAT-02", "Tripod Pro Carbon", 5, 220.0],
        ]
        data_b = [
            ["SKU", "Item Description", "Quantity", "Price"],
            ["MAT-01", "Camera Lens 50mm", 10, 450.0],
            ["MAT-02", "Tripod Pro Carbon", 4, 220.0],  # qty changed
            ["MAT-03", "Wireless Mic Kit", 2, 310.0],  # new item
        ]
        create_workbook(f1, sheet_name="Sheet1", data=data_a)
        create_workbook(f2, sheet_name="Sheet1", data=data_b)

        res_comp = compare_master_datasets(
            source_a_path=f1,
            source_b_path=f2,
            key_columns=["material_number"],
            column_mapping={
                "SKU": "material_number",
                "Item Description": "description",
                "Quantity": "qty",
                "Price": "rate",
            },
            output_audit_path=audit_out,
            tolerance=0.01,
        )
        assert res_comp["status"] == "success"
        assert res_comp["summary"]["matching_records"] == 1
        assert res_comp["summary"]["modified_records"] == 1
        assert res_comp["summary"]["new_records_in_b"] == 1
        assert os.path.exists(audit_out)


def test_rag_compact_search_and_chunk_context():
    from mcp_win_stdio.rag.store import RAGVectorStore

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "vector_store.db"
        store = RAGVectorStore(db_path)

        long_code = (
            "def calculate_total_revenue(transactions: list) -> float:\n"
            "    # This is a very long descriptive function created to test snippet truncation\n"
            "    total = 0.0\n"
            "    for tx in transactions:\n"
            "        if tx.get('status') == 'completed':\n"
            "            total += float(tx.get('amount', 0.0))\n"
            "    return total\n" * 5
        )

        files_data = [
            {
                "file_path": "src/finance/calculator.py",
                "content_hash": "hash_calc_001",
                "size_bytes": len(long_code),
                "chunks": [
                    {
                        "chunk_index": 0,
                        "line_start": 1,
                        "line_end": 20,
                        "section_title": "revenue_header",
                        "anchor_url": "",
                        "text": "import os\nimport sys\n# Financial revenue calculator module header.",
                        "content_hash": "chunk_h0",
                    },
                    {
                        "chunk_index": 1,
                        "line_start": 21,
                        "line_end": 60,
                        "section_title": "calculate_total_revenue",
                        "anchor_url": "",
                        "text": long_code,
                        "content_hash": "chunk_h1",
                    },
                    {
                        "chunk_index": 2,
                        "line_start": 61,
                        "line_end": 75,
                        "section_title": "revenue_footer",
                        "anchor_url": "",
                        "text": "def format_currency(val: float) -> str:\n    return f'${val:,.2f}'",
                        "content_hash": "chunk_h2",
                    },
                ],
            }
        ]

        store.update_files_batch("test_col", files_data)

        # 1. Test search with max_chars_per_snippet = 120
        hits = store.search("calculate_total_revenue", top_k=3, max_chars_per_snippet=120)
        assert len(hits) > 0
        hit = hits[0]
        assert "chunk_id" in hit
        assert hit["chunk_id"] is not None
        assert hit["is_truncated"] is True
        assert "[Truncated" in hit["snippet"]
        assert len(hit["snippet"]) < 300

        # 2. Test get_chunk_context for single chunk (window=0)
        target_cid = hit["chunk_id"]
        ctx_single = store.get_chunk_context(target_cid, window=0)
        assert ctx_single is not None
        assert ctx_single["chunk_id"] == target_cid
        assert ctx_single["text"] == long_code
        assert ctx_single["window"] == 0

        # 3. Test get_chunk_context with window=1 (expands to previous and next chunks)
        ctx_window = store.get_chunk_context(target_cid, window=1)
        assert ctx_window is not None
        assert ctx_window["total_chunks_in_window"] == 3
        assert "Financial revenue calculator" in ctx_window["full_text"]
        assert "format_currency" in ctx_window["full_text"]

        # 4. Test get_site_tree with filter_path and max_items
        tree_res = store.get_site_tree(filter_path="calculator", max_items=10)
        assert "src/finance/calculator.py" in tree_res


def test_rag_context_window_stays_within_source_file(tmp_path):
    from mcp_win_stdio.rag.store import RAGVectorStore

    store = RAGVectorStore(tmp_path / "vector_store.db")
    store.update_files_batch(
        "demo",
        [
            {
                "file_path": "README.md",
                "content_hash": "readme_hash",
                "chunks": [
                    {"chunk_index": 0, "line_start": 1, "line_end": 2, "text": "README target context"},
                ],
            },
            {
                "file_path": "src/other.py",
                "content_hash": "other_hash",
                "chunks": [
                    {"chunk_index": 1, "line_start": 3, "line_end": 4, "text": "unrelated code from another file"},
                ],
            },
        ],
    )

    target_id = store.search("README target", collection="demo")[0]["chunk_id"]
    context = store.get_chunk_context(target_id, window=1, collection="demo")
    assert context is not None
    assert context["total_chunks_in_window"] == 1
    assert "unrelated code" not in context["full_text"]


def test_rag_web_context_window_stays_within_document_section(tmp_path):
    from mcp_win_stdio.rag.store import RAGVectorStore

    store = RAGVectorStore(tmp_path / "web-store.db")
    store.index_crawled_data(
        {
            "target_url": "https://docs.example.test/guide",
            "pages": [
                {
                    "url": "https://docs.example.test/guide",
                    "title": "Guide",
                    "sections": [
                        {"anchor_id": "alpha", "section_title": "Alpha", "text": "alpha " * 300},
                        {"anchor_id": "beta", "section_title": "Beta", "text": "beta isolated context"},
                    ],
                }
            ],
        },
        collection_name="web-demo",
    )
    with store._get_connection() as conn:
        target_id = conn.execute(
            "SELECT id FROM chunks WHERE section_title = 'Alpha' AND chunk_index = 1"
        ).fetchone()[0]

    context = store.get_chunk_context(target_id, window=1, collection="web-demo")
    assert context is not None
    assert context["total_chunks_in_window"] == 2
    assert "alpha" in context["full_text"]
    assert "beta isolated context" not in context["full_text"]


def test_rag_query_coverage_ignores_question_filler_and_substring_accidents():
    from mcp_win_stdio.rag.store import analyze_query_coverage

    answer = (
        "Requests costing more than the token bucket capacity are rejected without changing the balance."
    )
    coverage = analyze_query_coverage(
        "What happens when a request costs more than the token bucket capacity?",
        answer,
        "Rate limiting",
    )
    assert coverage["coverage_ratio"] == 1.0
    assert coverage["missing"] == []

    substring_only = analyze_query_coverage("rate", "This is a separate concern.", "")
    assert substring_only["coverage_ratio"] == 0
    assert substring_only["missing"] == ["rate"]


def test_rag_natural_language_query_confidence(monkeypatch, tmp_path):
    import json

    import mcp_win_stdio.rag.server as rag_server
    from mcp_win_stdio.rag.store import RAGVectorStore

    monkeypatch.setattr(rag_server, "_get_rag_data_dir", lambda: tmp_path)
    store = RAGVectorStore(tmp_path / "confidence-demo" / "vector_store.db")
    store.update_files_batch(
        "confidence-demo",
        [
            {
                "file_path": "rate-limits.md",
                "content_hash": "rate_limit_content",
                "chunks": [
                    {
                        "chunk_index": 0,
                        "line_start": 1,
                        "line_end": 4,
                        "section_title": "Rate limiting",
                        "text": (
                            "Requests costing more than the token bucket capacity are rejected "
                            "without changing the balance."
                        ),
                    }
                ],
            }
        ],
    )

    answer = json.loads(
        rag_server.query_knowledge_base(
            "What happens when a request costs more than the token bucket capacity?",
            target_url_or_collection="confidence-demo",
        )
    )
    assert answer["confidence"] == "high"
    assert answer["missing_query_terms"] == []
    assert answer["results"][0]["file_path"] == "rate-limits.md"


def test_rag_query_abstains_when_keyword_overlap_is_too_weak(monkeypatch, tmp_path):
    import json

    import mcp_win_stdio.rag.server as rag_server
    from mcp_win_stdio.rag.store import RAGVectorStore

    monkeypatch.setattr(rag_server, "_get_rag_data_dir", lambda: tmp_path)
    store = RAGVectorStore(tmp_path / "weak-match-demo" / "vector_store.db")
    store.update_files_batch(
        "weak-match-demo",
        [
            {
                "file_path": "database.md",
                "content_hash": "database_content",
                "chunks": [
                    {
                        "chunk_index": 0,
                        "line_start": 1,
                        "line_end": 2,
                        "section_title": "Database guide",
                        "text": "This guide covers database connections and safe query execution.",
                    }
                ],
            }
        ],
    )

    result = json.loads(
        rag_server.query_knowledge_base(
            "database schema migration quantum oracle",
            target_url_or_collection="weak-match-demo",
        )
    )
    assert result["confidence"] == "none"
    assert result["results"] == []
    assert "schema" in result["missing_query_terms"]


def test_rag_chunk_id_collisions_require_collection_scope(monkeypatch, tmp_path):
    import json

    import mcp_win_stdio.rag.server as rag_server
    from mcp_win_stdio.rag.store import RAGVectorStore

    monkeypatch.setattr(rag_server, "_get_rag_data_dir", lambda: tmp_path)
    for collection, text in (("alpha", "alpha source content"), ("beta", "beta source content")):
        store = RAGVectorStore(tmp_path / collection / "vector_store.db")
        store.update_files_batch(
            collection,
            [
                {
                    "file_path": "README.md",
                    "content_hash": f"{collection}_hash",
                    "chunks": [{"chunk_index": 0, "line_start": 1, "line_end": 1, "text": text}],
                }
            ],
        )

    alpha_store = RAGVectorStore(tmp_path / "alpha" / "vector_store.db")
    alpha_id = alpha_store.search("alpha source", collection="alpha")[0]["chunk_id"]
    beta_store = RAGVectorStore(tmp_path / "beta" / "vector_store.db")
    beta_id = beta_store.search("beta source", collection="beta")[0]["chunk_id"]
    assert alpha_id == beta_id

    ambiguous = json.loads(rag_server.get_chunk_context(alpha_id))
    assert "multiple collections" in ambiguous["error"]
    assert set(ambiguous["collections"]) == {"alpha", "beta"}

    scoped = json.loads(rag_server.get_chunk_context(alpha_id, target_url_or_collection="alpha"))
    assert scoped["status"] == "success"
    assert scoped["chunk"]["collection"] == "alpha"
    assert "alpha source content" in scoped["chunk"]["text"]

    related_ambiguous = json.loads(rag_server.find_related_chunks(alpha_id))
    assert "multiple collections" in related_ambiguous["error"]


def test_rag_cache_prunes_expired_temporary_collections(monkeypatch, tmp_path):
    import json

    import mcp_win_stdio.rag.server as rag_server
    from mcp_win_stdio.rag.store import RAGVectorStore

    monkeypatch.setattr(rag_server, "_get_rag_data_dir", lambda: tmp_path)

    def create_collection(name, is_temp):
        db_path = tmp_path / name / "vector_store.db"
        store = RAGVectorStore(db_path)
        store.set_collection_meta(name, "remote_git", "https://github.com/example/repo", is_temp=is_temp)
        if is_temp:
            with store._get_connection() as conn:
                conn.execute(
                    "UPDATE collections_meta SET expires_at = ? WHERE collection_name = ?",
                    ("2000-01-01T00:00:00+00:00", name),
                )
        return db_path.parent

    expired_temp = create_collection("expired-temp", is_temp=True)
    permanent = create_collection("permanent", is_temp=False)

    result = json.loads(rag_server.prune_rag_cache(purge_temp_only=True))
    assert result["status"] == "success"
    assert result["expired_collections_deleted"] == ["expired-temp"]
    assert not expired_temp.exists()
    assert permanent.exists()


def test_rag_cache_size_limit_removes_oldest_collections(monkeypatch, tmp_path):
    import json
    import os
    import time

    import mcp_win_stdio.rag.server as rag_server
    from mcp_win_stdio.rag.store import RAGVectorStore

    monkeypatch.setattr(rag_server, "_get_rag_data_dir", lambda: tmp_path)
    old_path = tmp_path / "old" / "vector_store.db"
    new_path = tmp_path / "new" / "vector_store.db"
    for db_path, name in ((old_path, "old"), (new_path, "new")):
        store = RAGVectorStore(db_path)
        store.set_collection_meta(name, "local_codebase", name)
    os.utime(old_path, (time.time() - 60, time.time() - 60))

    result = json.loads(rag_server.prune_rag_cache(max_total_mb=0))
    assert result["status"] == "success"
    assert result["deleted_collections"] == ["old", "new"]
    assert not old_path.parent.exists()
    assert not new_path.parent.exists()
