"""
Mermaid Flowchart and ERD Renderers
"""

import re
from typing import List, Optional

from .graph import ArchitectureGraph
from .models import ArchitectureEdge, ArchitectureNode, NodeKind


def sanitize(name: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_]", "_", name)


class MermaidRenderer:
    @staticmethod
    def render_flowchart(
        graph: ArchitectureGraph,
        nodes: Optional[List[ArchitectureNode]] = None,
        edges: Optional[List[ArchitectureEdge]] = None,
    ) -> str:
        active_nodes = nodes or graph.get_all_nodes()
        active_edges = edges or graph.get_all_edges()

        lines = ["flowchart TD"]

        groups: dict[str, list[ArchitectureNode]] = {}
        for node in active_nodes:
            kind_str = node.kind.value if isinstance(node.kind, NodeKind) else str(node.kind)
            groups.setdefault(kind_str, []).append(node)

        order = [
            "Surface",
            "ClientTransport",
            "IngressRoute",
            "DomainLogic",
            "StorageEntity",
            "Contract",
        ]

        for kind in order:
            items = groups.get(kind, [])
            if not items:
                continue
            lines.append(f'  subgraph {kind}_Layer ["{kind} Layer"]')
            for n in items:
                sid = sanitize(n.id)
                lines.append(f'    {sid}["{n.name}\\n({kind})"]')
            lines.append("  end")

        for e in active_edges:
            sid = sanitize(e.source)
            tid = sanitize(e.target)
            etype = e.type.value if hasattr(e.type, "value") else str(e.type)
            conf = e.confidence.value if hasattr(e.confidence, "value") else str(e.confidence)
            lines.append(f'  {sid} -->|"{etype} ({conf})"| {tid}')

        return "\n".join(lines)

    @staticmethod
    def render_erd(graph: ArchitectureGraph, domain: Optional[str] = None) -> str:
        tables = (
            graph.get_nodes_by_domain(domain)
            if domain
            else graph.get_nodes_by_kind(NodeKind.STORAGE_ENTITY)
        )
        tables = [t for t in tables if t.kind == NodeKind.STORAGE_ENTITY]

        lines = ["erDiagram"]
        for t in tables:
            lines.append(f"  {sanitize(t.name)} {{")
            # find fields
            fields = [
                f for f in graph.get_nodes_by_kind(NodeKind.FIELD)
                if f.metadata.get("owner_id") == t.id
            ]
            if not fields:
                lines.append("    string id PK")
            else:
                for f in fields:
                    pk = "PK" if f.metadata.get("is_pk") else ""
                    fk = "FK" if f.metadata.get("is_fk") else ""
                    tag = ",".join(filter(None, [pk, fk]))
                    dtype = f.metadata.get("data_type", "string")
                    lines.append(f"    {dtype} {f.name} {tag}")
            lines.append("  }")

        for e in graph.get_all_edges():
            if e.type == "REFERENCES_FK" or getattr(e.type, "value", None) == "REFERENCES_FK":
                s = graph.get_node(e.source)
                t = graph.get_node(e.target)
                if s and t:
                    lines.append(f'  {sanitize(s.name)} }}o--|| {sanitize(t.name)} : "references"')

        return "\n".join(lines)
