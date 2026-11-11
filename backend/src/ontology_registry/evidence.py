"""Verification of extraction evidence against source chunks."""

from __future__ import annotations

from dataclasses import replace
from typing import Mapping

from .envelope import OntologyExtractionEnvelope
from .provenance import chunk_hash


def verify_envelope_evidence(
    envelope: OntologyExtractionEnvelope,
    chunks: Mapping[str, object],
    *,
    require_exact: bool = False,
) -> tuple[OntologyExtractionEnvelope, dict[str, int]]:
    """Verify chunk references, hashes, offsets, and exact spans.

    ``chunks`` values may be strings or LangChain Documents. Missing exact
    spans are reported separately and only quarantine assertions when
    ``require_exact`` is enabled.
    """
    verified = missing = invalid = 0
    assertions = []
    for assertion in envelope.assertions:
        evidence = assertion.evidence
        if evidence is None:
            missing += 1
            status = "quarantined" if require_exact else "missing"
            assertions.append(replace(assertion, assertion_status="quarantined" if require_exact else assertion.assertion_status,
                                      validation_status="quarantined" if require_exact else assertion.validation_status))
            continue
        source = chunks.get(evidence.source_chunk_id)
        text = source if isinstance(source, str) else getattr(source, "page_content", None)
        if text is None:
            invalid += 1
            assertions.append(replace(assertion, assertion_status="quarantined", validation_status="quarantined"))
            continue
        if evidence.text_span is None or evidence.start_offset is None or evidence.end_offset is None:
            missing += 1
            assertions.append(replace(assertion, assertion_status="quarantined" if require_exact else assertion.assertion_status,
                                      validation_status="quarantined" if require_exact else assertion.validation_status,
                                      evidence=replace(evidence, evidence_status="missing")))
            continue
        hash_ok = not evidence.source_hash or evidence.source_hash == chunk_hash(text)
        span_ok = evidence.verify(text)
        if hash_ok and span_ok:
            verified += 1
            assertions.append(replace(assertion, evidence=replace(evidence, evidence_status="verified")))
        else:
            invalid += 1
            assertions.append(replace(
                assertion,
                assertion_status="quarantined",
                validation_status="quarantined",
                evidence=replace(evidence, evidence_status="mismatch"),
            ))
    return replace(envelope, assertions=tuple(assertions)), {
        "verified": verified, "missing": missing, "invalid": invalid,
    }
