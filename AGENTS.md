# Repository Agent Guidelines

This repository is equipped with the **mcp-win-stdio (`mws`)** tool suite.

## 🛠️ Active Tools & Recommended Selection

* **Spreadsheets & Excel:** Use `excel` MCP (`preview_sheet`, `update_cells`, `profile_sheet`).
* **Word Documents:** Use `word` MCP for typography, layout, and document generation.
* **Code Navigation:** Use `explorer` MCP (`get_directory_tree`, `fuzzy_find`, `grep_search`).
* **TypeScript:** Use `tsc` MCP for 0ms compiler diagnostic checks.
* **Database Operations:** Use `db` MCP (`read_query`, `execute_query`, `describe_table`).
* **Git & PRs:** Use `git` MCP for status, diffs, commits, and GitHub API interactions.
* **Remote Shells:** Use `ssh` MCP for multi-host pooling and SFTP.
* **Documentation & Web RAG:** Use `rag` MCP (`crawl_and_index_url`, `query_knowledge_base`, `get_knowledge_tree`).
* **High-Speed Pipelines & Streaming:** Use `excel-db` MCP (`db_to_excel_stream`, `excel_to_db_upsert`, `query_unified_sources`, `reconcile_db_vs_excel`).

## ⚠️ Excel File Locking Protocol (CRITICAL)

When editing or updating Excel workbooks (`.xlsx`), if a `PermissionError`, `WinError 32`, or `FILE LOCKED BY EXCEL` error occurs:
* **The file is locked because the user has it open in Microsoft Excel desktop.**
* **DO NOT** attempt terminal workarounds, PowerShell scripts, writing temporary python scripts, or saving to random scratch files.
* **Immediately ask the user**: *"Please save and close `<filename>` in Microsoft Excel so I can apply the changes."*
* Once the user confirms that the workbook is closed, re-invoke the appropriate Excel MCP tool (`update_cells`, `format_cells`, etc.).
