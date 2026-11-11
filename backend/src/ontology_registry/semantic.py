"""Phase 2 semantic index and resolver for the local RDF/XML ontologies."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from xml.etree import ElementTree
import re

from .imports import LocalImportResolver
from .manifest import OntologyArtifact

RDF = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
OWL = "http://www.w3.org/2002/07/owl#"
RDFS = "http://www.w3.org/2000/01/rdf-schema#"


def _attr(namespace: str, name: str) -> str:
    return f"{{{namespace}}}{name}"


RDF_ABOUT = _attr(RDF, "about")
RDF_RESOURCE = _attr(RDF, "resource")


def _local_name(iri: str) -> str:
    return iri.rsplit("#", 1)[-1].rsplit("/", 1)[-1]


def _label_key(value: str) -> str:
    """Normalize human labels and OWL local names for tolerant lookup."""
    return re.sub(r"[^a-z0-9]", "", value.casefold())


def _values(element: ElementTree.Element, namespace: str, name: str) -> tuple[str, ...]:
    tag = _attr(namespace, name)
    return tuple(value for child in element.findall(tag) if (value := child.get(RDF_RESOURCE)))


def _labels(element: ElementTree.Element) -> tuple[str, ...]:
    return tuple(
        text.strip()
        for child in element.findall(_attr(RDFS, "label"))
        if (text := "".join(child.itertext()).strip())
    )


@dataclass(frozen=True)
class OntologyClass:
    iri: str
    labels: tuple[str, ...] = ()
    parents: tuple[str, ...] = ()
    layer: str | None = None
    ontology_id: str | None = None

    @property
    def preferred_label(self) -> str:
        return self.labels[0] if self.labels else _local_name(self.iri)


@dataclass(frozen=True)
class OntologyProperty:
    iri: str
    labels: tuple[str, ...] = ()
    domains: tuple[str, ...] = ()
    ranges: tuple[str, ...] = ()
    inverses: tuple[str, ...] = ()
    layer: str | None = None
    ontology_id: str | None = None

    @property
    def preferred_label(self) -> str:
        return self.labels[0] if self.labels else _local_name(self.iri)


@dataclass
class SemanticIndex:
    classes: dict[str, OntologyClass] = field(default_factory=dict)
    properties: dict[str, OntologyProperty] = field(default_factory=dict)
    _labels: dict[str, set[str]] = field(default_factory=dict)

    def add_class(self, value: OntologyClass) -> None:
        self.classes[value.iri] = value
        for label in (*value.labels, _local_name(value.iri)):
            self._labels.setdefault(_label_key(label), set()).add(value.iri)

    def add_property(self, value: OntologyProperty) -> None:
        self.properties[value.iri] = value
        for label in (*value.labels, _local_name(value.iri)):
            self._labels.setdefault(_label_key(label), set()).add(value.iri)


class SemanticResolver:
    """Resolve ontology terms and validate typed subject-predicate-object triples."""

    def __init__(self, index: SemanticIndex):
        self.index = index

    @classmethod
    def from_import_resolver(cls, resolver: LocalImportResolver, root_id: str) -> "SemanticResolver":
        index = SemanticIndex()
        manifest_path = resolver.repository.manifest.source_path
        if manifest_path is None:
            raise ValueError("Manifest source path is required")
        closure = resolver.resolve(root_id)
        for artifact in closure.artifacts:
            cls._parse_artifact(index, artifact, manifest_path)
        return cls(index)

    @staticmethod
    def _parse_artifact(index: SemanticIndex, artifact: OntologyArtifact, manifest_path: Path) -> None:
        root = ElementTree.parse(artifact.resolved_path(manifest_path)).getroot()
        class_tags = {_attr(OWL, "Class"), _attr(RDFS, "Class")}
        property_tags = {
            _attr(OWL, "ObjectProperty"),
            _attr(OWL, "DatatypeProperty"),
            _attr(RDF, "Property"),
        }
        for element in root.iter():
            iri = element.get(RDF_ABOUT)
            if not iri:
                continue
            if element.tag in class_tags:
                index.add_class(
                    OntologyClass(
                        iri=iri,
                        labels=_labels(element),
                        parents=_values(element, RDFS, "subClassOf"),
                        layer=artifact.layer,
                        ontology_id=artifact.id,
                    )
                )
            elif element.tag in property_tags:
                index.add_property(
                    OntologyProperty(
                        iri=iri,
                        labels=_labels(element),
                        domains=_values(element, RDFS, "domain"),
                        ranges=_values(element, RDFS, "range"),
                        inverses=_values(element, OWL, "inverseOf"),
                        layer=artifact.layer,
                        ontology_id=artifact.id,
                    )
                )

    def resolve_class(self, iri_or_label: str) -> OntologyClass:
        iri = self._resolve_iri(iri_or_label, self.index.classes)
        return self.index.classes[iri]

    def resolve_property(self, iri_or_label: str) -> OntologyProperty:
        iri = self._resolve_iri(iri_or_label, self.index.properties)
        return self.index.properties[iri]

    def _resolve_iri(self, value: str, values: dict[str, object]) -> str:
        if value in values:
            return value
        candidates = self.index._labels.get(_label_key(value), set()) & set(values)
        if len(candidates) > 1:
            domain_candidates = [
                iri for iri in candidates
                if getattr(values[iri], "layer", None) == "domain"
            ]
            if len(domain_candidates) == 1:
                return domain_candidates[0]
        if len(candidates) != 1:
            raise KeyError(f"Expected one ontology term for '{value}', found {sorted(candidates)}")
        return next(iter(candidates))

    def ancestors(self, class_iri_or_label: str) -> frozenset[str]:
        start = self.resolve_class(class_iri_or_label).iri
        result: set[str] = set()
        pending = [start]
        while pending:
            current = pending.pop()
            if current in result:
                continue
            result.add(current)
            current_class = self.index.classes.get(current)
            if current_class:
                pending.extend(current_class.parents)
        return frozenset(result)

    def inverse_properties(self, property_iri_or_label: str) -> frozenset[str]:
        prop = self.resolve_property(property_iri_or_label)
        result = set(prop.inverses)
        for candidate in self.index.properties.values():
            if prop.iri in candidate.inverses:
                result.add(candidate.iri)
        return frozenset(result)

    def compatible(self, subject_class: str, property_iri: str, object_class: str) -> bool:
        prop = self.resolve_property(property_iri)
        subject_types = self.ancestors(subject_class)
        object_types = self.ancestors(object_class)
        domain_ok = not prop.domains or bool(subject_types.intersection(prop.domains))
        range_ok = not prop.ranges or bool(object_types.intersection(prop.ranges))
        return domain_ok and range_ok

    def layer(self, iri_or_label: str) -> str | None:
        if iri_or_label in self.index.classes:
            return self.index.classes[iri_or_label].layer
        if iri_or_label in self.index.properties:
            return self.index.properties[iri_or_label].layer
        try:
            return self.resolve_class(iri_or_label).layer
        except KeyError:
            return self.resolve_property(iri_or_label).layer
