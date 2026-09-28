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

Available Tools (6 Tools):
--------------------------------------------------------------------------------
1.  get_tsc_errors
    - Returns active TypeScript compilation errors from cache (0ms latency).
    - Optional filters: project_path (str), tsconfig_path (str)

2.  get_file_errors
    - Returns TypeScript errors for a specific .ts / .tsx / .js / .jsx file.
    - Args: file_path (str)

3.  get_error_summary
    - Returns error counts per project and top 5 most common error codes (e.g. TS2322).

4.  list_watched_projects
    - Lists all active tsconfig.json files and current watcher statuses.

5.  watch_project
    - Dynamically verifies 'tsc', scans for tsconfig.json, and starts background
      watchers for a target project directory without restarting the server.
    - Args: project_path (str)

6.  restart_tsc_watcher
    - Restarts all watchers and flushes diagnostics.

--------------------------------------------------------------------------------
Environment Variables:
--------------------------------------------------------------------------------
* TSC_WATCH_DIR: Base directory to scan and watch for tsconfig.json files.
  - If NOT set: Server stays in standby mode until 'watch_project' is called.
  - Safety guard: Refuses to watch C:\\Users\\<user>, AppData, or root drive.

--------------------------------------------------------------------------------
Example Prompts for Claude:
--------------------------------------------------------------------------------
* "Watch the TypeScript project at 'Z:/projects/my-web-app'."
* "Check if there are any TypeScript errors in my project right now."
* "Are there any type errors in src/components/Dashboard.tsx?"
================================================================================
"""
    print(guide_text)


def print_tsc_guide() -> None:
    print_guide()
