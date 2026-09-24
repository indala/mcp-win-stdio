# mcp-win-stdio-word

Windows-optimized **Model Context Protocol (MCP)** server for Microsoft Word documents (`.docx`).

Provides 10 high-precision inspection and layout analysis tools for Claude Desktop and Claude Code CLI.

---

## 🌟 Features (10 Tools)

* **Layout & Geometry**: `get_document_layout` (exact margins in inches, cm, mm, pt, paper format, multi-column analysis, section breaks)
* **Spacing & Indents**: `get_paragraph_spacing_and_indentation` (line spacing, space before/after in pt, first-line and hanging indents, pagination controls)
* **Typography**: `get_document_typography` (font family, font size in pt, hex colors `#002060`, highlights, paragraph alignments)
* **Visuals & Tables**: `get_document_images` (inline vs floating anchor images, placement offsets, dimensions), `get_document_tables`, `get_headers_and_footers`
* **Content & Search**: `read_word_document`, `search_word_document`, `get_document_outline`, `get_document_metadata`

---

## 📦 Installation

```powershell
pip install mcp-win-stdio-word
```

---

## 🚀 Usage with Claude Desktop

Add to `%APPDATA%\Claude\claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "word": {
      "command": "python",
      "args": [
        "-m",
        "mcp_win_stdio.word"
      ]
    }
  }
}
```

---

## 📜 License
MIT License. Copyright (c) 2026 Mohan Kumar Indala.
