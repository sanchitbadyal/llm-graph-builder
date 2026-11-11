"""Reproducible local resolution of RDF/XML ``owl:imports`` declarations."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree

from .manifest import OntologyArtifact
from .repository import OntologyRepository

OWL_IMPORTS = "{http://www.w3.org/2002/07/owl#}imports"


class ImportResolutionError(ValueError):
    """Raised when an ontology import cannot be resolved locally."""


@dataclass(frozen=True)
class ResolvedImportClosure:
    """Ordered root-first import closure for one ontology artifact."""

    root: str
    artifacts: tuple[OntologyArtifact, ...]

    @property
    def artifact_ids(self) -> tuple[str, ...]:
        return tuple(artifact.id for artifact in self.artifacts)


class LocalImportResolver:
    """Resolve imports only through the approved local ontology manifest."""

    def __init__(self, repository: OntologyRepository):
        self.repository = repository

    def declared_imports(self, artifact_id: str) -> tuple[str, ...]:
        """Read import IRIs directly from the artifact's RDF/XML bytes."""
        artifact = self.repository.get(artifact_id)
        manifest_path = self.repository.manifest.source_path
        if manifest_path is None:
            raise ImportResolutionError("Manifest source path is required")
        try:
            root = ElementTree.parse(artifact.resolved_path(manifest_path)).getroot()
        except (OSError, ElementTree.ParseError) as exc:
            raise ImportResolutionError(f"Cannot parse ontology '{artifact_id}': {exc}") from exc
        return tuple(
            value
            for node in root.iter(OWL_IMPORTS)
            if (value := node.attrib.get("{http://www.w3.org/1999/02/22-rdf-syntax-ns#}resource"))
        )

    def validate_manifest_declarations(self, artifact_id: str) -> None:
        """Ensure manifest imports agree with the artifact's declared imports."""
        artifact = self.repository.get(artifact_id)
        declared = set(self.declared_imports(artifact_id))
        cataloged = set(artifact.imports)
        if declared != cataloged:
            raise ImportResolutionError(
                f"Import mismatch for '{artifact_id}': declared={sorted(declared)}, "
                f"manifest={sorted(cataloged)}"
            )

    def resolve(self, root_id: str) -> ResolvedImportClosure:
        """Resolve a root artifact and all local imports, root first."""
        ordered: list[OntologyArtifact] = []
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(artifact_id: str) -> None:
            if artifact_id in visiting:
                raise ImportResolutionError(f"Circular ontology import detected at '{artifact_id}'")
            if artifact_id in visited:
                return
            artifact = self.repository.get(artifact_id)
            if not self.repository.verify_artifact(artifact_id):
                raise ImportResolutionError(f"Checksum verification failed for '{artifact_id}'")
            self.validate_manifest_declarations(artifact_id)
            visiting.add(artifact_id)
            ordered.append(artifact)
            for imported_iri in artifact.imports:
                try:
                    imported = self.repository.manifest.by_iri(imported_iri)
                except KeyError as exc:
                    raise ImportResolutionError(
                        f"Import '{imported_iri}' from '{artifact_id}' is not in the local catalog"
                    ) from exc
                visit(imported.id)
            visiting.remove(artifact_id)
            visited.add(artifact_id)

        visit(root_id)
        return ResolvedImportClosure(root=root_id, artifacts=tuple(ordered))
