import sys
import os
from pathlib import Path

# Add packages to path
for p in Path("packages").glob("*/src"):
    sys.path.insert(0, str(p.resolve()))

from mcp_win_stdio.word.server import (
    create_document,
    add_heading,
    add_paragraph,
    fill_template,
    replace_text,
    export_to_pdf
)

test_doc = "scratch/test_live_author.docx"
print("1. Testing create_document...")
res1 = create_document(test_doc, title="Client Project Statement", author="Antigravity")
print("   Create status:", res1.get("status"), "size:", res1.get("file_size_bytes"))
assert res1.get("status") == "success"

print("2. Testing add_heading...")
res2 = add_heading(test_doc, "Executive Summary", level=1)
print("   Heading status:", res2.get("status"), "heading:", res2.get("heading"))
assert res2.get("status") == "success"

print("3. Testing add_paragraph...")
res3 = add_paragraph(
    test_doc,
    "This statement of work is prepared for {{client_name}} on {{agreement_date}}.",
    font_name="Calibri",
    font_size_pt=11,
    bold=False,
    color_hex="002060"
)
print("   Paragraph status:", res3.get("status"), "index:", res3.get("paragraph_index"))
assert res3.get("status") == "success"

print("4. Testing fill_template...")
filled_doc = "scratch/test_live_filled.docx"
res4 = fill_template(
    template_path=test_doc,
    output_path=filled_doc,
    replacements={
        "{{client_name}}": "Acme Productions Ltd",
        "{{agreement_date}}": "October 7, 2026"
    }
)
print("   Template status:", res4.get("status"), "replacements:", res4.get("total_replacements_applied"))
assert res4.get("total_replacements_applied") == 2

print("5. Testing replace_text...")
res5 = replace_text(filled_doc, "Acme Productions Ltd", "Acme International Studios")
print("   Replace status:", res5.get("status"), "count:", res5.get("occurrences_replaced"))
assert res5.get("occurrences_replaced") == 1

print("6. Testing export_to_pdf...")
pdf_path = "scratch/test_live_final.pdf"
res6 = export_to_pdf(filled_doc, pdf_path)
print("   PDF status:", res6.get("status"), "size:", res6.get("pdf_size_bytes"))
assert res6.get("status") == "success"
assert os.path.getsize(pdf_path) > 0

print("\n>>> ALL WORD AUTHORING TOOLS TESTED AND VERIFIED 100%! <<<")
