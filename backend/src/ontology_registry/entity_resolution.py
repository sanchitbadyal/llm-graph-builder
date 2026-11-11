"""Deterministic ontology-aware entity resolution for extraction assertions."""

from __future__ import annotations

from dataclasses import dataclass, replace
import re
from typing import Iterable, Mapping

from .envelope import ExtractionAssertion, OntologyExtractionEnvelope


def normalize_mention(value: str) -> str:
    """Normalize a mention for conservative exact alias matching."""
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


@dataclass(frozen=True)
class EntityCandidate:
    iri: str
    class_iri: str
    preferred_label: str
    aliases: tuple[str, ...] = ()

    def labels(self) -> tuple[str, ...]:
        return (self.preferred_label, *self.aliases)


@dataclass(frozen=True)
class EntityResolution:
    mention: str
    iri: str | None
    class_iri: str | None
    status: str
    candidates: tuple[str, ...] = ()


@dataclass(frozen=True)
class ReconciliationGroup:
    class_iri: str
    normalized_label: str
    canonical_iri: str
    duplicate_iris: tuple[str, ...]


class EntityResolver:
    """Resolve only exact normalized aliases; never guess from confidence."""

    def __init__(self, candidates: Iterable[EntityCandidate] = ()):
        self.candidates = tuple(candidates)
        self._index: dict[tuple[str, str], set[str]] = {}
        self._by_iri = {candidate.iri: candidate for candidate in self.candidates}
        for candidate in self.candidates:
            for label in candidate.labels():
                self._index.setdefault((normalize_mention(label), candidate.class_iri), set()).add(candidate.iri)

    @classmethod
    def from_mappings(cls, values: Iterable[Mapping[str, object]]) -> "EntityResolver":
        return cls(EntityCandidate(
            iri=str(value["iri"]), class_iri=str(value["class_iri"]),
            preferred_label=str(value["preferred_label"]),
            aliases=tuple(str(alias) for alias in value.get("aliases", ())),
        ) for value in values)

    def resolve(self, mention: str | None, class_iri: str | None) -> EntityResolution:
        if not mention or not class_iri:
            return EntityResolution(mention or "", None, class_iri, "unresolved")
        matches = self._index.get((normalize_mention(mention), class_iri), set())
        if len(matches) == 1:
            iri = next(iter(matches))
            return EntityResolution(mention, iri, class_iri, "resolved", (iri,))
        if len(matches) > 1:
            return EntityResolution(mention, None, class_iri, "ambiguous", tuple(sorted(matches)))
        return EntityResolution(mention, None, class_iri, "unresolved")

    def reconciliation_groups(self) -> tuple[ReconciliationGroup, ...]:
        """Return deterministic duplicate groups without mutating the catalog."""
        groups: dict[tuple[str, str], list[str]] = {}
        for candidate in self.candidates:
            key = (candidate.class_iri, normalize_mention(candidate.preferred_label))
            groups.setdefault(key, []).append(candidate.iri)
        return tuple(
            ReconciliationGroup(class_iri=class_iri, normalized_label=label,
                                canonical_iri=sorted(iris)[0], duplicate_iris=tuple(sorted(iris)[1:]))
            for (class_iri, label), iris in sorted(groups.items()) if len(set(iris)) > 1
        )


def resolver_from_neo4j(graph: object, limit: int = 10000) -> EntityResolver:
    """Load ontology-aware candidates from the existing ``__Entity__`` projection.

    Only entities carrying ``primary_class_iri`` are eligible. Legacy nodes
    without that additive property remain available to the old pipeline but
    are not guessed into ontology identities.
    """
    query = """
    MATCH (n:__Entity__)
    WHERE n.primary_class_iri IS NOT NULL AND n.id IS NOT NULL
    RETURN n.iri AS iri, n.primary_class_iri AS class_iri,
           coalesce(n.preferred_label, n.name, n.id) AS preferred_label,
           coalesce(n.aliases, []) AS aliases
    LIMIT $limit
    """
    try:
        rows = graph.query(query, {"limit": limit})
    except Exception:
        return EntityResolver()
    candidates = []
    for row in rows or []:
        values = dict(row)
        if values.get("iri") and values.get("class_iri") and values.get("preferred_label"):
            candidates.append(values)
    return EntityResolver.from_mappings(candidates)


