"""
Usage guide and Claude prompt recipes for TypeScript Watcher MCP server.
"""

def print_guide() -> None:
    guide_text = """
================================================================================
           TypeScript Diagnostic Watcher MCP Server (mcp-win-stdio.tsc)
================================================================================

Description:
  Background TypeScript file watcher maintaining an in-memory diagnostic cache
  for instant (0ms latency) TypeScript error checking across multi-tsconfig projects.

Available Tools (6 Tools):
--------------------------------------------------------------------------------
1.  get_tsc_errors
    - Returns all active TypeScript compilation errors from cache.
    - Optional filters: project_path (str), tsconfig_path (str)

2.  get_file_errors
    - Returns TypeScript errors for a specific .ts / .tsx / .js / .jsx file.
    - Args: file_path (str)

3.  get_error_summary
    - Returns error counts per project and top 5 most common error codes (e.g. TS2322).

4.  list_watched_projects
    - Lists all active tsconfig.json files and current watcher statuses.

5.  watch_project
    - Dynamically adds a new project directory to watch without restarting the server.
    - Args: project_path (str)

6.  restart_tsc_watcher
    - Restarts all watchers and flushes diagnostics.

--------------------------------------------------------------------------------
Environment Variables:
--------------------------------------------------------------------------------
* TSC_WATCH_DIR: Base directory to scan and watch for tsconfig.json files.
  (Defaults to current workspace directory if not specified).

--------------------------------------------------------------------------------
Example Prompts for Claude:
--------------------------------------------------------------------------------
* "Check if there are any TypeScript errors in my project right now."
* "Are there any type errors in src/components/Dashboard.tsx?"
* "Watch the project located at 'Z:/projects/IJITEST Main' for TypeScript diagnostics."
================================================================================
"""
    print(guide_text)


def print_tsc_guide() -> None:
    print_guide()
