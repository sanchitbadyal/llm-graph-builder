"""Local ontology repository backed by a validated manifest."""

from __future__ import annotations

from pathlib import Path

from .manifest import OntologyArtifact, OntologyManifest, load_manifest


class OntologyRepository:
    """Discover approved ontology artifacts without resolving imports yet."""

    def __init__(self, manifest: OntologyManifest):
        self.manifest = manifest

    @classmethod
    def from_manifest(cls, path: str | Path) -> "OntologyRepository":
        return cls(load_manifest(path))

    def get(self, artifact_id: str) -> OntologyArtifact:
        return self.manifest.by_id(artifact_id)

    def list_artifacts(self) -> tuple[OntologyArtifact, ...]:
        return self.manifest.artifacts

    def imports_for(self, artifact_id: str) -> tuple[str, ...]:
        return self.manifest.import_ids(artifact_id)

    def verify_artifact(self, artifact_id: str) -> bool:
        artifact = self.get(artifact_id)
        if self.manifest.source_path is None:
            raise ValueError("Manifest source path is required for artifact verification")
        return artifact.verify_checksum(self.manifest.source_path)
