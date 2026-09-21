"""
Usage guide and Claude prompt recipes for Word MCP server.
"""

def print_guide() -> None:
    guide_text = """
================================================================================
          Word Document MCP (Advanced Layout & Typography Edition)
================================================================================

Description:
  10 specialized tools to extract complete document contents, advanced page geometry,
  exact margins (in, cm, mm, pt), multi-column layouts (IEEE/Journal), paragraph
  spacing & indentation, typography (fonts, sizes, hex colors), tables, outline,
  floating/inline images, and metadata from .docx and legacy .doc files.

Available Tools (10 Tools):
--------------------------------------------------------------------------------
1.  get_document_layout
    - Extracts paper sizes (Letter, A4), margins across 4 units (inches, cm, mm, pt),
      printable area, multi-column layout (columns, width, gap, separators),
      section break types (CONTINUOUS, NEW_PAGE), header/footer edge distances.
    - Args: file_path (str)

2.  get_paragraph_spacing_and_indentation
    - Extracts line spacing (single, 1.15, 1.5, double, exact pt), space before/after (pt),
      first-line & hanging indents (in, cm), pagination rules (keep_with_next, widow_control).
    - Args: file_path (str), start_paragraph (int, default=0), max_paragraphs (int, default=50)

3.  get_document_typography
    - Extracts font families (Times New Roman, Arial), font sizes (pt), hex colors (#000000,
      #002060), highlights, and paragraph alignments (LEFT, CENTER, RIGHT, JUSTIFY).
    - Args: file_path (str), start_paragraph (int, default=0), max_paragraphs (int, default=50)

4.  get_document_images
    - Extracts images across headers, footers, body paragraphs, and tables along with
      placement type (INLINE vs FLOATING_ANCHOR), alignments, offsets, and dimensions.
    - Args: file_path (str)

5.  get_headers_and_footers
    - Extracts primary, first-page, and even/odd page headers/footers with typography and images.
    - Args: file_path (str)

6.  get_document_tables
    - Extracts all tables in Markdown or structured JSON format.
    - Args: file_path (str), output_format (str: 'markdown' | 'json')

7.  get_document_outline
    - Extracts document heading tree (Title, Heading 1 - 4) with paragraph indices.
    - Args: file_path (str)

8.  get_document_metadata
    - Extracts core document properties: author, title, revisions, dates, word count.
    - Args: file_path (str)

9.  read_word_document
    - Full reader returning body paragraphs with markdown formatting, tables, and headers/footers.
    - Args: file_path (str), output_format (str: 'markdown' | 'json')

10. search_word_document
    - Searches for keywords or regex patterns across body, headers, footers, and table cells.
    - Args: file_path (str), query (str), case_sensitive (bool, default=False)

--------------------------------------------------------------------------------
Example Prompts for Claude:
--------------------------------------------------------------------------------
* "Analyze the page layout and margins of 'paper_template.docx' and tell me if it follows IEEE 2-column format."
* "Check all fonts and font sizes used in 'report.docx' and make sure the body text is 10pt Times New Roman."
* "Extract all tables from 'data_spec.docx' into clean Markdown tables."
* "Find the logo image in the header of 'proposal.docx' and check its dimensions and placement."
================================================================================
"""
    print(guide_text)


def print_word_guide() -> None:
    print_guide()
