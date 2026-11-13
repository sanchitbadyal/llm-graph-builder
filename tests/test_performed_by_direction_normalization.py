from pathlib import Path
from types import SimpleNamespace

from langchain_neo4j.graphs.graph_document import Node, Relationship

from src.llm import rewrite_inverse_relationships
from src.ontology_registry import (
    OntologyExtractionAdapter,
    graph_documents_to_envelope,
    validate_envelope_yaml,
)


ROOT = Path(__file__).parents[1]
MANIFEST = ROOT / "backend/src/Ontology/manifest.yaml"


def _relationship(source_type, predicate, target_type):
    source = Node(id="source", type=source_type)
    target = Node(id="target", type=target_type)
    return Relationship(
        source=source,
        target=target,
        type=predicate,
        properties={},
    )


def test_performs_alias_is_reversed_to_canonical_performed_by():
    profile = OntologyExtractionAdapter.build_selected(
        MANIFEST, ["business-fulfillment-logistics", "production-planning-complete"]
    )
    relationship = _relationship("Person", "PERFORMS", "Process Step")
    document = SimpleNamespace(relationships=[relationship])

    rewrite_inverse_relationships(
        [document], profile.inverse_relationships, profile
    )

    normalized = document.relationships[0]
    assert normalized.type == "performed by"
    assert normalized.source.type == "Process Step"
    assert normalized.target.type == "Person"


def test_reversed_performed_by_is_fixed_but_canonical_direction_is_unchanged():
    profile = OntologyExtractionAdapter.build_selected(
        MANIFEST, ["business-fulfillment-logistics", "production-planning-complete"]
    )
    reversed_relationship = _relationship("Person", "PERFORMED_BY", "Process Step")
    canonical_relationship = _relationship("Process Step", "PERFORMED_BY", "Person")
    document = SimpleNamespace(
        relationships=[reversed_relationship, canonical_relationship]
    )

    rewrite_inverse_relationships(
        [document], profile.inverse_relationships, profile
    )

    reversed_normalized, canonical_unchanged = document.relationships
    assert reversed_normalized.source.type == "Process Step"
    assert reversed_normalized.target.type == "Person"
    assert reversed_normalized.type == "performed by"
    assert canonical_unchanged.source.type == "Process Step"
    assert canonical_unchanged.target.type == "Person"

    envelope = graph_documents_to_envelope(
        [document], ontology_id=profile.ontology_id, profile=profile
    )
    _, report = validate_envelope_yaml(envelope, profile)

    assert report.valid == 2
    assert report.rejected == 0
