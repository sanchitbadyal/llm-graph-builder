"""Stable ontology-aware extraction envelope (independent of LangChain)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping
from uuid import uuid4

from .provenance import EvidenceProvenance

ASSERTION_STATUSES = frozenset({
    "explicit", "deterministically_derived", "ontology_inferred", "llm_candidate",
    "quarantined", "rejected", "verified",
})
VALIDATION_STATUSES = frozenset({"not_validated", "valid", "invalid", "quarantined"})


@dataclass(frozen=True)
class ExtractionAssertion:
    assertion_id: str
    subject_iri: str
    subject_class_iri: str
    predicate_iri: str
    object_iri: str | None = None
    object_literal: Any | None = None
    object_class_iri: str | None = None
    subject_mention: str | None = None
    object_mention: str | None = None
    ontology_layer: str | None = None
    assertion_status: str = "llm_candidate"
    evidence: EvidenceProvenance | None = None
    extraction_model: str | None = None
    extraction_timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    confidence: float | None = None
    validation_status: str = "not_validated"

    def __post_init__(self) -> None:
        if not self.assertion_id.strip() or not self.subject_iri.strip() or not self.subject_class_iri.strip() or not self.predicate_iri.strip():
            raise ValueError("assertion_id, subject_iri, subject_class_iri, and predicate_iri are required")
        if (self.object_iri is None) == (self.object_literal is None):
            raise ValueError("exactly one of object_iri or object_literal is required")
        if self.assertion_status not in ASSERTION_STATUSES:
            raise ValueError(f"unknown assertion_status: {self.assertion_status}")
        if self.validation_status not in VALIDATION_STATUSES:
            raise ValueError(f"unknown validation_status: {self.validation_status}")
        if self.confidence is not None and not 0 <= self.confidence <= 1:
            raise ValueError("confidence must be between 0 and 1")

    @classmethod
    def candidate(cls, *, subject_iri: str, subject_class_iri: str, predicate_iri: str,
                  object_iri: str | None = None, object_literal: Any | None = None, **kwargs: Any) -> "ExtractionAssertion":
        return cls(assertion_id=str(uuid4()), subject_iri=subject_iri, subject_class_iri=subject_class_iri,
                   predicate_iri=predicate_iri, object_iri=object_iri, object_literal=object_literal, **kwargs)

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "ExtractionAssertion":
        data = dict(value)
        if isinstance(data.get("evidence"), Mapping):
            data["evidence"] = EvidenceProvenance.from_mapping(data["evidence"])
        return cls(**data)

    def as_dict(self) -> dict[str, Any]:
        result = {key: value for key, value in self.__dict__.items() if value is not None}
        if self.evidence is not None:
            result["evidence"] = self.evidence.as_dict()
        return result


@dataclass(frozen=True)
class OntologyExtractionEnvelope:
    assertions: tuple[ExtractionAssertion, ...] = ()
    ontology_id: str | None = None
    source_document_id: str | None = None
    extraction_model: str | None = None
    envelope_version: str = "1.0"

    def as_dict(self) -> dict[str, Any]:
        return {"envelope_version": self.envelope_version, "ontology_id": self.ontology_id,
                "source_document_id": self.source_document_id,
                "extraction_model": self.extraction_model,
                "assertions": [item.as_dict() for item in self.assertions]}

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "OntologyExtractionEnvelope":
        return cls(assertions=tuple(ExtractionAssertion.from_mapping(item) for item in value.get("assertions", ())),
                   **{key: value[key] for key in ("ontology_id", "source_document_id", "extraction_model", "envelope_version") if key in value})
