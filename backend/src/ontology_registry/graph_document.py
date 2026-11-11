"""Conversion of LangChain graph documents into the Phase 6 envelope."""

from __future__ import annotations

from hashlib import sha256
import logging
from typing import Any, Iterable

from .envelope import ExtractionAssertion, OntologyExtractionEnvelope
from .provenance import EvidenceProvenance


def normalize_relationship_type(value: Any) -> str:
    return " ".join(str(value).replace("_", " ").casefold().split())


def _stable_mention_iri(mention: Any) -> str:
    value = str(mention).strip()
    return "urn:llm-mention:" + sha256(value.casefold().encode("utf-8")).hexdigest()[:32]


def _class_iri(profile: Any, label: Any) -> str | None:
    if profile is None:
        return None
    lookup = dict(getattr(profile, "class_iri_lookup", ()) or ())
    if lookup.get(str(label)):
        return lookup[str(label)]
    for item in profile.prompt_context.split('"iri":"')[1:]:
        iri, _, rest = item.partition('"')
        if '"label":"' + str(label).replace('"', '\\"') + '"' in rest:
            return iri
    return None


def _property_iri(profile: Any, predicate: Any) -> str | None:
    if profile is None:
        return None
    lookup = dict(getattr(profile, "relationship_iri_lookup", ()) or ())
    if lookup.get(str(predicate)):
        return lookup[str(predicate)]
    for item in profile.prompt_context.split('"iri":"')[1:]:
        iri, _, rest = item.partition('"')
        if '"label":"' + str(predicate).replace('"', '\\"') + '"' in rest:
            return iri
    return None


def graph_documents_to_envelope(
    graph_documents: Iterable[Any], *, model: str | None = None,
    ontology_id: str | None = None, profile: Any = None,
) -> OntologyExtractionEnvelope:
    """Create candidate assertions without changing the original documents.

    GraphDocument does not expose evidence spans, so this phase records the
    source chunk reference when available and leaves evidence unverified.
    Canonical mention IRIs are deterministic placeholders, never persisted as
    ontology identities; entity resolution will replace them in a later phase.
    """
    assertions: list[ExtractionAssertion] = []
    input_nodes = 0
    input_relationships = 0
    skipped = 0
    for document in graph_documents:
        input_nodes += len(getattr(document, "nodes", ()) or ())
        input_relationships += len(getattr(document, "relationships", ()) or ())
        metadata = getattr(document, "source", None) or getattr(document, "metadata", None) or {}
        metadata = getattr(metadata, "metadata", metadata) or {}
        chunk_ids = metadata.get("combined_chunk_ids") or metadata.get("chunk_id") or ["unknown-chunk"]
        if isinstance(chunk_ids, str):
            chunk_ids = [chunk_ids]
        for relationship in getattr(document, "relationships", ()) or ():
            source = getattr(relationship, "source", None)
            target = getattr(relationship, "target", None)
            predicate = str(getattr(relationship, "type", ""))
            if source is None or target is None or not predicate.strip():
                skipped += 1
                logging.warning("Ontology envelope skipped relationship label=%r reason=missing_endpoint_or_type", predicate)
                continue
            source_type = str(getattr(source, "type", ""))
            target_type = str(getattr(target, "type", ""))
            subject_class = _class_iri(profile, source_type) or source_type
            object_class = _class_iri(profile, target_type) or target_type
            predicate_iri = _property_iri(profile, predicate) or predicate
            evidence = EvidenceProvenance(
                source_document_id=str(metadata.get("source_document_id", "unknown-document")),
                source_chunk_id=str(chunk_ids[0]),
            )
            assertions.append(ExtractionAssertion.candidate(
                subject_iri=_stable_mention_iri(source.id), subject_class_iri=subject_class,
                predicate_iri=predicate_iri, object_iri=_stable_mention_iri(target.id),
                object_class_iri=object_class, subject_mention=str(source.id),
                object_mention=str(target.id), ontology_layer="domain" if profile else None,
                evidence=evidence, extraction_model=model,
            ))
    logging.info("Ontology envelope conversion: input_nodes=%d input_relationships=%d assertions=%d skipped=%d", input_nodes, input_relationships, len(assertions), skipped)
    return OntologyExtractionEnvelope(tuple(assertions), ontology_id=ontology_id, extraction_model=model)


def filter_graph_documents_by_envelope(
    graph_documents: Iterable[Any], envelope: OntologyExtractionEnvelope,
) -> tuple[list[Any], int]:
    """Remove relationships whose corresponding ontology assertion is not valid."""
    valid = {
        (item.subject_mention, normalize_relationship_type(item.predicate_iri), item.object_mention)
        for item in envelope.assertions
        if item.validation_status == "valid"
    }
    removed = 0
    documents = list(graph_documents)
    for document in documents:
        relationships = []
        for relationship in getattr(document, "relationships", ()) or ():
            source = relationship.source
            target = relationship.target
            key = (str(getattr(source, "id", "")), normalize_relationship_type(getattr(relationship, "type", "")), str(getattr(target, "id", "")))
            if key in valid:
                relationships.append(relationship)
            else:
                removed += 1
        document.relationships = relationships
    return documents, removed
