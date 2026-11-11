"""Deterministic validation for ontology extraction envelopes."""

from __future__ import annotations

from dataclasses import dataclass, replace

from .envelope import ExtractionAssertion, OntologyExtractionEnvelope
from .semantic import SemanticResolver


@dataclass(frozen=True)
class SemanticValidationReport:
    valid: int = 0
    rejected: int = 0
    quarantined: int = 0
    errors: tuple[dict[str, str], ...] = ()

    @property
    def total(self) -> int:
        return self.valid + self.rejected + self.quarantined

    def as_dict(self) -> dict[str, object]:
        return {
            "valid": self.valid,
            "rejected": self.rejected,
            "quarantined": self.quarantined,
            "total": self.total,
            "errors": list(self.errors),
        }


@dataclass(frozen=True)
class NodeValidationReport:
    valid: int = 0
    rejected: int = 0
    invalid_property_keys: int = 0

    def as_dict(self) -> dict[str, int]:
        return {"valid": self.valid, "rejected": self.rejected,
                "invalid_property_keys": self.invalid_property_keys}


def validate_graph_document_nodes(graph_documents: list[object], resolver: SemanticResolver) -> NodeValidationReport:
    """Remove nodes with unknown ontology classes before graph projection.

    Application/YAML property names are intentionally preserved. Only
    property keys that are full ontology IRIs are checked here; Phase 8 will
    provide shape-level validation for application properties.
    """
    valid = rejected = invalid_property_keys = 0
    for document in graph_documents:
        accepted_nodes = []
        rejected_ids: set[str] = set()
        for node in getattr(document, "nodes", ()) or ():
            try:
                resolver.resolve_class(str(getattr(node, "type", "")))
            except KeyError:
                rejected += 1
                rejected_ids.add(str(getattr(node, "id", "")))
                continue
            properties = getattr(node, "properties", None) or {}
            invalid = [key for key in properties if isinstance(key, str) and (key.startswith("http://") or key.startswith("https://")) and key not in resolver.index.properties]
            if invalid:
                invalid_property_keys += len(invalid)
                node.properties = {key: value for key, value in properties.items() if key not in invalid}
            accepted_nodes.append(node)
            valid += 1
        document.nodes = accepted_nodes
        document.relationships = [
            relationship for relationship in (getattr(document, "relationships", ()) or [])
            if str(getattr(relationship.source, "id", "")) not in rejected_ids
            and str(getattr(relationship.target, "id", "")) not in rejected_ids
        ]
    return NodeValidationReport(valid=valid, rejected=rejected, invalid_property_keys=invalid_property_keys)


def _checked(assertion: ExtractionAssertion, resolver: SemanticResolver) -> tuple[str | None, str | None]:
    """Return an error code/message, or ``(None, None)`` when valid."""
    try:
        subject = resolver.resolve_class(assertion.subject_class_iri)
    except KeyError:
        return "unknown_subject_class", f"Unknown subject class: {assertion.subject_class_iri}"
    try:
        resolver.resolve_property(assertion.predicate_iri)
    except KeyError:
        return "unknown_property", f"Unknown property: {assertion.predicate_iri}"
    if assertion.object_class_iri is None:
        return "missing_object_class", "Object class is required for ontology relationship validation"
    try:
        resolver.resolve_class(assertion.object_class_iri)
    except KeyError:
        return "unknown_object_class", f"Unknown object class: {assertion.object_class_iri}"
    if not resolver.compatible(subject.iri, assertion.predicate_iri, assertion.object_class_iri):
        return "incompatible_domain_range", (
            f"Property {assertion.predicate_iri} is incompatible with "
            f"{assertion.subject_class_iri} -> {assertion.object_class_iri}"
        )
    return None, None


def validate_envelope(
    envelope: OntologyExtractionEnvelope, resolver: SemanticResolver,
) -> tuple[OntologyExtractionEnvelope, SemanticValidationReport]:
    """Validate each candidate without mutating the original envelope.

    Unknown terms and incompatible triples are rejected. Missing class
    information is quarantined because it may be recoverable by entity
    resolution; no LLM confidence is used in this decision.
    """
    assertions: list[ExtractionAssertion] = []
    errors: list[dict[str, str]] = []
    valid = rejected = quarantined = 0
    for assertion in envelope.assertions:
        code, message = _checked(assertion, resolver)
        if code is None:
            assertions.append(replace(assertion, validation_status="valid"))
            valid += 1
            continue
        status = "quarantined" if code == "missing_object_class" else "invalid"
        assertion_status = "quarantined" if status == "quarantined" else "rejected"
        assertions.append(replace(assertion, validation_status=status, assertion_status=assertion_status))
        if status == "quarantined":
            quarantined += 1
        else:
            rejected += 1
        errors.append({"assertion_id": assertion.assertion_id, "code": code, "message": message or ""})
    return replace(envelope, assertions=tuple(assertions)), SemanticValidationReport(
        valid=valid, rejected=rejected, quarantined=quarantined, errors=tuple(errors)
    )
