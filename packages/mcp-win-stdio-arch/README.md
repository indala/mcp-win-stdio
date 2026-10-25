# mcp-win-stdio-arch

Universal Architecture Knowledge Graph & Blueprint Model Context Protocol (MCP) server.

Traces full-stack applications from Frontend UI (`Next.js`), Client Transport (`TanStack Query`, `Axios`), Ingress Routes (`NestJS`), Domain Services, and Data Storage (`Drizzle ORM`, `PostgreSQL`/`MySQL`).

## Tools Provided

1. `blueprint_feature(domain, workspace_root)`: Generates full-stack vertical blueprint with Mermaid flowchart.
2. `blueprint_trace(target, workspace_root)`: Ordered vertical execution path with source evidence and line numbers.
3. `blueprint_erd(domain, workspace_root)`: Entity-Relationship Diagram (ERD) with tables, columns, and foreign keys.
4. `blueprint_impact(node_id, direction, workspace_root)`: Upstream & downstream blast-radius analysis.
5. `blueprint_audit(workspace_root)`: Architectural linting (missing FK indexes, broken routes, layer leaks, orphan entities).
