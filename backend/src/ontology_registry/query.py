"""Ontology-aware query expansion and evidence filtering helpers."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

from .semantic import SemanticResolver


@dataclass(frozen=True)
class OntologyQueryPlan:
    question: str
    class_iris: tuple[str, ...] = ()
    property_iris: tuple[str, ...] = ()
    expanded_terms: tuple[str, ...] = ()
    cypher_predicate: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {"question": self.question, "class_iris": list(self.class_iris),
                "property_iris": list(self.property_iris), "expanded_terms": list(self.expanded_terms),
                "cypher_predicate": self.cypher_predicate}


class OntologyQueryPlanner:
    def __init__(self, resolver: SemanticResolver):
        self.resolver = resolver

    def plan(self, question: str) -> OntologyQueryPlan:
        tokens = {token.rstrip("s") for token in re.findall(r"[a-zA-Z][\w-]*", question.casefold())}
        classes = [item for item in self.resolver.index.classes.values()
                   if any(token.rstrip("s") in {part.rstrip("s") for part in item.preferred_label.casefold().split()} for token in tokens)]
        properties = [item for item in self.resolver.index.properties.values()
                      if any(token.rstrip("s") in {part.rstrip("s") for part in item.preferred_label.casefold().split()} for token in tokens)]
        class_iris = tuple(sorted(item.iri for item in classes))
        property_iris = tuple(sorted(item.iri for item in properties))
        expanded = tuple(sorted({item.preferred_label for item in (*classes, *properties)}))
        predicate = "r.validation_status IN ['valid'] AND coalesce(r.assertion_status, 'explicit') <> 'rejected'"
        return OntologyQueryPlan(question, class_iris, property_iris, expanded, predicate)


def ontology_answering_context(plan: OntologyQueryPlan) -> str:
    return (
        "Ontology-aware answer policy:\n"
        "Use only retrieved assertions whose validation_status is valid. "
        "Label answers as explicit or inferred; do not present quarantined or rejected assertions. "
        "Cite source chunks and evidence spans when available.\n"
        f"Ontology query plan: {plan.as_dict()}"
    )
