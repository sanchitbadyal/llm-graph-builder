"""Optional OWL reasoning through Owlready2 and HermiT."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

from rdflib import BNode, Graph, URIRef
from rdflib.namespace import OWL, RDFS

from .imports import LocalImportResolver
from .repository import OntologyRepository


def load_reasoning_closure(repository: OntologyRepository, root_id: str) -> tuple[Any, ...]:
    """Load the manifest-approved import closure from local files only."""
    from owlready2 import PREDEFINED_ONTOLOGIES, get_ontology

    if repository.manifest.source_path is None:
        raise ValueError("Manifest source path is required")
    closure = LocalImportResolver(repository).resolve(root_id)
    ontologies = []
    for artifact in closure.artifacts:
        path = artifact.resolved_path(repository.manifest.source_path)
        local_path = str(path.resolve())
        PREDEFINED_ONTOLOGIES[artifact.iri] = local_path
        PREDEFINED_ONTOLOGIES[f"{artifact.iri}/"] = local_path
        if artifact.version_iri:
            PREDEFINED_ONTOLOGIES[artifact.version_iri] = local_path
    for artifact in closure.artifacts:
        path = artifact.resolved_path(repository.manifest.source_path)
        ontologies.append(get_ontology(path.resolve().as_uri()).load(only_local=True))
    return tuple(ontologies)


def reason_over_ontology(repository: OntologyRepository, root_id: str):
    """Run HermiT over a local ontology closure and return its root ontology."""
    from owlready2 import sync_reasoner

    ontologies = load_reasoning_closure(repository, root_id)
    root = ontologies[0]
    with root:
        sync_reasoner(ontologies, infer_property_values=True, ignore_unsupported_datatypes=True)
    return root


def load_all_local_ontologies(repository: OntologyRepository) -> tuple[Any, ...]:
    """Load every local IOF and BFO RDF/OWL file into one Owlready2 world."""
    from owlready2 import PREDEFINED_ONTOLOGIES, World

    if repository.manifest.source_path is None:
        raise ValueError("Manifest source path is required")
    ontology_root = repository.manifest.source_path.parent / "ontologies"
    world = World()
    for artifact in repository.list_artifacts():
        path = artifact.resolved_path(repository.manifest.source_path)
        if path.exists():
            local_path = str(path)
            PREDEFINED_ONTOLOGIES[artifact.iri] = local_path
            PREDEFINED_ONTOLOGIES[f"{artifact.iri}/"] = local_path
            if artifact.version_iri:
                PREDEFINED_ONTOLOGIES[artifact.version_iri] = local_path

    ontologies = []
    for directory in (ontology_root / "iof", ontology_root / "bfo"):
        for path in sorted(directory.rglob("*.rdf")) + sorted(directory.rglob("*.owl")):
            try:
                ontologies.append(world.get_ontology(path.resolve().as_uri()).load(only_local=True))
            except Exception:
                continue
    return tuple(ontologies)


def reason_over_all_local_ontologies(repository: OntologyRepository) -> tuple[Any, ...]:
    """Run HermiT over all locally loaded IOF and BFO ontologies."""
    from owlready2 import sync_reasoner

    ontologies = load_all_local_ontologies(repository)
    if ontologies:
        sync_reasoner(ontologies, infer_property_values=True, ignore_unsupported_datatypes=True)
    return ontologies


@lru_cache(maxsize=1)
def _local_rdf_graph() -> tuple[Graph, dict[str, str]]:
    """Load all local RDF/OWL files without following remote imports."""
    ontology_root = Path(__file__).resolve().parents[1] / "Ontology" / "ontologies"
    graph = Graph()
    class_sources: dict[str, str] = {}
    for suffix in ("*.rdf", "*.owl", "*.ttl"):
        for path in sorted(ontology_root.rglob(suffix)):
            file_graph = Graph()
            file_graph.parse(path)
            graph += file_graph
            subjects = set(file_graph.subjects(RDFS.subClassOf, None))
            subjects.update(file_graph.subjects(RDFS.label, None))
            for subject in subjects:
                class_sources.setdefault(str(subject), path.stem)
    return graph, class_sources


def parent_relationships(class_iri: str) -> tuple[dict[str, str], ...]:
    """Return ordered root-to-class rdfs:subClassOf relationships."""
    graph, class_sources = _local_rdf_graph()
    def description(node: URIRef) -> str:
        values = list(graph.objects(node, RDFS.comment))
        values.extend(value for predicate, value in graph.predicate_objects(node)
                      if str(predicate).lower().endswith(('definition', 'definitiontext', 'description')))
        return next((str(value) for value in values if str(value).strip()), "")

    def named_parents(class_node: URIRef) -> tuple[str, ...]:
        parents: set[str] = set()
        expressions = list(graph.objects(class_node, RDFS.subClassOf))
        expressions.extend(graph.objects(class_node, OWL.equivalentClass))
        for parent in expressions:
            if isinstance(parent, URIRef):
                parents.add(str(parent))
                continue
            if not isinstance(parent, BNode):
                continue
            for intersection in graph.objects(parent, OWL.intersectionOf):
                for member in graph.items(intersection):
                    if isinstance(member, URIRef):
                        parents.add(str(member))
        return tuple(sorted(parents))

    current = URIRef(class_iri)
    chain: list[dict[str, str]] = []
    visited: set[URIRef] = set()
    while current not in visited:
        visited.add(current)
        parents = named_parents(current)
        if not parents:
            break
        parent = URIRef(parents[0])
        child_label = next((str(label) for label in graph.objects(current, RDFS.label)), str(current))
        parent_label = next((str(label) for label in graph.objects(parent, RDFS.label)), str(parent))
        chain.append({
            "child": str(current),
            "child_label": child_label,
            "child_profile": class_sources.get(str(current)),
            "relationship": "subClassOf",
            "parent": str(parent),
            "parent_label": parent_label,
            "parent_profile": class_sources.get(str(parent)),
            "child_description": description(current),
            "parent_description": description(parent),
        })
        current = parent
    return tuple(reversed(chain))


def ontology_catalog() -> tuple[dict[str, str], ...]:
    """Return all named local classes and their named superclass edges."""
    graph, class_sources = _local_rdf_graph()
    def description(node: URIRef) -> str:
        return next((str(value) for predicate, value in graph.predicate_objects(node)
                     if str(predicate).lower().endswith(('definition', 'definitiontext', 'description'))), "")
    classes = {subject for subject in graph.subjects(RDFS.label, None) if isinstance(subject, URIRef)}
    rows: list[dict[str, str]] = []
    for child in sorted(classes, key=str):
        label = next((str(value) for value in graph.objects(child, RDFS.label)), str(child))
        for parent in graph.objects(child, RDFS.subClassOf):
            named = [parent] if isinstance(parent, URIRef) else [
                member for collection in graph.objects(parent, OWL.intersectionOf)
                for member in graph.items(collection) if isinstance(member, URIRef)
            ]
            for parent_iri in named:
                rows.append({
                    "child_iri": str(child), "child_label": label,
                    "child_profile": class_sources.get(str(child), ""),
                    "child_description": description(child),
                    "parent_iri": str(parent_iri),
                    "parent_label": next((str(value) for value in graph.objects(parent_iri, RDFS.label)), str(parent_iri)),
                    "parent_profile": class_sources.get(str(parent_iri), ""),
                    "parent_description": description(parent_iri),
                })
    return tuple(rows)


def ontology_catalog_from_reasoner(ontologies: tuple[Any, ...]) -> tuple[dict[str, str], ...]:
    """Return all named classes and inferred named superclass edges from Owlready2."""
    if not ontologies:
        return ()
    graph, class_sources = _local_rdf_graph()
    def description(node: URIRef) -> str:
        values = list(graph.objects(node, RDFS.comment))
        values.extend(value for predicate, value in graph.predicate_objects(node)
                      if str(predicate).lower().endswith(('definition', 'definitiontext', 'description')))
        return next((str(value) for value in values if str(value).strip()), "")
    world = ontologies[0].world
    classes = tuple(world.classes())
    rows: list[dict[str, str]] = []
    for child in classes:
        child_iri = getattr(child, "iri", None)
        if not child_iri:
            continue
        child_label = child.label.first() if child.label else next(
            (str(value) for value in graph.objects(URIRef(child_iri), RDFS.label)), child.name
        )
        child_node = URIRef(str(child_iri))
        named_parents = [parent for parent in child.is_a if getattr(parent, "iri", None)
                         and getattr(parent, "iri", None) != "http://www.w3.org/2002/07/owl#Thing"]
        if not named_parents:
            child_node = URIRef(str(child_iri))
            for expression in graph.objects(child_node, OWL.equivalentClass):
                for collection in graph.objects(expression, OWL.intersectionOf):
                    named_parents.extend(
                        world[member] for member in graph.items(collection)
                        if isinstance(member, URIRef) and world[member] is not None
                    )
        if not named_parents:
            rows.append({
                "child_iri": str(child_iri), "child_label": str(child_label),
                "child_profile": class_sources.get(str(child_iri), ""),
                "child_description": description(child_node),
                "parent_iri": "", "parent_label": "", "parent_profile": "",
            })
        for parent in named_parents:
            parent_iri = getattr(parent, "iri", None)
            if not parent_iri or parent_iri == "http://www.w3.org/2002/07/owl#Thing":
                continue
            if str(parent_iri) == str(child_iri):
                continue
            parent_label = parent.label.first() if parent.label else next(
                (str(value) for value in graph.objects(URIRef(parent_iri), RDFS.label)), parent.name
            )
            rows.append({
                "child_iri": str(child_iri), "child_label": str(child_label),
                "child_profile": class_sources.get(str(child_iri), ""),
                "parent_iri": str(parent_iri), "parent_label": str(parent_label),
                "parent_profile": class_sources.get(str(parent_iri), ""),
                "child_description": description(child_node),
                "parent_description": description(URIRef(parent_iri)),
            })
    return tuple(rows)
