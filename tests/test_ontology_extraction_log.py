from src.ontology_registry import ExtractionAssertion, OntologyExtractionEnvelope, write_extraction_log


def test_extraction_log_appends_structured_jsonl(tmp_path):
    envelope = OntologyExtractionEnvelope((ExtractionAssertion.candidate(
        subject_iri="urn:s", subject_class_iri="urn:Plant", predicate_iri="urn:p",
        object_iri="urn:o", object_class_iri="urn:Product",
    ),))
    path = write_extraction_log(envelope, source_name="sample.pdf", stage="raw_after_extraction", path=tmp_path / "ontology.log")
    content = path.read_text(encoding="utf-8")
    assert "Source: sample.pdf" in content
    assert "Stage: raw_after_extraction" in content
    assert "Extraction envelope:" in content
    assert envelope.assertions[0].assertion_id in content
