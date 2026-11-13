import re
from pathlib import Path
from types import SimpleNamespace

import yaml

from src.llm import (
    _append_ontology_text_chunks_log,
    _format_ontology_context_for_log,
    build_transformer_instructions,
)
from src.llm import rewrite_inverse_relationships
from src.ontology_registry.graph_document import filter_graph_documents_by_envelope
from src.ontology_registry.envelope import ExtractionAssertion, OntologyExtractionEnvelope
from src.ontology_registry.adapter import OntologyExtractionAdapter
from langchain_neo4j.graphs.graph_document import GraphDocument, Node, Relationship


ROOT = Path(__file__).parents[1]
MANIFEST = ROOT / "backend/src/Ontology/manifest.yaml"
BUSINESS_PROFILES = (
    "business-order-to-cash",
    "business-procurement-supplier-management",
    "business-fulfillment-logistics",
    "business-revenue-accounting",
    "business-governance-risk-compliance",
    "business-products-inventory",
)


def _full_business_profile():
    return OntologyExtractionAdapter.build_selected(MANIFEST, BUSINESS_PROFILES)


def test_final_transformer_instructions_have_no_braces():
    profile = _full_business_profile()
    instructions = build_transformer_instructions("Use {only} source facts", profile.yaml_context)
    assert "{" not in instructions
    assert "}" not in instructions


def test_yaml_context_has_no_type_sets_or_aliases_and_preserves_yaml_layout():
    profile = _full_business_profile()
    assert "type_sets:" not in profile.yaml_context
    assert "&" not in profile.yaml_context
    assert "*" not in profile.yaml_context
    assert "\ngroups:\n  things_and_places:" in profile.yaml_context
    assert "\n  - {label:" in profile.yaml_context


def test_context_log_formats_yaml_as_readable_block_documents():
    profile = _full_business_profile()
    formatted = _format_ontology_context_for_log(profile.yaml_context)

    assert "\n  - {label:" not in formatted
    assert "entity_properties:\n  - identifier\n  - amount" in formatted
    assert "# Source profile: business.yaml" in formatted
    assert "\n---\n\n# Source profile: core.yaml" in formatted

    documents = list(yaml.safe_load_all(formatted))
    assert len(documents) == len(profile.yaml_context.split("# Source profile: ")) - 1
    assert documents[0]["profile"]["id"] == "business-common"


def test_text_chunk_log_includes_selection_sample_and_chunk_ids(tmp_path):
    log_path = tmp_path / "ontology-llm-text-chunks.log"
    chunks = [
        SimpleNamespace(
            page_content="Sales Order SO-1\nCustomer: Acme",
            metadata={"combined_chunk_ids": ["chunk-1", "chunk-2"]},
        ),
        SimpleNamespace(
            page_content="Shipment SH-1\nStatus: dispatched",
            metadata={"combined_chunk_ids": ["chunk-3"]},
        ),
    ]

    _append_ontology_text_chunks_log(log_path, chunks, "Sales Order SO-1", 24000)
    logged = log_path.read_text(encoding="utf-8")

    assert "Text sample sent to profile selection:\nSales Order SO-1" in logged
    assert "Combined chunk 1/2 | source chunk IDs: chunk-1, chunk-2" in logged
    assert "Sales Order SO-1\nCustomer: Acme" in logged
    assert "Combined chunk 2/2 | source chunk IDs: chunk-3" in logged
    assert "Shipment SH-1\nStatus: dispatched" in logged


def test_yaml_relationship_domain_and_range_lists_are_single_line():
    profile = _full_business_profile()
    lines = profile.yaml_context.splitlines()
    assert all(line.strip().startswith(("domain:", "range:")) for line in lines if "domain:" in line or "range:" in line)
    assert any("domain: [Sales Order]" in line for line in lines)
    assert any("range: [Discount Approval]" in line for line in lines)


def test_only_user_instructions_are_sanitized():
    profile = _full_business_profile()
    instructions = build_transformer_instructions("{user} os.getenv(", profile.yaml_context)
    assert "[user]" in instructions
    assert "[BLOCKED]" in instructions
    assert "domain: [Sales Order]" in instructions


def test_prompt_omits_iris_and_keeps_inverse_pairs_once():
    profile = _full_business_profile()
    assert "iri:" not in profile.yaml_context
    assert "http://" not in profile.yaml_context
    for dropped, kept in profile.inverse_relationships:
        assert profile.yaml_context.count(f"label: {dropped}") == 0
        assert len(
            re.findall(rf"label: {re.escape(kept)}(?=[,\n}}])", profile.yaml_context)
        ) == 1


def test_iri_lookups_cover_all_allowed_classes_and_relationships():
    profile = _full_business_profile()
    class_lookup = dict(profile.class_iri_lookup)
    relationship_lookup = dict(profile.relationship_iri_lookup)
    assert set(profile.allowed_nodes) <= set(class_lookup)
    labels = {
        item if isinstance(item, str) else item[1]
        for item in profile.allowed_relationships
    }
    assert labels <= set(relationship_lookup)


def test_dropped_inverse_relationship_is_rewritten_with_swapped_endpoints():
    source = Node(id="process", type="Process")
    target = Node(id="step", type="Step")
    document = GraphDocument(
        nodes=[source, target],
        relationships=[Relationship(source=source, target=target, type="step of")],
    )
    rewrite_inverse_relationships([document], (("step of", "has step"),))
    relationship = document.relationships[0]
    assert relationship.type == "has step"
    assert relationship.source is target
    assert relationship.target is source


def test_relationship_matching_is_case_and_separator_insensitive():
    source = Node(id="a", type="A")
    target = Node(id="b", type="B")
    document = GraphDocument(
        nodes=[source, target],
        relationships=[Relationship(source=source, target=target, type="HAS_MAINTENANCE_STATE")],
    )
    assertion = ExtractionAssertion.candidate(
        subject_iri="urn:a", subject_class_iri="A", predicate_iri="has maintenance state",
        object_iri="urn:b", object_class_iri="B", subject_mention="a", object_mention="b",
    )
    assertion = assertion.__class__(**{**assertion.__dict__, "validation_status": "valid"})
    envelope = OntologyExtractionEnvelope((assertion,))
    filtered, removed = filter_graph_documents_by_envelope([document], envelope)
    assert removed == 0
    assert len(filtered[0].relationships) == 1
    rewrite_inverse_relationships([document], (("HAS_MAINTENANCE_STATE", "has maintenance state"),))
    assert document.relationships[0].type == "has maintenance state"