def project_entity_metadata(graph: object, envelope: OntologyExtractionEnvelope) -> int:
    """Add ontology metadata to existing Neo4j entity nodes by their legacy id."""
    query = """
    MATCH (n:__Entity__ {id: $id})
    SET n.iri = $iri,
        n.primary_class_iri = $class_iri,
        n.ontology_layer = $layer,
        n.aliases = CASE WHEN $mention IS NULL THEN coalesce(n.aliases, [])
                         WHEN $mention IN coalesce(n.aliases, []) THEN coalesce(n.aliases, [])
                         ELSE coalesce(n.aliases, []) + $mention END
    """
    updates = 0
    seen: set[tuple[str, str]] = set()
    for assertion in envelope.assertions:
        for entity_id, iri, class_iri, mention in (
            (assertion.subject_mention, assertion.subject_iri, assertion.subject_class_iri, assertion.subject_mention),
            (assertion.object_mention, assertion.object_iri, assertion.object_class_iri, assertion.object_mention),
        ):
            if not entity_id or not iri or not class_iri or (entity_id, iri) in seen:
                continue
            seen.add((entity_id, iri))
            try:
                graph.query(query, {"id": entity_id, "iri": iri, "class_iri": class_iri,
                                    "layer": "domain", "mention": mention})
                updates += 1
            except Exception:
                continue
    return updates


def project_relationship_metadata(graph: object, graph_documents: list[object], envelope: OntologyExtractionEnvelope) -> int:
    """Add ontology and provenance properties to existing Neo4j relationships."""
    query = """
    MATCH (s:__Entity__ {id: $source_id})-[r]->(t:__Entity__ {id: $target_id})
    WHERE type(r) = $relationship_type
    SET r.predicate_iri = $predicate_iri,
        r.assertion_id = $assertion_id,
        r.validation_status = $validation_status,
        r.assertion_status = $assertion_status,
        r.source_document_id = $source_document_id,
        r.source_chunk_id = $source_chunk_id,
        r.evidence_span = $evidence_span,
        r.evidence_status = $evidence_status
    """
    by_key = {
        (item.subject_mention, item.predicate_iri, item.object_mention): item
        for item in envelope.assertions
    }
    updates = 0
    for document in graph_documents:
        for relationship in getattr(document, "relationships", ()) or ():
            source = str(getattr(relationship.source, "id", ""))
            target = str(getattr(relationship.target, "id", ""))
            predicate = str(getattr(relationship, "type", ""))
            assertion = by_key.get((source, predicate, target))
            if assertion is None:
                continue
            evidence = assertion.evidence
            params = {
                "source_id": source, "target_id": target, "relationship_type": predicate,
                "predicate_iri": assertion.predicate_iri, "assertion_id": assertion.assertion_id,
                "validation_status": assertion.validation_status, "assertion_status": assertion.assertion_status,
                "source_document_id": evidence.source_document_id if evidence else None,
                "source_chunk_id": evidence.source_chunk_id if evidence else None,
                "evidence_span": evidence.text_span if evidence else None,
                "evidence_status": evidence.evidence_status if evidence else "missing",
            }
            try:
                graph.query(query, params)
                updates += 1
            except Exception:
                continue
    return updates


def resolve_envelope(
    envelope: OntologyExtractionEnvelope, resolver: EntityResolver,
) -> tuple[OntologyExtractionEnvelope, dict[str, int]]:
    """Resolve subject/object mentions and quarantine only ambiguous matches."""
    resolved = ambiguous = unresolved = 0
    assertions: list[ExtractionAssertion] = []
    for assertion in envelope.assertions:
        subject = resolver.resolve(assertion.subject_mention, assertion.subject_class_iri)
        object_match = resolver.resolve(assertion.object_mention, assertion.object_class_iri)
        if subject.status == "resolved" and object_match.status in {"resolved", "unresolved"}:
            assertions.append(replace(assertion, subject_iri=subject.iri or assertion.subject_iri,
                                      object_iri=object_match.iri or assertion.object_iri))
            resolved += 1
        elif subject.status == "ambiguous" or object_match.status == "ambiguous":
            assertions.append(replace(assertion, assertion_status="quarantined", validation_status="quarantined"))
            ambiguous += 1
        else:
            assertions.append(assertion)
            unresolved += 1
    return replace(envelope, assertions=tuple(assertions)), {
        "resolved": resolved, "ambiguous": ambiguous, "unresolved": unresolved,
    }
