# `Node.js & TypeScript (`node`, `tsc`, `npx`)`

> Runs background `tsc --watch` compiler diagnostics (resolved via local `node_modules/.bin/tsc`, global `tsc`, or `npx tsc`) and Node-based child MCP servers.

## Tool Metadata

| Property | Details |
| :--- | :--- |
| **Category** | External CLI & Binary |
| **Install / Prerequisite** | `winget install --id OpenJS.NodeJS -e` / `npm install -D typescript` |
| **Used By (`mcp-win-stdio`)** | `packages/mcp-win-stdio-tsc/src/mcp_win_stdio/tsc/server.py`, `tsc/cli.py`, `src/mcp_win_stdio/server/process_pool.py`, `src/mcp_win_stdio/cli.py` |

## Subcommands, Flags & Environment Variables

| Function Name / Variable | Attributes & Description |
| :--- | :--- |
| `node <script.js>` | `binary` · Node.js runtime used to execute local `node_modules/typescript/bin/tsc` and JS MCP servers. |
| `tsc --watch --noEmit --pretty false -p <tsconfig>` | `command` · Background TypeScript compiler watcher parsed into the 0ms diagnostic cache (`watch_project`). |
| `npx tsc ...` | `command` · Fallback TypeScript invocation when neither local nor global `tsc` is found. |
| `npx <mcp-package>` | `command` · Supported command runner in `process_pool.py` / `wizard.py` for custom JS/TS MCP servers. |
| `npm install -D typescript` / `@types/node` | `guidance` · Suggested package installation for project-local TypeScript & Node type definitions. |
