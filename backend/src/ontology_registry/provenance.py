"""Evidence and source provenance for ontology extraction assertions."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Any, Mapping


@dataclass(frozen=True)
class EvidenceProvenance:
    """A location in the source that supports one extraction assertion.

    Offsets are zero-based, half-open character offsets into ``chunk_text``.
    ``text_span`` is retained verbatim so evidence can be displayed without
    re-reading the source.  A caller may omit text/offsets for a candidate, but
    persisted or verified assertions should provide them.
    """

    source_document_id: str
    source_chunk_id: str
    text_span: str | None = None
    page: int | None = None
    start_offset: int | None = None
    end_offset: int | None = None
    source_document_version: str | None = None
    source_hash: str | None = None
    evidence_status: str = "unverified"

    def __post_init__(self) -> None:
        if not self.source_document_id.strip() or not self.source_chunk_id.strip():
            raise ValueError("source_document_id and source_chunk_id are required")
        if self.page is not None and self.page < 1:
            raise ValueError("page must be a positive number")
        if self.start_offset is not None and self.start_offset < 0:
            raise ValueError("start_offset must be non-negative")
        if self.end_offset is not None and self.end_offset < 0:
            raise ValueError("end_offset must be non-negative")
        if (self.start_offset is None) != (self.end_offset is None):
            raise ValueError("start_offset and end_offset must be supplied together")
        if self.start_offset is not None and self.end_offset < self.start_offset:
            raise ValueError("end_offset must be greater than or equal to start_offset")
        if self.source_hash and not self.source_hash.startswith("sha256:"):
            raise ValueError("source_hash must use the sha256:<digest> form")

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "EvidenceProvenance":
        aliases = {"chunk_id": "source_chunk_id", "document_id": "source_document_id",
                   "character_start": "start_offset", "character_end": "end_offset"}
        data = {aliases.get(key, key): item for key, item in value.items()}
        return cls(**{key: data[key] for key in cls.__dataclass_fields__ if key in data})

    def verify(self, chunk_text: str) -> bool:
        """Check offsets and exact span against the supplied chunk text."""
        if self.text_span is None or self.start_offset is None or self.end_offset is None:
            return False
        return chunk_text[self.start_offset:self.end_offset] == self.text_span

    def as_dict(self) -> dict[str, Any]:
        return {key: value for key, value in {
            "source_document_id": self.source_document_id,
            "source_document_version": self.source_document_version,
            "source_hash": self.source_hash,
            "source_chunk_id": self.source_chunk_id,
            "page": self.page,
            "start_offset": self.start_offset,
            "end_offset": self.end_offset,
            "text_span": self.text_span,
            "evidence_status": self.evidence_status,
        }.items() if value is not None}


def chunk_hash(chunk_text: str) -> str:
    """Return the canonical hash format used by provenance records."""
    return "sha256:" + sha256(chunk_text.encode("utf-8")).hexdigest()
