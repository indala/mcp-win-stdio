import os
from pathlib import Path
import docx
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH

# Test creating doc
doc = docx.Document()
sec = doc.sections[0]
sec.top_margin = Inches(1.0)
sec.bottom_margin = Inches(1.0)
doc.add_heading("Automated Word Document Report", level=1)
p = doc.add_paragraph()
r = p.add_run("Created with mcp-win-stdio-word authoring suite. {{token}}")
r.bold = True
r.font.name = "Arial"
r.font.size = Pt(12)
r.font.color.rgb = RGBColor(0x00, 0x20, 0x60)

doc.save("scratch/test_authored.docx")
print("Authored doc saved successfully.")

# Test image insertion if image exists
import win32com.client
word = win32com.client.DispatchEx("Word.Application")
word.Visible = False
word.DisplayAlerts = False
try:
    src = os.path.abspath("scratch/test_authored.docx")
    pdf = os.path.abspath("scratch/test_authored.pdf")
    wdoc = word.Documents.Open(src)
    wdoc.SaveAs2(pdf, FileFormat=17)
    wdoc.Close(False)
    print("PDF export successful, size:", os.path.getsize(pdf))
finally:
    word.Quit()
