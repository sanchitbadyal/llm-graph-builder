from pathlib import Path
from types import SimpleNamespace

from src.ontology_registry import (
    ExtractionAssertion,
    OntologyExtractionAdapter,
    OntologyExtractionEnvelope,
    validate_envelope_yaml,
    validate_graph_document_nodes_yaml,
)


ROOT = Path(__file__).parents[1]
MANIFEST = ROOT / "backend/src/Ontology/manifest.yaml"


def _profile():
    return OntologyExtractionAdapter.build_selected(
        MANIFEST, ["business-order-to-cash"]
    )


def _assertion(profile, subject, predicate, object_):
    classes = dict(profile.class_iri_lookup)
    relationships = dict(profile.relationship_iri_lookup)
    return ExtractionAssertion.candidate(
        subject_iri="urn:subject",
        subject_class_iri=classes[subject],
        predicate_iri=relationships[predicate],
        object_iri="urn:object",
        object_class_iri=classes[object_],
        subject_mention="subject",
        object_mention="object",
    )


def test_yaml_semantic_validation_accepts_defined_compatible_triple():
    profile = _profile()
    envelope = OntologyExtractionEnvelope((
        _assertion(profile, "Sales Order", "has customer", "Customer"),
    ))

    validated, report = validate_envelope_yaml(envelope, profile)

    assert report.valid == 1
    assert report.rejected == 0
    assert validated.assertions[0].validation_status == "valid"


def test_yaml_semantic_validation_rejects_incompatible_domain_and_range():
    profile = _profile()
    envelope = OntologyExtractionEnvelope((
        _assertion(profile, "Organization", "has customer", "Customer"),
        _assertion(profile, "Sales Order", "has customer", "Organization"),
    ))

    validated, report = validate_envelope_yaml(envelope, profile)

    assert report.valid == 0
    assert report.rejected == 2
    assert [error["code"] for error in report.errors] == [
        "incompatible_domain",
        "incompatible_range",
    ]
    assert all(item.validation_status == "invalid" for item in validated.assertions)


def test_performed_by_allows_process_to_person_and_rejects_reverse_direction():
    profile = OntologyExtractionAdapter.build_selected(
        MANIFEST, ["business-fulfillment-logistics", "production-planning-complete"]
    )
    process_to_person = _assertion(
        profile, "Process Step", "performed by", "Person"
    )
    person_to_process = _assertion(
        profile, "Person", "performed by", "Process Step"
    )
    envelope = OntologyExtractionEnvelope((process_to_person, person_to_process))

    validated, report = validate_envelope_yaml(envelope, profile)

    assert report.valid == 1
    assert report.rejected == 1
    assert report.errors[0]["code"] == "incompatible_domain"
    assert validated.assertions[0].validation_status == "valid"
    assert validated.assertions[1].validation_status == "invalid"


def test_organization_operates_plant_without_treating_plant_as_sub_unit():
    profile = OntologyExtractionAdapter.build_selected(
        MANIFEST, ["business-fulfillment-logistics"]
    )
    assertions = (
        _assertion(profile, "Organization", "operates", "Plant"),
        _assertion(profile, "Legal Entity", "operates", "Plant"),
        _assertion(profile, "Organization", "has sub-unit", "Plant"),
    )

    validated, report = validate_envelope_yaml(
        OntologyExtractionEnvelope(assertions), profile
    )

    assert report.valid == 2
    assert report.rejected == 1
    assert report.errors[0]["code"] == "incompatible_range"
    assert [item.validation_status for item in validated.assertions] == [
        "valid", "valid", "invalid"
    ]


def test_workflow_relations_allow_process_steps_and_locations_but_not_orders():
    profile = OntologyExtractionAdapter.build_selected(
        MANIFEST, ["business-fulfillment-logistics", "production-planning-complete"]
    )
    assertions = (
        _assertion(profile, "Business Process", "triggers", "Process Step"),
        _assertion(profile, "Product Inspection Process", "triggers", "Business Process"),
        _assertion(profile, "Business Process", "performed at", "Location"),
        _assertion(profile, "Production Order", "triggers", "Process Step"),
        _assertion(profile, "Business Process", "triggers", "Production Order"),
    )

    validated, report = validate_envelope_yaml(
        OntologyExtractionEnvelope(assertions), profile
    )

    assert report.valid == 3
    assert report.rejected == 2
    assert [error["code"] for error in report.errors] == [
        "incompatible_domain", "incompatible_range"
    ]
    assert [item.validation_status for item in validated.assertions] == [
        "valid", "valid", "valid", "invalid", "invalid"
    ]


def test_non_conformance_records_can_be_issued_and_used_as_business_inputs():
    profile = OntologyExtractionAdapter.build_selected(
        MANIFEST, ["business-fulfillment-logistics", "production-planning-complete"]
    )
    assertions = (
        _assertion(profile, "Non-Conformance Record", "issued by", "Person"),
        _assertion(profile, "Business Process", "has business input", "Non-Conformance Record"),
    )

    _, report = validate_envelope_yaml(OntologyExtractionEnvelope(assertions), profile)

    assert report.valid == 2
    assert report.rejected == 0


def test_yaml_node_validation_rejects_classes_outside_selected_profiles():
    profile = _profile()
    accepted = SimpleNamespace(id="order", type="Sales Order", properties={})
    rejected = SimpleNamespace(id="plant", type="Unlisted Class", properties={})
    document = SimpleNamespace(nodes=[accepted, rejected], relationships=[])

    report = validate_graph_document_nodes_yaml([document], profile)

    assert report.valid == 1
    assert report.rejected == 1
    assert document.nodes == [accepted]
