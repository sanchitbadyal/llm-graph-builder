"""Ontology artifact and manifest services.

Phase 1 deliberately provides metadata and artifact discovery only. It does
not change extraction, Neo4j persistence, or validation behavior.
"""

from .manifest import OntologyArtifact, OntologyManifest, load_manifest
from .imports import ImportResolutionError, LocalImportResolver, ResolvedImportClosure
from .repository import OntologyRepository
from .semantic import OntologyClass, OntologyProperty, SemanticIndex, SemanticResolver
from .context import OntologyContext, OntologyContextBuilder
from .adapter import OntologyExtractionAdapter, OntologyExtractionProfile, default_adapter, default_profile
from .provenance import EvidenceProvenance, chunk_hash
from .envelope import ExtractionAssertion, OntologyExtractionEnvelope
from .graph_document import filter_graph_documents_by_envelope, graph_documents_to_envelope
from .validation import (
    NodeValidationReport,
    SemanticValidationReport,
    validate_envelope,
    validate_envelope_yaml,
    validate_graph_document_nodes,
    validate_graph_document_nodes_yaml,
)
from .shacl import ShaclValidationReport, assertion_graph, validate_envelope_shacl
from .entity_resolution import (EntityCandidate, EntityResolution, EntityResolver, ReconciliationGroup,
                                normalize_mention, project_entity_metadata, project_relationship_metadata,
                                resolve_envelope, resolver_from_neo4j)
from .evidence import verify_envelope_evidence
from .query import OntologyQueryPlan, OntologyQueryPlanner, ontology_answering_context
from .authority import (AuthorityDrift, AuthorityPolicy, CompatibilityReport, IriMigration,
                        MigrationPlan, build_migration_plan, check_compatibility, compare_labels)
from .profile import NoOpProfileValidator, ProfileValidator, validate_with_optional_profile
from .extraction_log import write_extraction_log
from .reasoner import load_reasoning_closure, reason_over_ontology

__all__ = [
    "ImportResolutionError",
    "LocalImportResolver",
    "OntologyArtifact",
    "OntologyManifest",
    "OntologyRepository",
    "OntologyClass",
    "OntologyProperty",
    "OntologyContext",
    "OntologyContextBuilder",
    "OntologyExtractionAdapter",
    "OntologyExtractionProfile",
    "ResolvedImportClosure",
    "SemanticIndex",
    "SemanticResolver",
    "default_adapter",
    "default_profile",
    "load_manifest",
    "EvidenceProvenance",
    "ExtractionAssertion",
    "OntologyExtractionEnvelope",
    "chunk_hash",
    "graph_documents_to_envelope",
    "filter_graph_documents_by_envelope",
    "SemanticValidationReport",
    "validate_envelope",
    "validate_envelope_yaml",
    "NodeValidationReport",
    "validate_graph_document_nodes",
    "validate_graph_document_nodes_yaml",
    "ShaclValidationReport",
    "assertion_graph",
    "validate_envelope_shacl",
    "EntityCandidate",
    "EntityResolution",
    "EntityResolver",
    "normalize_mention",
    "resolve_envelope",
    "resolver_from_neo4j",
    "ReconciliationGroup",
    "project_entity_metadata",
    "project_relationship_metadata",
    "verify_envelope_evidence",
    "OntologyQueryPlan",
    "OntologyQueryPlanner",
    "ontology_answering_context",
    "AuthorityDrift",
    "AuthorityPolicy",
    "compare_labels",
    "CompatibilityReport",
    "IriMigration",
    "MigrationPlan",
    "build_migration_plan",
    "check_compatibility",
    "NoOpProfileValidator",
    "ProfileValidator",
    "validate_with_optional_profile",
    "write_extraction_log",
    "load_reasoning_closure",
    "reason_over_ontology",
]
