"""
Core Canonical Schema: Universal Architectural Primitives (UIR)
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class NodeKind(str, Enum):
    SURFACE = "Surface"                  # UI Page, Component, Screen, Template
    CLIENT_TRANSPORT = "ClientTransport" # Hook, API Client method, RPC client
    INGRESS_ROUTE = "IngressRoute"       # HTTP Route, Controller method, RPC handler
    DOMAIN_LOGIC = "DomainLogic"         # Service, Use Case, Business domain function
    STORAGE_ENTITY = "StorageEntity"     # ORM Model, SQL Table, View, Collection
    FIELD = "Field"                      # Database Column or DTO Property
    CONTRACT = "Contract"                # DTO, Zod Schema, OpenAPI Request/Response
    EXTERNAL_SYSTEM = "ExternalSystem"   # Third-party API, Message Broker
    CONFIGURATION = "Configuration"      # Env var, Route prefix, Feature flag
    JOB = "Job"                          # Cron job, Queue consumer, Worker


class EdgeType(str, Enum):
    DECLARES = "DECLARES"                # e.g. Controller declares method, Schema declares Table
    IMPORTS = "IMPORTS"                  # Module imports another module
    CALLS = "CALLS"                      # Method or function invocation
    USES_HOOK = "USES_HOOK"              # Surface uses query/mutation hook
    ROUTES_TO = "ROUTES_TO"              # Client request matches an ingress route
    INJECTS = "INJECTS"                  # Dependency injection
    READS = "READS"                      # Logic queries a table or field
    WRITES = "WRITES"                    # Logic mutates a table or field
    SERIALIZES_AS = "SERIALIZES_AS"      # Entity shapes into DTO
    REFERENCES_FK = "REFERENCES_FK"      # Foreign-key relationship
    PUBLISHES = "PUBLISHES"              # Event-driven message publishing
    CONSUMES = "CONSUMES"                # Event-driven message consumption
    CONFIGURED_BY = "CONFIGURED_BY"      # Component depends on configuration


class Confidence(str, Enum):
    HIGH = "high"       # Statically resolved symbol call, explicit foreign key, exact route match
    MEDIUM = "medium"   # Inferred through convention or partial types
    LOW = "low"         # Heuristic or ambiguous string matching


class Resolution(str, Enum):
    STATIC = "static"   # AST symbol checker or static code analysis
    INFERRED = "inferred" # Normalized route or naming pattern match
    RUNTIME = "runtime" # Database introspection or live trace
    MANUAL = "manual"   # User/developer annotated


@dataclass
class EvidenceLocation:
    file_path: str
    start_line: Optional[int] = None
    end_line: Optional[int] = None
    symbol: Optional[str] = None


@dataclass
class EdgeEvidence:
    rule_id: str
    locations: List[EvidenceLocation] = field(default_factory=list)
    explanation: Optional[str] = None
    snippet: Optional[str] = None


@dataclass
class ArchitectureNode:
    id: str
    kind: NodeKind
    name: str
    file_path: Optional[str] = None
    domain: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ArchitectureEdge:
    id: str
    source: str
    target: str
    type: EdgeType
    evidence: EdgeEvidence
    confidence: Confidence = Confidence.HIGH
    resolution: Resolution = Resolution.STATIC
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ScanDiagnostic:
    code: str
    severity: str  # "info" | "warning" | "error"
    message: str
    location: Optional[EvidenceLocation] = None
    attempted_resolution: Optional[Dict[str, Any]] = None
