"""
User and LLM guide for mcp-win-stdio-explorer.
"""

GUIDE_TEXT = """
# ================================================================
# MCP-WIN-STDIO-EXPLORER: USER & LLM GUIDE (11 Tools)
# ================================================================

Provides 11 specialized tools for token-safe directory navigation,
smart .gitignore awareness, in-file grep, RapidFuzz fuzzy search,
and code symbol extraction:

1. DIRECTORY LISTING & NAVIGATION
   - list_dir(path, filter_pattern, sort_by, limit, offset):
     Detailed directory listing (PowerShell Get-ChildItem style) with sizes,
     child counts, and heavy build directory flags.
   - get_directory_tree(path, max_depth, ignore_mode, collapse_heavy_dirs):
     Depth-controlled hierarchy tree. Automatically collapses node_modules,
     .next, dist, and .git into informative summary nodes to prevent token bloat.

2. ADVANCED FILE SEARCH
   - find_files(search_path, pattern, extensions, min/max_size, modified_after):
     Advanced glob search honoring .gitignore and build caches.
   - fuzzy_find(query, search_path, extensions, score_cutoff):
     RapidFuzz typo-tolerant search. Find files by abbreviation (e.g. 'usrctrl').

3. IN-FILE CONTENT SEARCH (GREP)
   - grep_search(query, search_path, is_regex, context_lines, max_matches):
     Search text or regex INSIDE file contents across the workspace.

4. TOKEN-SAFE READING
   - read_file(file_path, start_line, end_line, line_numbers, max_lines):
     Windowed file reader with automatic binary detection/protection.
   - read_head_tail(file_path, mode, lines):
     Quick top N (head) or bottom N (tail) line peek for logs/CSVs.

5. CODE STRUCTURE & DIAGNOSTICS
   - get_code_outline(file_path):
     Extracts classes, functions, arguments, docstrings, and line numbers
     from Python (AST), JS/TS, and JSON without loading the whole file!
   - get_file_info(path, include_hash):
     Full diagnostics (timestamps, line count, CRLF/LF, MD5/SHA256).
   - workspace_summary(path):
     Folder disk usage, file count breakdown by extension, recent files, Git status.
   - export_tree_to_file(path, output_file_path, format):
     Writes a complete un-truncated workspace map directly to disk.

# ================================================================
"""

def print_guide() -> None:
    print(GUIDE_TEXT.strip())
