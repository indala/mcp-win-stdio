"""
Usage guide and Claude prompt recipes for TypeScript Watcher MCP server.
"""


def print_guide() -> None:
    guide_text = """
================================================================================
           TypeScript Diagnostic Watcher MCP Server (mcp-win-stdio.tsc)
================================================================================

Description:
  Background TypeScript compiler watcher maintaining an in-memory diagnostic cache
  for instant (0ms latency) TypeScript error checking across multi-tsconfig projects.

Safety & Standby Architecture:
  * Zero Admin/AppData default crawling: If TSC_WATCH_DIR is not explicitly set,
    the watcher starts safely in standby mode without scanning system or home folders.
  * Compiler Pre-Check: Verifies TypeScript compiler ('tsc') availability before
    scanning or watching files, returning clear installation guidance if missing.

Available Tools (12 Tools):
--------------------------------------------------------------------------------
1.  list_projects
    - Lists all configured TypeScript projects (from ~/.mcp-win-stdio/tsc_projects.json
      and active background watchers), indicating the active sticky project, watcher status,
      error counts, and compiler binary.

2.  use_project
    - Switches the active default TypeScript project context by alias or directory path.
      All subsequent diagnostic queries automatically target this project.
    - Args: project (str)

3.  add_project
    - Registers and persists a new TypeScript project to ~/.mcp-win-stdio/tsc_projects.json.
      Optionally starts background watchers and waits for initial compilation.
    - Args: project_path (str), alias (optional str), auto_watch (bool), description (optional str)

4.  remove_project
    - Removes a registered project from ~/.mcp-win-stdio/tsc_projects.json and optionally
      terminates background compiler processes.
    - Args: project (str), stop_watcher (bool)

5.  get_tsc_errors
    - Returns active TypeScript compilation errors from cache (0ms latency).
    - Context-window protected, paginated, and token-safe.
    - Optional filters: project_path (alias or path), tsconfig_path (str), error_code (str)

6.  suggest_error_fixes
    - Instant actionable fix recommendations, explanation, and code patterns
      for common TypeScript compiler errors (e.g. TS2304, TS2322, TS2339, TS2345).
    - Args: error_code (str), message (optional str)

7.  get_error_category_breakdown
    - High-level categorization of all active TypeScript errors into semantic groups:
      type_mismatch, missing_declaration, nullability, imports, jsx, config.
    - Optional filter: project (str)

8.  get_file_errors
    - Returns TypeScript errors for a specific .ts / .tsx / .js / .jsx file.
    - Args: file_path (str), project (optional str), limit (int), offset (int), max_message_chars (int)

9.  get_error_summary
    - Returns error counts per project and top 5 most common error codes (e.g. TS2322).
    - Optional filter: project (str)

10. list_watched_projects
    - Granular list of all individual tsconfig.json files and current watcher statuses.

11. watch_project
    - Dynamically verifies 'tsc', scans for tsconfig.json, registers project, and starts
      background watchers without restarting the server.
    - Args: project_path (str)

12. restart_tsc_watcher
    - Restarts all watchers across registered projects and flushes diagnostics.

--------------------------------------------------------------------------------
Dynamic Multi-Project Configuration:
--------------------------------------------------------------------------------
* Registered projects are stored in ~/.mcp-win-stdio/tsc_projects.json (like ssh and git).
* No mandatory environment variables needed!
* Use 'add_project' to add folders and 'use_project' to switch active context.
* Backward compatibility: TSC_WATCH_DIR is still supported as a fallback if present.

--------------------------------------------------------------------------------
Example Prompts for Claude:
--------------------------------------------------------------------------------
* "Watch the TypeScript project at 'Z:/projects/my-web-app'."
* "Check if there are any TypeScript errors in my project right now."
* "Are there any type errors in src/components/Dashboard.tsx?"
* "How do I fix TypeScript error TS2322 in my component?"
================================================================================
"""
    print(guide_text)


def print_tsc_guide() -> None:
    print_guide()
