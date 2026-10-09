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
from mcp_win_stdio.word.server import (
    add_heading,
    add_paragraph,
    create_document,
    export_to_pdf,
    fill_template,
    replace_text,
)

from mcp_win_stdio.excel_db.server import (
    compare_master_datasets,
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
