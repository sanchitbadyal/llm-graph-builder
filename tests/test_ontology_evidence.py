from src.ontology_registry import (
    EvidenceProvenance, ExtractionAssertion, OntologyExtractionEnvelope,
    chunk_hash, verify_envelope_evidence,
)


def assertion(evidence):
    return ExtractionAssertion.candidate(
        subject_iri="urn:s", subject_class_iri="urn:Plant", predicate_iri="urn:p",
        object_iri="urn:o", object_class_iri="urn:Product", evidence=evidence,
    )


def test_phase10_verifies_exact_span_and_hash():
    text = "The plant produces bromine."
    evidence = EvidenceProvenance(
        source_document_id="doc", source_chunk_id="chunk", text_span="produces bromine",
        start_offset=10, end_offset=26, source_hash=chunk_hash(text),
    )
    envelope, report = verify_envelope_evidence(
        OntologyExtractionEnvelope((assertion(evidence),)), {"chunk": text}, require_exact=True,
    )
    assert report["verified"] == 1
    assert envelope.assertions[0].evidence.evidence_status == "verified"


def test_phase10_quarantines_mismatched_span():
    evidence = EvidenceProvenance(
        source_document_id="doc", source_chunk_id="chunk", text_span="wrong",
        start_offset=0, end_offset=5,
    )
    envelope, report = verify_envelope_evidence(
        OntologyExtractionEnvelope((assertion(evidence),)), {"chunk": "actual text"}, require_exact=True,
    )
    assert report["invalid"] == 1
    assert envelope.assertions[0].validation_status == "quarantined"


def test_phase10_missing_span_is_non_blocking_by_default():
    envelope, report = verify_envelope_evidence(
        OntologyExtractionEnvelope((assertion(EvidenceProvenance(source_document_id="doc", source_chunk_id="chunk")),)),
        {"chunk": "actual text"},
    )
    assert report["missing"] == 1
    assert envelope.assertions[0].assertion_status == "llm_candidate"
