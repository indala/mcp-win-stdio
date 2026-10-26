"""
Universal Full-Stack Architecture AST Scanner
Part of mcp-win-stdio-arch.

Auto-discovers and maps full-stack architectures:
Frontend (Next.js / React / TanStack Query / SWR)
  -> Ingress Routes (NestJS Controllers, Next.js App Router API Routes)
  -> Domain Logic (NestJS Services, Domain Handlers)
  -> Storage Entities (Drizzle ORM pgTable/mysqlTable/sqliteTable).
"""

import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

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


class ArchitectureScanner:
    """
    Universal scanner for full-stack TypeScript / JavaScript architectures.
    Auto-discovers frontend, backend, and database schema layers.
    """

    def __init__(
        self,
        workspace_root: Optional[str] = None,
        frontend_root: Optional[str] = None,
        backend_root: Optional[str] = None,
        schema_dir: Optional[str] = None,
    ) -> None:
        self.workspace_root = Path(workspace_root or os.getcwd()).resolve()

        # 1. Resolve frontend root
        if frontend_root:
            self.frontend_root = Path(frontend_root).resolve()
        else:
            candidates = [
                self.workspace_root / "rfc_location_booking_frontend",
                self.workspace_root / "frontend",
                self.workspace_root / "client",
                self.workspace_root / "web",
                self.workspace_root / "apps" / "web",
                self.workspace_root / "apps" / "frontend",
            ]
            self.frontend_root = next((c for c in candidates if c.is_dir()), self.workspace_root)

        # 2. Resolve backend root
        if backend_root:
            self.backend_root = Path(backend_root).resolve()
        else:
            candidates = [
                self.workspace_root / "rfc_location_booking_backend",
                self.workspace_root / "backend",
                self.workspace_root / "server",
                self.workspace_root / "api",
                self.workspace_root / "apps" / "api",
                self.workspace_root / "apps" / "backend",
            ]
            self.backend_root = next((c for c in candidates if c.is_dir()), self.workspace_root)

        # 3. Explicit schema directory or auto-discover
        self.explicit_schema_dir = Path(schema_dir).resolve() if schema_dir else None

        # Diagnostic tracker for actionable feedback
        self.diagnostics: Dict[str, Any] = {
            "workspace_root": str(self.workspace_root),
            "frontend_root": str(self.frontend_root),
            "backend_root": str(self.backend_root),
            "schema_dirs_scanned": [],
            "tables_found": 0,
            "routes_found": 0,
            "services_found": 0,
            "client_hooks_found": 0,
            "warnings": [],
        }

    def _discover_schema_dirs(self) -> List[Path]:
        """Discover directories containing Drizzle ORM schemas."""
        if self.explicit_schema_dir and self.explicit_schema_dir.exists():
            return [self.explicit_schema_dir]

        found: List[Path] = []
        candidates = [
            self.backend_root / "src" / "database" / "schema",
            self.backend_root / "src" / "db" / "schema",
            self.backend_root / "src" / "db",
            self.backend_root / "src" / "database",
            self.backend_root / "drizzle",
            self.workspace_root / "drizzle",
            self.workspace_root / "src" / "db" / "schema",
            self.workspace_root / "src" / "db",
            self.workspace_root / "src" / "database" / "schema",
            self.workspace_root / "packages" / "db" / "src" / "schema",
            self.workspace_root / "packages" / "database" / "src" / "schema",
        ]

        # Check drizzle.config.ts / drizzle.config.js for custom schema entry
        for cfg_name in ("drizzle.config.ts", "drizzle.config.js", "drizzle.config.json"):
            for root_target in (self.backend_root, self.workspace_root):
                cfg_path = root_target / cfg_name
                if cfg_path.exists():
                    try:
                        content = cfg_path.read_text(encoding="utf-8")
                        m = re.search(r"schema\s*:\s*['\"]([^'\"]+)['\"]", content)
                        if m:
                            raw_schema = m.group(1)
                            resolved = (root_target / raw_schema).resolve()
                            if resolved.is_dir():
                                found.append(resolved)
                            elif resolved.parent.is_dir():
                                found.append(resolved.parent)
                    except Exception:
                        pass

        for c in candidates:
            if c.is_dir() and c not in found:
                found.append(c)

        return found

    def scan_all(self, graph: ArchitectureGraph, domain: Optional[str] = None) -> Dict[str, Any]:
        """Execute full architectural scan across schemas, backend, and frontend."""
        # 1. Scan Drizzle DB Schemas
        self.scan_drizzle_schemas(graph, domain)
        # 2. Scan Backend (NestJS Controllers, Next.js App Router API Routes)
        self.scan_backend_routes(graph, domain)
        # 3. Scan Frontend (Next.js TanStack Query / SWR / React Hooks)
        self.scan_frontend_clients(graph, domain)

        # Assemble diagnostics
        total_nodes = (
            self.diagnostics["tables_found"]
            + self.diagnostics["routes_found"]
            + self.diagnostics["services_found"]
            + self.diagnostics["client_hooks_found"]
        )
        if total_nodes == 0:
            self.diagnostics["warnings"].append(
                f"No architectural entities matched in '{self.workspace_root}'. "
                "Ensure project contains Drizzle schemas, NestJS controllers, or Next.js API routes, "
                "or configure explicit workspace_root / backend_root / schema_dir."
            )

        return self.diagnostics

    def scan_drizzle_schemas(self, graph: ArchitectureGraph, domain: Optional[str] = None) -> None:
        """Scan Drizzle schema definitions (pgTable, mysqlTable, sqliteTable, schema.table)."""
        schema_dirs = self._discover_schema_dirs()
        self.diagnostics["schema_dirs_scanned"] = [str(d) for d in schema_dirs]

        if not schema_dirs:
            return

        table_var_map: Dict[str, str] = {}  # varName -> tableNodeId

        for schema_dir in schema_dirs:
            schema_files = list(schema_dir.glob("*.ts")) + list(schema_dir.glob("*.js"))
            for sfile in schema_files:
                try:
                    content = sfile.read_text(encoding="utf-8")
                except Exception:
                    continue

                try:
                    rel_path = str(sfile.relative_to(self.workspace_root))
                except ValueError:
                    rel_path = str(sfile)

                # Match: export const <varName> = pgTable|mysqlTable|sqliteTable|schema.table('tableName', ...)
                table_matches = re.finditer(
                    r"export\s+const\s+([a-zA-Z0-9_]+)\s*=\s*(?:pgTable|mysqlTable|sqliteTable|[a-zA-Z0-9_]+\.table)\s*\(\s*['\"]([^'\"]+)['\"]",
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
                        domain=domain or "database",
                        metadata={"var_name": var_name, "orm": "drizzle"},
                    )
                    graph.add_node(table_node)
                    table_var_map[var_name] = node_id
                    self.diagnostics["tables_found"] += 1

                # Parse foreign keys: .references(() => otherTable.id)
                fk_matches = re.finditer(
                    r"export\s+const\s+([a-zA-Z0-9_]+)\s*=\s*(?:pgTable|mysqlTable|sqliteTable|[a-zA-Z0-9_]+\.table).*?\.references\(\s*\(\)\s*=>\s*([a-zA-Z0-9_]+)\.",
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

    def scan_backend_routes(self, graph: ArchitectureGraph, domain: Optional[str] = None) -> None:
        """Scan backend endpoints from NestJS controllers and Next.js App Router route handlers."""
        # 1. NestJS Controllers
        controller_files: List[Path] = []
        for root_target in (self.backend_root, self.workspace_root):
            if root_target.exists():
                controller_files.extend(root_target.rglob("*controller.ts"))
                controller_files.extend(root_target.rglob("*controller.js"))

        seen_ctrl_files: Set[Path] = set()
        for ctrl_file in controller_files:
            resolved_ctrl = ctrl_file.resolve()
            if resolved_ctrl in seen_ctrl_files:
                continue
            seen_ctrl_files.add(resolved_ctrl)

            try:
                content = ctrl_file.read_text(encoding="utf-8")
            except Exception:
                continue

            try:
                rel_path = str(ctrl_file.relative_to(self.workspace_root))
            except ValueError:
                rel_path = str(ctrl_file)

            # Match @Controller('prefix')
            prefix_match = re.search(r"@Controller\(\s*['\"]([^'\"]*)['\"]\s*\)", content)
            base_prefix = prefix_match.group(1) if prefix_match else ""
            if not base_prefix.startswith("/") and base_prefix:
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
                norm_route_id = NodeIdentifier.for_ingress_route(http_method, full_path)

                route_node = ArchitectureNode(
                    id=norm_route_id,
                    kind=NodeKind.INGRESS_ROUTE,
                    name=f"{http_method} {full_path}",
                    file_path=rel_path,
                    domain=domain or "backend",
                    metadata={"handler": fn_name, "method": http_method, "path": full_path, "framework": "nestjs"},
                )
                graph.add_node(route_node)
                self.diagnostics["routes_found"] += 1

                # Link to Service in same module if called
                svc_call_match = re.search(r"this\.([a-zA-Z0-9_]+Service)\.([a-zA-Z0-9_]+)\(", content)
                if svc_call_match:
                    svc_class = svc_call_match.group(1)
                    svc_method = svc_call_match.group(2)
                    svc_id = NodeIdentifier.for_domain_logic("backend", rel_path, svc_class, svc_method)
                    if not graph.has_node(svc_id):
                        graph.add_node(
                            ArchitectureNode(
                                id=svc_id,
                                kind=NodeKind.DOMAIN_LOGIC,
                                name=f"{svc_class}.{svc_method}",
                                file_path=rel_path,
                                domain=domain or "backend",
                            )
                        )
                        self.diagnostics["services_found"] += 1

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

        # 2. Next.js App Router API Routes (app/**/route.ts)
        app_dirs = [
            self.backend_root / "src" / "app",
            self.backend_root / "app",
            self.frontend_root / "src" / "app",
            self.frontend_root / "app",
            self.workspace_root / "src" / "app",
            self.workspace_root / "app",
        ]
        seen_route_files: Set[Path] = set()
        for app_dir in app_dirs:
            if not app_dir.is_dir():
                continue
            for rfile in app_dir.rglob("route.ts"):
                resolved_rf = rfile.resolve()
                if resolved_rf in seen_route_files:
                    continue
                seen_route_files.add(resolved_rf)

                try:
                    content = rfile.read_text(encoding="utf-8")
                except Exception:
                    continue

                try:
                    rel_path = str(rfile.relative_to(self.workspace_root))
                except ValueError:
                    rel_path = str(rfile)

                # Route path is the directory path relative to app/
                route_subpath = rfile.parent.relative_to(app_dir).as_posix()
                api_path = f"/{route_subpath}" if not route_subpath.startswith("/") else route_subpath

                # Match export async function GET/POST/PUT/DELETE/PATCH
                handlers = re.findall(
                    r"export\s+async\s+function\s+(GET|POST|PUT|DELETE|PATCH)\s*\(",
                    content,
                )
                for http_method in handlers:
                    norm_route_id = NodeIdentifier.for_ingress_route(http_method, api_path)
                    route_node = ArchitectureNode(
                        id=norm_route_id,
                        kind=NodeKind.INGRESS_ROUTE,
                        name=f"{http_method} {api_path}",
                        file_path=rel_path,
                        domain=domain or "api",
                        metadata={"path": api_path, "method": http_method, "framework": "nextjs-app-router"},
                    )
                    graph.add_node(route_node)
                    self.diagnostics["routes_found"] += 1

    def scan_frontend_clients(self, graph: ArchitectureGraph, domain: Optional[str] = None) -> None:
        """Scan frontend React Query / SWR / API hooks and map them to backend routes."""
        hook_dirs: List[Path] = []
        for root_target in (self.frontend_root, self.workspace_root):
            for sub in ("features", "src/features", "hooks", "src/hooks", "components", "src/components"):
                target = root_target / sub
                if target.is_dir() and target not in hook_dirs:
                    hook_dirs.append(target)

        if not hook_dirs:
            return

        seen_hook_files: Set[Path] = set()
        for hdir in hook_dirs:
            for hook_file in hdir.rglob("*.ts*"):
                resolved_hf = hook_file.resolve()
                if resolved_hf in seen_hook_files:
                    continue
                seen_hook_files.add(resolved_hf)

                try:
                    content = hook_file.read_text(encoding="utf-8")
                except Exception:
                    continue

                try:
                    rel_path = str(hook_file.relative_to(self.workspace_root))
                except ValueError:
                    rel_path = str(hook_file)

                # Match hooks: export function useEstimationQuery or const useX =
                hook_match = re.search(r"export\s+(?:function|const)\s+(use[a-zA-Z0-9_]+)", content)
                if not hook_match:
                    continue

                hook_name = hook_match.group(1)
                hook_id = NodeIdentifier.for_client_transport("frontend", rel_path, hook_name)

                # Look for endpoint pattern: e.g. /api/v1/prop/estimations or axios.get('/api/...')
                endpoint_match = re.search(r"['\"](\/api\/[a-zA-Z0-9_\-\/]+(?:\$\{[^}]+\})?)['\"]", content)
                endpoint_url = endpoint_match.group(1) if endpoint_match else None

                client_node = ArchitectureNode(
                    id=hook_id,
                    kind=NodeKind.CLIENT_TRANSPORT,
                    name=hook_name,
                    file_path=rel_path,
                    domain=domain or "frontend",
                    metadata={"endpoint": endpoint_url},
                )
                graph.add_node(client_node)
                self.diagnostics["client_hooks_found"] += 1

                # Match with backend route if endpoint matches
                if endpoint_url:
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


# Backwards-compatibility alias
ShowreelScanner = ArchitectureScanner
