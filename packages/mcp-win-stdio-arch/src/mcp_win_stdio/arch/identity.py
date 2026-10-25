"""
Deterministic URN & Node ID Generators
"""

import re


def normalize_path(path_str: str) -> str:
    """Normalize file paths to clean POSIX format."""
    return path_str.replace("\\", "/").lstrip("/")


def normalize_route_path(raw_path: str) -> str:
    """
    Normalize route paths across frameworks:
    Converts :id, ${id}, [id] to {param}
    """
    p = raw_path.strip().split("?")[0].split("#")[0]
    p = re.sub(r"\$\{[^}]+\}", "{param}", p)
    p = re.sub(r":([a-zA-Z0-9_]+)", "{param}", p)
    p = re.sub(r"\[([a-zA-Z0-9_]+)\]", "{param}", p)
    if not p.startswith("/"):
        p = "/" + p
    if len(p) > 1 and p.endswith("/"):
        p = p[:-1]
    return p.lower()


class NodeIdentifier:
    @staticmethod
    def for_surface(workspace: str, file_path: str, component_name: str) -> str:
        return f"surface:{workspace}:{normalize_path(file_path)}#{component_name}"

    @staticmethod
    def for_client_transport(workspace: str, file_path: str, symbol: str) -> str:
        return f"client:{workspace}:{normalize_path(file_path)}#{symbol}"

    @staticmethod
    def for_ingress_route(method: str, normalized_path: str) -> str:
        return f"route:{method.upper()}:{normalize_route_path(normalized_path)}"

    @staticmethod
    def for_domain_logic(workspace: str, file_path: str, class_name: str, method: str = "") -> str:
        symbol = f"{class_name}.{method}" if method else class_name
        return f"logic:{workspace}:{normalize_path(file_path)}#{symbol}"

    @staticmethod
    def for_storage_entity(schema: str, table_name: str) -> str:
        return f"storage:{schema.lower()}:{table_name.lower()}"

    @staticmethod
    def for_field(owner_id: str, field_name: str) -> str:
        return f"field:{owner_id}#{field_name}"

    @staticmethod
    def for_contract(workspace: str, file_path: str, type_name: str) -> str:
        return f"contract:{workspace}:{normalize_path(file_path)}#{type_name}"

    @staticmethod
    def for_edge(source: str, edge_type: str, target: str) -> str:
        return f"edge:{source}--{edge_type}-->{target}"
