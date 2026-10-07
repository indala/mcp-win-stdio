# mcp-win-stdio-word

Windows-optimized **Model Context Protocol (MCP)** server for Microsoft Word documents (`.docx` and `.doc`): 20 high-precision inspection, layout geometry, typography, document authoring, templating, and native COM PDF export tools for Claude.

Part of the **`mcp-win-stdio`** Windows-optimized suite.

---

## 🚀 Features (20 Tools)

- **Complete Document Authoring**: Create new `.docx` documents (`create_document`) with paper sizes (A4, Letter, Legal, A3), orientations, margins, and core metadata.
- **Rich Paragraphs & Headings**: Append formatted headings (`add_heading`) and paragraphs (`add_paragraph`) with custom font families, sizes, hex colors, alignments, and line spacing.
- **Automated Template Population**: Fill placeholder tokens like `{{client_name}}` and `{{invoice_date}}` (`fill_template`) across paragraphs, tables, and headers/footers while preserving styling.
- **Native Windows Word COM PDF Export**: High-fidelity `.pdf` generation (`export_to_pdf`) powered by Microsoft Word desktop automation.
- **Find, Replace & Images**: Document-wide search & replace (`replace_text`) and image embedding with dimension scaling and captions (`insert_image`).
- **Advanced Page Layout Geometry**: Extracts paper sizes, exact margins across 4 units (inches, cm, mm, pt), printable area, and multi-column layout (IEEE / academic style).
- **Paragraph Spacing & Indentation**: Inspects line spacing, space before/after, first-line & hanging indents, and widow/orphan control.
- **Typography & Formatting**: Extracts font families, sizes in pt, hex colors, highlights, and paragraph alignments.
- **Tables, Outlines & Reader**: Extracts tables in Markdown or structured JSON, outlines, and complete document bodies.

---

## 🛠️ Included Tools (20 Tools)

1. `get_document_layout`: Paper sizes, margins in 4 units (in, cm, mm, pt), multi-column layout, printable area.
2. `get_paragraph_spacing_and_indentation`: Line spacing, space before/after (pt), first-line & hanging indents.
3. `get_document_typography`: Font names, sizes (pt), hex colors, highlights, text alignment.
4. `get_document_images`: Images across body, headers, footers, tables with positioning and dimensions.
5. `get_headers_and_footers`: Primary, first-page, and even/odd headers/footers with typography.
6. `get_document_tables`: Extracts all tables in clean Markdown or structured JSON.
7. `get_document_outline`: Heading hierarchy (Title, Heading 1 - 4) with paragraph indices.
8. `get_document_metadata`: Author, title, revision, word count, timestamps.
9. `read_word_document`: Complete body paragraphs, tables, and headers with formatting.
10. `search_word_document`: Keyword and regex search across body, headers, footers, and tables.
11. `edit_paragraph`: Modifies existing paragraph text, style, or formatting in place.
12. `insert_table`: Inserts a new formatted table with headers and data rows.
13. `inspect_revisions_and_comments`: Extracts comments, tracked insertions, and tracked deletions.
14. `create_document`: Creates a new empty .docx file with custom page setup, paper size, orientation, and margins.
15. `add_paragraph`: Appends a styled paragraph with custom font family, size, bold, italic, hex color, alignment, spacing.
16. `add_heading`: Appends a heading (level 1-9) or Title (level 0).
17. `fill_template`: Populates placeholders across paragraphs, tables, and headers/footers while preserving styles.
18. `replace_text`: Global find-and-replace across the entire document.
19. `insert_image`: Inserts an image with dimensions and optional caption.
20. `export_to_pdf`: Exports .docx to high-fidelity PDF using native Windows Word COM automation.

---

## 📦 Installation

```powershell
pip install mcp-win-stdio-word
```
*(Installing this package automatically installs `mws` CLI orchestrator)*.

---

## 🚀 One-Command Claude Setup

```powershell
mws setup word
# or:
mws add word
```

### Manual Configuration Example
In `%APPDATA%\Claude\claude_desktop_config.json`:
```json
{
  "mcpServers": {
    "word": {
      "command": "python",
      "args": ["-m", "mcp_win_stdio.word"]
    }
  }
}
```

---

## 📖 CLI Commands & Interactive Guide

```powershell
mws word guide      # Complete tool reference & prompt recipes
mws word doctor     # Verify python-docx and PyWin32 COM readiness
mws word setup      # Configure Claude Desktop / Claude Code
mws word run        # Launch server over stdio
```

---

## 📜 License
MIT License. Copyright (c) 2026 Mohan Kumar Indala.
