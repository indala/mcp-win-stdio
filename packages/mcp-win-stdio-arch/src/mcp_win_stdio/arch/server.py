"""
Server definition for mcp-win-stdio-arch (FastMCP)
Part of mcp-win-stdio.
"""

import os
from typing import Any, Dict, Optional, Tuple

try:
    from mcp.server.mcpserver import MCPServer as FastMCP
except (ImportError, ModuleNotFoundError):
    from mcp.server.fastmcp import FastMCP  # type: ignore[import-not-found]

from .graph import ArchitectureGraph
from .models import NodeKind
from .renderers import MermaidRenderer
from .scanner import ArchitectureScanner

mcp = FastMCP("arch-mcp")

# In-memory graph cache
_GRAPH = ArchitectureGraph()
_SCANNED_KEY: Optional[Tuple[str, Optional[str], Optional[str], Optional[str]]] = None
_LAST_DIAGNOSTICS: Dict[str, Any] = {}


def _ensure_graph(
    workspace_root: Optional[str] = None,
    frontend_path: Optional[str] = None,
    backend_path: Optional[str] = None,
    schema_path: Optional[str] = None,
) -> Tuple[ArchitectureGraph, Dict[str, Any]]:
    global _GRAPH, _SCANNED_KEY, _LAST_DIAGNOSTICS
    root = os.path.abspath(workspace_root) if workspace_root else os.getcwd()
    key = (root, frontend_path, backend_path, schema_path)

    if _SCANNED_KEY != key or _GRAPH.stats()["node_count"] == 0:
        _GRAPH.clear()
        scanner = ArchitectureScanner(
            workspace_root=root,
            frontend_root=frontend_path,
            backend_root=backend_path,
            schema_dir=schema_path,
        )
        _LAST_DIAGNOSTICS = scanner.scan_all(_GRAPH)
        _SCANNED_KEY = key

    return _GRAPH, _LAST_DIAGNOSTICS


@mcp.tool()
def blueprint_feature(
    domain: Optional[str] = None,
    workspace_root: Optional[str] = None,
    frontend_path: Optional[str] = None,
    backend_path: Optional[str] = None,
    schema_path: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Generates a full-stack vertical architecture blueprint for a domain feature.
    Connects: UI Views -> TanStack Hooks -> NestJS Controllers -> Services -> Drizzle DB Tables.
    Returns: Mermaid flowchart and structured node/edge statistics.
    """
    graph, diag = _ensure_graph(workspace_root, frontend_path, backend_path, schema_path)
    nodes = graph.get_nodes_by_domain(domain) if domain else []
    if not nodes:
        nodes = graph.get_all_nodes()

    mermaid = MermaidRenderer.render_flowchart(graph, nodes=nodes)
    res: Dict[str, Any] = {
        "domain": domain or "all",
        "mermaid": mermaid,
        "stats": graph.stats(),
        "node_sample": [n.name for n in nodes[:15]],
    }
    if diag.get("warnings"):
        res["warnings"] = diag["warnings"]
        res["scanned_paths"] = {
            "workspace_root": diag["workspace_root"],
            "frontend_root": diag["frontend_root"],
            "backend_root": diag["backend_root"],
            "schema_dirs": diag["schema_dirs_scanned"],
        }
    return res


@mcp.tool()
def blueprint_erd(
    domain: Optional[str] = None,
    workspace_root: Optional[str] = None,
    schema_path: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Generates an Entity-Relationship Diagram (ERD) with tables, columns, and foreign keys.
    """
    graph, diag = _ensure_graph(workspace_root, schema_path=schema_path)
    mermaid_erd = MermaidRenderer.render_erd(graph, domain=domain)
    tables = [
        n.name for n in graph.get_nodes_by_kind(NodeKind.STORAGE_ENTITY)
        if not domain or n.domain == domain
    ]
    res: Dict[str, Any] = {
        "domain": domain,
        "mermaid_erd": mermaid_erd,
        "tables_count": len(tables),
        "tables": tables,
    }
    if not tables:
        res["warning"] = "No database tables found. Ensure Drizzle schema files (*.ts) exist in scanned schema directories or pass schema_path."
        res["scanned_schema_dirs"] = diag.get("schema_dirs_scanned", [])
    return res


@mcp.tool()
def blueprint_trace(
    target: str,
    workspace_root: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Traces the ordered execution path starting from a component, hook, or endpoint down to DB tables.
    """
    graph, _ = _ensure_graph(workspace_root)
    paths = graph.trace_paths(target, target_kind=NodeKind.STORAGE_ENTITY)
    return {
        "target": target,
        "paths_found": len(paths),
        "paths": paths,
    }


@mcp.tool()
def blueprint_impact(
    node_id: str,
    direction: str = "upstream",
    workspace_root: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Calculates the architectural blast radius before refactoring a table, column, or service.
    """
    graph, _ = _ensure_graph(workspace_root)
    return graph.compute_blast_radius(node_id, direction=direction)


@mcp.tool()
def blueprint_audit(
    workspace_root: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Audits the architecture for broken routes, unindexed foreign keys, or layer leaks.
    """
    graph, diag = _ensure_graph(workspace_root)
    diagnostics = [
        {
            "code": d.code,
            "severity": d.severity,
            "message": d.message,
            "location": d.location.file_path if d.location else None,
        }
        for d in graph.get_diagnostics()
    ]
    res: Dict[str, Any] = {
        "diagnostics_count": len(diagnostics),
        "diagnostics": diagnostics,
        "stats": graph.stats(),
    }
    if diag.get("warnings"):
        res["scan_warnings"] = diag["warnings"]
    return res
