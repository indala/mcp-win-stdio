# mcp-win-stdio-word

Windows-optimized **Model Context Protocol (MCP)** server for Microsoft Word documents (`.docx` and `.doc`): 10 high-precision inspection, layout geometry, typography, and image extraction tools for Claude.

Part of the **`mcp-win-stdio`** Windows-optimized suite.

---

## 🚀 Features (10 Tools)

- **Advanced Page Layout Geometry**: Extracts paper sizes (Letter, A4), exact margins across 4 units (inches, cm, mm, pt), printable area, and section break types (Continuous vs New Page).
- **Multi-Column Analysis**: Detects multi-column layouts (IEEE / academic journal style), column widths, gaps, and separator lines.
- **Paragraph Spacing & Indentation**: Inspects line spacing (single, 1.15, 1.5, double, exact pt), space before/after in pt, first-line indents, hanging indents, and pagination rules (widow/orphan control).
- **Typography & Formatting**: Extracts font families (Times New Roman, Arial, Calibri), font sizes in pt, hex colors (`#002060`), highlights, and paragraph alignments.
- **Image & Visuals Extraction**: Identifies inline vs floating anchor images, placement offsets, dimensions, and header/footer logo positions.
- **Tables & Full Reader**: Extracts tables in Markdown or structured JSON, outlines, and complete document bodies.

---

## 🛠️ Included Tools (10 Tools)

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
