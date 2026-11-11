"""SHACL validation for ontology extraction assertions."""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from rdflib import BNode, Graph, Literal, Namespace, URIRef
from rdflib.namespace import OWL, RDF
from pyshacl import validate

from .envelope import ExtractionAssertion, OntologyExtractionEnvelope

EX = Namespace("urn:ontology-registry:")


@dataclass(frozen=True)
class ShaclValidationReport:
    valid: int = 0
    quarantined: int = 0
    errors: tuple[dict[str, str], ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {"valid": self.valid, "quarantined": self.quarantined,
                "errors": list(self.errors)}


def _uri(value: str) -> URIRef:
    return URIRef(value if "://" in value or value.startswith("urn:") else "urn:label:" + value)


def assertion_graph(assertion: ExtractionAssertion) -> Graph:
    graph = Graph()
    subject = _uri(assertion.subject_iri)
    predicate = _uri(assertion.predicate_iri)
    graph.add((subject, RDF.type, EX.AssertionSubject))
    graph.add((subject, EX.subjectClass, _uri(assertion.subject_class_iri)))
    graph.add((subject, predicate, _uri(assertion.object_iri) if assertion.object_iri else Literal(assertion.object_literal)))
    if assertion.object_class_iri:
        object_node = _uri(assertion.object_iri) if assertion.object_iri else BNode()
        graph.add((object_node, RDF.type, OWL.Thing))
        graph.add((object_node, EX.objectClass, _uri(assertion.object_class_iri)))
    if assertion.evidence:
        evidence = BNode()
        graph.add((subject, EX.evidence, evidence))
        graph.add((evidence, EX.sourceDocument, Literal(assertion.evidence.source_document_id)))
        graph.add((evidence, EX.sourceChunk, Literal(assertion.evidence.source_chunk_id)))
        if assertion.evidence.text_span is not None:
            graph.add((evidence, EX.textSpan, Literal(assertion.evidence.text_span)))
    return graph


def validate_envelope_shacl(
    envelope: OntologyExtractionEnvelope, shapes_path: str | Path | None = None,
) -> tuple[OntologyExtractionEnvelope, ShaclValidationReport]:
    shapes = Graph()
    path = Path(shapes_path) if shapes_path else Path(__file__).resolve().parents[1] / "Ontology" / "shapes" / "phase8.ttl"
    shapes.parse(path, format="turtle")
    assertions = []
    errors: list[dict[str, str]] = []
    valid = quarantined = 0
    for assertion in envelope.assertions:
        conforms, _, report_text = validate(assertion_graph(assertion), shacl_graph=shapes, inference="none", advanced=True)
        if conforms:
            assertions.append(replace(assertion, validation_status="valid"))
            valid += 1
        else:
            assertions.append(replace(assertion, validation_status="quarantined", assertion_status="quarantined"))
            quarantined += 1
            errors.append({"assertion_id": assertion.assertion_id, "message": str(report_text)})
    return replace(envelope, assertions=tuple(assertions)), ShaclValidationReport(valid, quarantined, tuple(errors))
