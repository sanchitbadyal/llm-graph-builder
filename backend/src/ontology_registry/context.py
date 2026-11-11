"""Build compact, deterministic ontology context for LLM extraction prompts."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Iterable

from .imports import LocalImportResolver
from .semantic import OntologyClass, OntologyProperty, SemanticResolver


@dataclass(frozen=True)
class OntologyContext:
    """Prompt-safe projection of the active ontology profile."""

    ontology_id: str
    classes: tuple[dict[str, Any], ...]
    properties: tuple[dict[str, Any], ...]
    instructions: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "ontology_id": self.ontology_id,
            "classes": list(self.classes),
            "properties": list(self.properties),
            "instructions": list(self.instructions),
        }

    def to_prompt(self) -> str:
        payload = json.dumps(self.as_dict(), ensure_ascii=False, separators=(",", ":"))
        return "Ontology extraction context (JSON; treat as an allowlist):\n" + payload

    def to_human_prompt(self) -> str:
        lines = [
            "Ontology extraction allowlist (use only these classes and properties):",
            "",
            "Classes:",
        ]
        for item in self.classes:
            lines.extend([
                f"- {item['label']} [IRI: {item['iri']}; layer: {item.get('layer')}].",
                f"  Parents: {', '.join(item.get('parents', [])) or '(none)' }.",
                f"  Ancestors: {', '.join(item.get('ancestors', [])) or '(none)' }.",
            ])
            if item.get("definition"):
                lines.append(f"  Definition: {item['definition']}")
        lines.append("Properties:")
        for item in self.properties:
            lines.extend([
                f"- {item['label']} [IRI: {item['iri']}; layer: {item.get('layer')}].",
                f"  Domain: {', '.join(item.get('domain', [])) or '(unrestricted)' }.",
                f"  Range: {', '.join(item.get('range', [])) or '(unrestricted)' }.",
                f"  Inverses: {', '.join(item.get('inverses', [])) or '(none)' }.",
            ])
            if item.get("definition"):
                lines.append(f"  Definition: {item['definition']}")
        lines.extend(["", "Instructions:", *[f"- {item}" for item in self.instructions]])
        return "\n".join(lines)


class OntologyContextBuilder:
    """Create an extraction context from a Phase 2 semantic resolver."""

    DEFAULT_INSTRUCTIONS = (
        "Use only classes and properties in this context.",
        "Return canonical IRIs exactly as provided; never invent ontology terms.",
        "Use domain and range restrictions to validate candidate relationships.",
        "Distinguish explicit source statements from inferred or unresolved candidates.",
        "Do not treat model confidence as factual proof.",
    )

    def __init__(self, resolver: SemanticResolver):
        self.resolver = resolver

    @classmethod
    def from_import_resolver(cls, resolver: LocalImportResolver, root_id: str) -> "OntologyContextBuilder":
        return cls(SemanticResolver.from_import_resolver(resolver, root_id))

    def build(
        self,
        ontology_id: str,
        *,
        layers: Iterable[str] | None = None,
        class_iris: Iterable[str] | None = None,
        include_partial_relationships: bool = False,
    ) -> OntologyContext:
        allowed_layers = set(layers) if layers is not None else None
        requested_classes = set(class_iris) if class_iris is not None else None
        classes = [
            value for value in self.resolver.index.classes.values()
            if (allowed_layers is None or value.layer in allowed_layers)
            and (requested_classes is None or value.iri in requested_classes)
        ]
        class_ids = {value.iri for value in classes}
        properties = [
            value for value in self.resolver.index.properties.values()
            if (allowed_layers is None or value.layer in allowed_layers)
            and (
                not class_ids
                or (
                    any(item in class_ids for item in value.domains)
                    and any(item in class_ids for item in value.ranges)
                )
                or (
                    include_partial_relationships
                    and (
                        any(item in class_ids for item in value.domains)
                        or any(item in class_ids for item in value.ranges)
                    )
                )
            )
        ]
        return OntologyContext(
            ontology_id=ontology_id,
            classes=tuple(self._class_payload(value) for value in sorted(classes, key=lambda item: item.iri)),
            properties=tuple(
                self._property_payload(value, class_ids)
                for value in sorted(properties, key=lambda item: item.iri)
            ),
            instructions=self.DEFAULT_INSTRUCTIONS,
        )

    def _class_payload(self, value: OntologyClass) -> dict[str, Any]:
        return {
            "iri": value.iri,
            "label": value.preferred_label,
            "labels": list(value.labels),
            "parents": sorted(value.parents),
            "ancestors": sorted(self.resolver.ancestors(value.iri)),
            "layer": value.layer,
        }

    def _property_payload(self, value: OntologyProperty, class_ids: set[str]) -> dict[str, Any]:
        return {
            "iri": value.iri,
            "label": value.preferred_label,
            "labels": list(value.labels),
            "domain": sorted(value.domains),
            "range": sorted(value.ranges),
            "inverses": sorted(value.inverses),
            "layer": value.layer,
            "usable_with_context_classes": bool(
                not class_ids or any(item in class_ids for item in (*value.domains, *value.ranges))
            ),
        }
