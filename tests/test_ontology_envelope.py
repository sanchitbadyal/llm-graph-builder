from src.ontology_registry import EvidenceProvenance, ExtractionAssertion, OntologyExtractionEnvelope, chunk_hash


def test_evidence_verification_uses_exact_half_open_offsets():
    evidence = EvidenceProvenance(
        source_document_id="doc-1", source_chunk_id="chunk-1", text_span="plant produces",
        start_offset=4, end_offset=18, page=2,
    )
    assert evidence.verify("The plant produces bromine")
    assert not evidence.verify("The facility produces chlorine")


def test_envelope_round_trips_assertion_and_provenance():
    assertion = ExtractionAssertion.candidate(
        subject_iri="urn:plant:1", subject_class_iri="urn:Plant", predicate_iri="urn:produces",
        object_iri="urn:product:1", object_class_iri="urn:Product",
        evidence=EvidenceProvenance(source_document_id="doc", source_chunk_id="chunk", text_span="makes"),
        confidence=0.8,
    )
    envelope = OntologyExtractionEnvelope(assertions=(assertion,), ontology_id="catalog")
    restored = OntologyExtractionEnvelope.from_mapping(envelope.as_dict())
    assert restored.assertions[0].assertion_id == assertion.assertion_id
    assert restored.assertions[0].evidence.source_chunk_id == "chunk"


def test_chunk_hash_is_stable_and_namespaced():
    assert chunk_hash("abc").startswith("sha256:")
    assert chunk_hash("abc") == chunk_hash("abc")
