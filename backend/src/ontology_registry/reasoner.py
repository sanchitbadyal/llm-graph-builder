"""Optional OWL reasoning through Owlready2 and HermiT."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .imports import LocalImportResolver
from .repository import OntologyRepository


def load_reasoning_closure(repository: OntologyRepository, root_id: str) -> tuple[Any, ...]:
    """Load the manifest-approved import closure from local files only."""
    try:
        from owlready2 import PREDEFINED_ONTOLOGIES, get_ontology
    except ImportError as exc:
        raise RuntimeError(
            "Owlready2 is optional. Install it with "
            "'backend/venv/bin/pip install owlready2' before using the reasoner."
        ) from exc
    if repository.manifest.source_path is None:
        raise ValueError("Manifest source path is required")

    closure = LocalImportResolver(repository).resolve(root_id)
    ontologies = []
    # Register the complete closure before loading any file, because Owlready2
    # resolves owl:imports recursively while the root document is parsed.
    for artifact in closure.artifacts:
        path = artifact.resolved_path(repository.manifest.source_path)
        local_path = str(path.resolve())
        # Owlready2 otherwise tries to download example.org / BFO imports.
        # Bind every approved ontology IRI to its manifest-approved local file.
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
    try:
        from owlready2 import sync_reasoner
    except ImportError as exc:
        raise RuntimeError(
            "Owlready2 is optional. Install it with "
            "'backend/venv/bin/pip install owlready2' before using the reasoner."
        ) from exc
    ontologies = load_reasoning_closure(repository, root_id)
    root = ontologies[0]
    with root:
        sync_reasoner(
            ontologies,
            infer_property_values=True,
            ignore_unsupported_datatypes=True,
        )
    return root
