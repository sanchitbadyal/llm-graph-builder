import json
from collections import Counter
from pathlib import Path
import re
from types import SimpleNamespace

import pytest

from src.ontology_registry import (
    OntologyExtractionAdapter,
    OntologyExtractionEnvelope,
    validate_envelope_yaml,
    validate_graph_document_nodes_yaml,
)


ROOT = Path(__file__).parents[1]
MANIFEST = ROOT / "backend/src/Ontology/manifest.yaml"
EXTRACTION_LOG = ROOT / "logs/ontology-extraction.log"
SOURCE_DOCUMENT = "cabalmar_plant_fulfillment_process.pdf"
ENVELOPE_MARKER = "Extraction envelope:\n"


def _normalized_label(value):
    return re.sub(r"[^a-z0-9]", "", value.casefold())


def _latest_raw_envelope(log_text, source_document):
    decoder = json.JSONDecoder()
    latest = None
    position = 0

    while True:
        marker_position = log_text.find(ENVELOPE_MARKER, position)
        if marker_position < 0:
            break
        json_start = marker_position + len(ENVELOPE_MARKER)
        data, json_length = decoder.raw_decode(log_text[json_start:])
        header = log_text[max(0, marker_position - 1200):marker_position]
        source = re.search(r"^Source: (.+)$", header, re.MULTILINE)
        stage = re.search(r"^Stage: (.+)$", header, re.MULTILINE)
        if (
            source
            and source.group(1) == source_document
            and stage
            and stage.group(1) == "raw_after_extraction"
        ):
            latest = OntologyExtractionEnvelope.from_mapping(data)
        position = json_start + json_length

    return latest


@pytest.mark.skipif(not EXTRACTION_LOG.is_file(), reason="local extraction log is unavailable")
def test_latest_cabalmar_extraction_log_is_validated_against_selected_yaml():
    envelope = _latest_raw_envelope(
        EXTRACTION_LOG.read_text(encoding="utf-8"),
        SOURCE_DOCUMENT,
    )
    if envelope is None:
        pytest.skip(f"no raw extraction for {SOURCE_DOCUMENT} in local log")

    profile_ids = envelope.ontology_id.split(",") if envelope.ontology_id else []
    profile = OntologyExtractionAdapter.build_selected(MANIFEST, profile_ids)
    validated, report = validate_envelope_yaml(envelope, profile)

    assert report.total == len(envelope.assertions)
    assert report.valid + report.rejected + report.quarantined == report.total

    labels_by_iri = {
        iri: label for label, iri in profile.class_iri_lookup
    }
    relationships_by_iri = {
        iri: label for label, iri in profile.relationship_iri_lookup
    }
    extracted_nodes = {}
    for assertion in envelope.assertions:
        for mention, class_iri in (
            (assertion.subject_mention, assertion.subject_class_iri),
            (assertion.object_mention, assertion.object_class_iri),
        ):
            if mention is None or class_iri is None:
                continue
            extracted_nodes[(mention, class_iri)] = SimpleNamespace(
                id=mention,
                type=labels_by_iri.get(class_iri, class_iri),
                properties={},
            )
    graph_document = SimpleNamespace(
        nodes=list(extracted_nodes.values()),
        relationships=[],
    )
    node_report = validate_graph_document_nodes_yaml([graph_document], profile)

    print(
        f"YAML validation for {SOURCE_DOCUMENT}: "
        f"nodes rejected={node_report.rejected}/{node_report.valid + node_report.rejected}; "
        f"relationships rejected={report.rejected}/{report.total}; "
        f"relationships quarantined={report.quarantined}"
    )
    errors_by_id = {error["assertion_id"]: error for error in report.errors}
    print("\nRelationship rejection counts by reason:")
    for code, count in sorted(Counter(
        error["code"] for error in report.errors
    ).items()):
        print(f"  {code}: {count}")

    if report.errors:
        print("\nRejected relationship details:")
        for assertion in validated.assertions:
            error = errors_by_id.get(assertion.assertion_id)
            if error is None:
                continue
            subject_class = labels_by_iri.get(
                assertion.subject_class_iri, assertion.subject_class_iri
            )
            object_class = labels_by_iri.get(
                assertion.object_class_iri, assertion.object_class_iri or "unknown"
            )
            predicate = relationships_by_iri.get(
                assertion.predicate_iri, assertion.predicate_iri
            )
            object_value = assertion.object_mention or assertion.object_literal
            print(
                f"  [{error['code']}] {assertion.subject_mention!r} "
                f"({subject_class}) --{predicate}--> {object_value!r} "
                f"({object_class})"
            )
            print(f"    assertion_id: {assertion.assertion_id}")
            print(f"    reason: {error['message']}")

    plant_subunit_assertions = [
        assertion
        for assertion in validated.assertions
        if _normalized_label(assertion.predicate_iri) == _normalized_label("has sub-unit")
        and assertion.subject_mention == "Cabalmar Chemicals"
        and assertion.object_class_iri == dict(profile.class_iri_lookup).get("Plant")
    ]
    assert len(plant_subunit_assertions) == 10
    assert all(
        assertion.validation_status == "invalid"
        and assertion.assertion_status == "rejected"
        for assertion in plant_subunit_assertions
    )
    assert report.rejected >= len(plant_subunit_assertions)
