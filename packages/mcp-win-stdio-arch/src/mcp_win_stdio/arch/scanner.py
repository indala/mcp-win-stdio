"""
Real-world AST Scanner for Showreel (Drizzle ORM + NestJS Backend + Next.js Frontend)
"""

import os
import re
from pathlib import Path
from typing import Dict, List, Optional

from .graph import ArchitectureGraph
from .identity import NodeIdentifier, normalize_route_path
from .models import (
    ArchitectureEdge,
    ArchitectureNode,
    Confidence,
    EdgeEvidence,
    EdgeType,
    EvidenceLocation,
    NodeKind,
    Resolution,
)


class ShowreelScanner:
    """
    Scans full-stack Showreel architecture:
    Frontend (Next.js/TanStack) -> Backend (NestJS) -> Schema (Drizzle).
    """

    def __init__(self, workspace_root: str = r"Z:\projects\showreel") -> None:
        self.workspace_root = Path(workspace_root)
        self.frontend_root = self.workspace_root / "rfc_location_booking_frontend"
        self.backend_root = self.workspace_root / "rfc_location_booking_backend"

    def scan_all(self, graph: ArchitectureGraph, domain: Optional[str] = "prop-management") -> None:
        # 1. Scan Drizzle DB Schemas
        self.scan_drizzle_schemas(graph, domain)
        # 2. Scan NestJS Controllers & Services
        self.scan_nestjs_backend(graph, domain)
        # 3. Scan Next.js Features & React Query Hooks
        self.scan_nextjs_frontend(graph, domain)

    def scan_drizzle_schemas(self, graph: ArchitectureGraph, domain: Optional[str] = None) -> None:
        schema_dir = self.backend_root / "src" / "database" / "schema"
        if not schema_dir.exists():
            return

        schema_files = list(schema_dir.glob("*.ts"))
        table_var_map: Dict[str, str] = {}  # varName -> tableNodeId

        for sfile in schema_files:
            try:
                content = sfile.read_text(encoding="utf-8")
            except Exception:
                continue

            rel_path = str(sfile.relative_to(self.workspace_root))

            # Match: export const <varName> = pgTable('tableName', { ... })
            # or export const <varName> = publicSchema.table('tableName', { ... })
            table_matches = re.finditer(
                r"export\s+const\s+([a-zA-Z0-9_]+)\s*=\s*(?:pgTable|[a-zA-Z0-9_]+\.table)\s*\(\s*['\"]([^'\"]+)['\"]",
                content,
            )

            for m in table_matches:
                var_name = m.group(1)
                table_name = m.group(2)
                node_id = NodeIdentifier.for_storage_entity("public", table_name)

                table_node = ArchitectureNode(
                    id=node_id,
                    kind=NodeKind.STORAGE_ENTITY,
                    name=table_name,
                    file_path=rel_path,
                    domain=domain or "prop-management",
                    metadata={"var_name": var_name, "orm": "drizzle"},
                )
                graph.add_node(table_node)
                table_var_map[var_name] = node_id

            # Parse foreign keys: .references(() => otherTable.id)
            fk_matches = re.finditer(
                r"export\s+const\s+([a-zA-Z0-9_]+)\s*=\s*(?:pgTable|[a-zA-Z0-9_]+\.table).*?\.references\(\s*\(\)\s*=>\s*([a-zA-Z0-9_]+)\.",
                content,
                re.DOTALL,
            )
            for fk in fk_matches:
                src_var = fk.group(1)
                tgt_var = fk.group(2)
                if src_var in table_var_map and tgt_var in table_var_map and src_var != tgt_var:
                    src_id = table_var_map[src_var]
                    tgt_id = table_var_map[tgt_var]
                    edge_id = NodeIdentifier.for_edge(src_id, "REFERENCES_FK", tgt_id)
                    if not graph.get_edge(edge_id):
                        graph.add_edge(
                            ArchitectureEdge(
                                id=edge_id,
                                source=src_id,
                                target=tgt_id,
                                type=EdgeType.REFERENCES_FK,
                                confidence=Confidence.HIGH,
                                resolution=Resolution.STATIC,
                                evidence=EdgeEvidence(
                                    rule_id="DRIZZLE_FK_REFERENCES",
                                    locations=[EvidenceLocation(file_path=rel_path)],
                                    explanation=f"FK: {src_var} -> {tgt_var}",
                                ),
                            )
                        )

    def scan_nestjs_backend(self, graph: ArchitectureGraph, domain: Optional[str] = None) -> None:
        modules_dir = self.backend_root / "src" / "modules"
        if not modules_dir.exists():
            return

        for ctrl_file in modules_dir.rglob("*controller.ts"):
            try:
                content = ctrl_file.read_text(encoding="utf-8")
            except Exception:
                continue

            rel_path = str(ctrl_file.relative_to(self.workspace_root))

            # Match @Controller('prefix')
            prefix_match = re.search(r"@Controller\(\s*['\"]([^'\"]*)['\"]\s*\)", content)
            base_prefix = prefix_match.group(1) if prefix_match else ""
            if not base_prefix.startswith("/"):
                base_prefix = "/" + base_prefix

            # Match routes: @Get(':id'), @Post(), etc.
            method_matches = re.finditer(
                r"@(Get|Post|Put|Patch|Delete)\(\s*(?:['\"]([^'\"]*)['\"])?\s*\)\s*(?:async\s+)?([a-zA-Z0-9_]+)\s*\(",
                content,
            )

            for mm in method_matches:
                http_method = mm.group(1).upper()
                sub_path = mm.group(2) or ""
                fn_name = mm.group(3)

                full_path = f"{base_prefix}/{sub_path}".replace("//", "/")
                # Showreel uses standard api prefix (e.g. /api/v1/prop/...)
                norm_route_id = NodeIdentifier.for_ingress_route(http_method, full_path)

                route_node = ArchitectureNode(
                    id=norm_route_id,
                    kind=NodeKind.INGRESS_ROUTE,
                    name=f"{http_method} {full_path}",
                    file_path=rel_path,
                    domain=domain or "prop-management",
                    metadata={"handler": fn_name, "method": http_method, "path": full_path},
                )
                graph.add_node(route_node)

                # Link to Service in same module if called
                svc_call_match = re.search(r"this\.([a-zA-Z0-9_]+Service)\.([a-zA-Z0-9_]+)\(", content)
                if svc_call_match:
                    svc_class = svc_call_match.group(1)
                    svc_method = svc_call_match.group(2)
                    svc_id = NodeIdentifier.for_domain_logic("showreel", rel_path, svc_class, svc_method)
                    if not graph.has_node(svc_id):
                        graph.add_node(
                            ArchitectureNode(
                                id=svc_id,
                                kind=NodeKind.DOMAIN_LOGIC,
                                name=f"{svc_class}.{svc_method}",
                                file_path=rel_path,
                                domain=domain or "prop-management",
                            )
                        )
                    edge_id = NodeIdentifier.for_edge(norm_route_id, "CALLS", svc_id)
                    if not graph.get_edge(edge_id):
                        graph.add_edge(
                            ArchitectureEdge(
                                id=edge_id,
                                source=norm_route_id,
                                target=svc_id,
                                type=EdgeType.CALLS,
                                confidence=Confidence.HIGH,
                                resolution=Resolution.STATIC,
                                evidence=EdgeEvidence(
                                    rule_id="NESTJS_CONTROLLER_SERVICE_CALL",
                                    locations=[EvidenceLocation(file_path=rel_path, symbol=fn_name)],
                                ),
                            )
                        )

    def scan_nextjs_frontend(self, graph: ArchitectureGraph, domain: Optional[str] = None) -> None:
        features_dir = self.frontend_root / "features"
        if not features_dir.exists():
            return

        for hook_file in features_dir.rglob("*.ts*"):
            try:
                content = hook_file.read_text(encoding="utf-8")
            except Exception:
                continue

            rel_path = str(hook_file.relative_to(self.workspace_root))

            # Match TanStack Query hooks: export function useEstimationQuery or const useX =
            hook_match = re.search(r"export\s+(?:function|const)\s+(use[a-zA-Z0-9_]+)", content)
            if not hook_match:
                continue

            hook_name = hook_match.group(1)
            hook_id = NodeIdentifier.for_client_transport("showreel", rel_path, hook_name)

            # Look for endpoint pattern: e.g. /api/v1/prop/estimations or axios.get('/api/...')
            endpoint_match = re.search(r"['\"](\/api\/[a-zA-Z0-9_\-\/]+(?:\$\{[^}]+\})?)['\"]", content)
            endpoint_url = endpoint_match.group(1) if endpoint_match else None

            client_node = ArchitectureNode(
                id=hook_id,
                kind=NodeKind.CLIENT_TRANSPORT,
                name=hook_name,
                file_path=rel_path,
                domain=domain or "prop-management",
                metadata={"endpoint": endpoint_url},
            )
            graph.add_node(client_node)

            # Match with backend route if endpoint matches
            if endpoint_url:
                norm_route_id = NodeIdentifier.for_ingress_route("GET", endpoint_url)
                # Check if route exists or starts with pattern
                for rnode in graph.get_nodes_by_kind(NodeKind.INGRESS_ROUTE):
                    r_path = rnode.metadata.get("path", "")
                    if normalize_route_path(r_path) == normalize_route_path(endpoint_url) or (
                        r_path and r_path in endpoint_url
                    ):
                        edge_id = NodeIdentifier.for_edge(hook_id, "ROUTES_TO", rnode.id)
                        if not graph.get_edge(edge_id):
                            graph.add_edge(
                                ArchitectureEdge(
                                    id=edge_id,
                                    source=hook_id,
                                    target=rnode.id,
                                    type=EdgeType.ROUTES_TO,
                                    confidence=Confidence.HIGH,
                                    resolution=Resolution.INFERRED,
                                    evidence=EdgeEvidence(
                                        rule_id="HTTP_CLIENT_ROUTE_MATCH",
                                        locations=[EvidenceLocation(file_path=rel_path, symbol=hook_name)],
                                        explanation=f"Matched {endpoint_url} to backend {r_path}",
                                    ),
                                )
                            )
                        break
