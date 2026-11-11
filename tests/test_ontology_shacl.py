from src.ontology_registry import (
    EvidenceProvenance, ExtractionAssertion, OntologyExtractionEnvelope,
    validate_envelope_shacl,
)


def assertion(evidence):
    return ExtractionAssertion.candidate(
        subject_iri="urn:subject", subject_class_iri="urn:Plant",
        predicate_iri="urn:produces", object_iri="urn:product",
        object_class_iri="urn:Product", evidence=evidence,
    )


def test_phase8_accepts_assertions_with_minimum_evidence():
    envelope, report = validate_envelope_shacl(OntologyExtractionEnvelope((assertion(
        EvidenceProvenance(source_document_id="doc", source_chunk_id="chunk"),
    ),)))
    assert report.valid == 1
    assert envelope.assertions[0].validation_status == "valid"


def test_phase8_quarantines_assertions_without_evidence():
    envelope, report = validate_envelope_shacl(OntologyExtractionEnvelope((assertion(None),)))
    assert report.quarantined == 1
    assert envelope.assertions[0].assertion_status == "quarantined"
