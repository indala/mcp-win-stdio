"""
Core Directed Multigraph Engine using NetworkX
"""

from typing import Any, Dict, List, Optional, Set

import networkx as nx

from .models import (
    ArchitectureEdge,
    ArchitectureNode,
    EdgeType,
    NodeKind,
    ScanDiagnostic,
)


class ArchitectureGraph:
    def __init__(self) -> None:
        self.g = nx.MultiDiGraph()
        self.nodes_map: Dict[str, ArchitectureNode] = {}
        self.edges_map: Dict[str, ArchitectureEdge] = {}
        self.diagnostics: List[ScanDiagnostic] = []

    def clear(self) -> None:
        self.g.clear()
        self.nodes_map.clear()
        self.edges_map.clear()
        self.diagnostics.clear()

    # --- Node Operations ---

    def add_node(self, node: ArchitectureNode) -> None:
        self.nodes_map[node.id] = node
        self.g.add_node(
            node.id,
            kind=node.kind.value if isinstance(node.kind, NodeKind) else str(node.kind),
            name=node.name,
            domain=node.domain,
            file_path=node.file_path,
        )

    def get_node(self, node_id: str) -> Optional[ArchitectureNode]:
        return self.nodes_map.get(node_id)

    def has_node(self, node_id: str) -> bool:
        return node_id in self.nodes_map

    def get_all_nodes(self) -> List[ArchitectureNode]:
        return list(self.nodes_map.values())

    def get_nodes_by_kind(self, kind: NodeKind) -> List[ArchitectureNode]:
        return [n for n in self.nodes_map.values() if n.kind == kind]

    def get_nodes_by_domain(self, domain: str) -> List[ArchitectureNode]:
        return [n for n in self.nodes_map.values() if n.domain == domain]

    # --- Edge Operations ---

    def add_edge(self, edge: ArchitectureEdge) -> None:
        if edge.source not in self.nodes_map or edge.target not in self.nodes_map:
            raise ValueError(
                f"Cannot add edge {edge.id}: source ({edge.source}) or target ({edge.target}) does not exist"
            )

        self.edges_map[edge.id] = edge
        self.g.add_edge(
            edge.source,
            edge.target,
            key=edge.id,
            type=edge.type.value if isinstance(edge.type, EdgeType) else str(edge.type),
            confidence=edge.confidence.value,
            resolution=edge.resolution.value,
        )

    def get_edge(self, edge_id: str) -> Optional[ArchitectureEdge]:
        return self.edges_map.get(edge_id)

    def get_all_edges(self) -> List[ArchitectureEdge]:
        return list(self.edges_map.values())

    def get_outgoing_edges(self, node_id: str) -> List[ArchitectureEdge]:
        if not self.g.has_node(node_id):
            return []
        edges = []
        for _, _, key in self.g.out_edges(node_id, keys=True):
            if key in self.edges_map:
                edges.append(self.edges_map[key])
        return edges

    def get_incoming_edges(self, node_id: str) -> List[ArchitectureEdge]:
        if not self.g.has_node(node_id):
            return []
        edges = []
        for _, _, key in self.g.in_edges(node_id, keys=True):
            if key in self.edges_map:
                edges.append(self.edges_map[key])
        return edges

    # --- Diagnostics ---

    def add_diagnostic(self, diagnostic: ScanDiagnostic) -> None:
        self.diagnostics.append(diagnostic)

    def get_diagnostics(self) -> List[ScanDiagnostic]:
        return list(self.diagnostics)

    # --- Traversals & Blast Radius ---

    def trace_paths(
        self,
        from_node_id: str,
        target_kind: Optional[NodeKind] = None,
        max_depth: int = 10,
        max_paths: int = 20,
    ) -> List[List[str]]:
        """
        Traces paths from from_node_id to target_kind with cycle protection.
        Returns list of path node ID lists.
        """
        if not self.has_node(from_node_id):
            return []

        results: List[List[str]] = []

        def dfs(current_id: str, path: List[str], depth: int, visited: Set[str]):
            if len(results) >= max_paths or depth >= max_depth:
                return

            curr_node = self.nodes_map.get(current_id)
            if target_kind and curr_node and curr_node.kind == target_kind and len(path) > 1:
                results.append(list(path))
                return

            extended = False
            for edge in self.get_outgoing_edges(current_id):
                nxt = edge.target
                if nxt in visited:
                    continue

                extended = True
                visited.add(nxt)
                path.append(nxt)

                dfs(nxt, path, depth + 1, visited)

                path.pop()
                visited.remove(nxt)

            if not extended and not target_kind and len(path) > 1:
                results.append(list(path))

        dfs(from_node_id, [from_node_id], 0, {from_node_id})
        return results

    def compute_blast_radius(
        self,
        node_id: str,
        direction: str = "both",
        max_depth: int = 8,
    ) -> Dict[str, Any]:
        """
        Calculates upstream/downstream blast radius for refactoring.
        """
        if not self.has_node(node_id):
            return {"root_node_id": node_id, "total_affected": 0, "impacted": []}

        impacted: Dict[str, Dict[str, Any]] = {}

        queue: List[tuple[str, int, str]] = []
        if direction in ("downstream", "both"):
            queue.append((node_id, 0, "downstream"))
        if direction in ("upstream", "both"):
            queue.append((node_id, 0, "upstream"))

        visited: Set[str] = set()

        while queue:
            curr_id, depth, d = queue.pop(0)
            vkey = f"{curr_id}:{d}"
            if vkey in visited:
                continue
            visited.add(vkey)

            if depth > 0 and curr_id not in impacted:
                impacted[curr_id] = {
                    "node_id": curr_id,
                    "depth": depth,
                    "direction": d,
                    "kind": self.nodes_map[curr_id].kind.value,
                    "name": self.nodes_map[curr_id].name,
                }

            if depth >= max_depth:
                continue

            if d == "downstream":
                for edge in self.get_outgoing_edges(curr_id):
                    queue.append((edge.target, depth + 1, "downstream"))
            else:
                for edge in self.get_incoming_edges(curr_id):
                    queue.append((edge.source, depth + 1, "upstream"))

        return {
            "root_node_id": node_id,
            "total_affected": len(impacted),
            "impacted": list(impacted.values()),
        }

    def stats(self) -> Dict[str, int]:
        return {
            "node_count": len(self.nodes_map),
            "edge_count": len(self.edges_map),
            "diagnostic_count": len(self.diagnostics),
        }
