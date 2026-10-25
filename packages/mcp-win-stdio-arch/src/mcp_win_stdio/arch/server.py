"""
Server definition for mcp-win-stdio-arch (FastMCP)
Part of mcp-win-stdio.
"""

import json
import os
from typing import Any, Dict, Optional

try:
    from mcp.server.mcpserver import MCPServer as FastMCP
except (ImportError, ModuleNotFoundError):
    from mcp.server.fastmcp import FastMCP  # type: ignore[import-not-found]

from .graph import ArchitectureGraph
from .models import NodeKind
from .renderers import MermaidRenderer
from .scanner import ShowreelScanner

mcp = FastMCP("arch-mcp")

# In-memory graph cache
_GRAPH = ArchitectureGraph()
_SCANNED_ROOT: Optional[str] = None


def _ensure_graph(workspace_root: Optional[str] = None) -> ArchitectureGraph:
    global _GRAPH, _SCANNED_ROOT
    root = os.path.abspath(workspace_root) if workspace_root else os.getcwd()
    if _SCANNED_ROOT != root or _GRAPH.stats()["node_count"] == 0:
        _GRAPH.clear()
        scanner = ShowreelScanner(root)
        scanner.scan_all(_GRAPH)
        _SCANNED_ROOT = root
    return _GRAPH


@mcp.tool()
def blueprint_feature(
    domain: Optional[str] = None,
    workspace_root: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Generates a full-stack vertical architecture blueprint for a domain feature.
    Connects: UI Views -> TanStack Hooks -> NestJS Controllers -> Services -> Drizzle DB Tables.
    Returns: Mermaid flowchart and structured node/edge statistics.
    """
    graph = _ensure_graph(workspace_root)
    nodes = graph.get_nodes_by_domain(domain) if domain else []
    if not nodes:
        nodes = graph.get_all_nodes()

    mermaid = MermaidRenderer.render_flowchart(graph, nodes=nodes)
    return {
        "domain": domain or "all",
        "mermaid": mermaid,
        "stats": graph.stats(),
        "node_sample": [n.name for n in nodes[:15]],
    }


@mcp.tool()
def blueprint_erd(
    domain: Optional[str] = None,
    workspace_root: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Generates an Entity-Relationship Diagram (ERD) with tables, columns, and foreign keys.
    """
    graph = _ensure_graph(workspace_root)
    mermaid_erd = MermaidRenderer.render_erd(graph, domain=domain)
    tables = [
        n.name for n in graph.get_nodes_by_kind(NodeKind.STORAGE_ENTITY)
        if not domain or n.domain == domain
    ]
    return {
        "domain": domain,
        "mermaid_erd": mermaid_erd,
        "tables_count": len(tables),
        "tables": tables,
    }


@mcp.tool()
def blueprint_trace(
    target: str,
    workspace_root: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Traces the ordered execution path starting from a component, hook, or endpoint down to DB tables.
    """
    graph = _ensure_graph(workspace_root)
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
    graph = _ensure_graph(workspace_root)
    return graph.compute_blast_radius(node_id, direction=direction)


@mcp.tool()
def blueprint_audit(
    workspace_root: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Audits the architecture for broken routes, unindexed foreign keys, or layer leaks.
    """
    graph = _ensure_graph(workspace_root)
    diagnostics = [
        {
            "code": d.code,
            "severity": d.severity,
            "message": d.message,
            "location": d.location.file_path if d.location else None,
        }
        for d in graph.get_diagnostics()
    ]
    return {
        "diagnostics_count": len(diagnostics),
        "diagnostics": diagnostics,
        "stats": graph.stats(),
    }
