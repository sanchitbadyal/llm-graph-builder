"""Typed loading and validation for the ontology release manifest."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

import yaml


class ManifestError(ValueError):
    """Raised when an ontology manifest is malformed or unsafe."""


@dataclass(frozen=True)
class OntologyArtifact:
    """A versioned ontology artifact known to the local catalog."""

    id: str
    iri: str
    path: Path
    version: str | None = None
    version_iri: str | None = None
    imports: tuple[str, ...] = ()
    checksum: str | None = None
    media_type: str | None = None
    layer: str | None = None

    def resolved_path(self, manifest_path: Path) -> Path:
        path = self.path if self.path.is_absolute() else manifest_path.parent / self.path
        return path.resolve()

    def sha256(self, manifest_path: Path) -> str:
        digest = hashlib.sha256()
        with self.resolved_path(manifest_path).open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest()

    def verify_checksum(self, manifest_path: Path) -> bool:
        if not self.checksum:
            return True
        expected = self.checksum.removeprefix("sha256:").lower()
        return self.sha256(manifest_path).lower() == expected


@dataclass(frozen=True)
class OntologyManifest:
    """Catalog of approved ontology artifacts and their import identities."""

    id: str
    version: str
    artifacts: tuple[OntologyArtifact, ...]
    default_profile: str | None = None
    source_path: Path | None = field(default=None, compare=False)

    def by_id(self, artifact_id: str) -> OntologyArtifact:
        for artifact in self.artifacts:
            if artifact.id == artifact_id:
                return artifact
        raise KeyError(f"Unknown ontology artifact: {artifact_id}")

    def by_iri(self, iri: str) -> OntologyArtifact:
        for artifact in self.artifacts:
            if artifact.iri == iri or artifact.version_iri == iri:
                return artifact
        raise KeyError(f"Unknown ontology IRI: {iri}")

    def import_ids(self, artifact_id: str) -> tuple[str, ...]:
        artifact = self.by_id(artifact_id)
        resolved: list[str] = []
        for imported_iri in artifact.imports:
            try:
                resolved.append(self.by_iri(imported_iri).id)
            except KeyError:
                continue
        return tuple(resolved)


def _require_text(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ManifestError(f"Manifest field '{field_name}' must be a non-empty string")
    return value.strip()


def _artifact(raw: Mapping[str, Any], manifest_path: Path) -> OntologyArtifact:
    artifact_id = _require_text(raw.get("id"), "artifacts[].id")
    iri = _require_text(raw.get("iri"), f"artifacts[{artifact_id}].iri")
    raw_path = _require_text(raw.get("path"), f"artifacts[{artifact_id}].path")
    path = Path(raw_path)
    resolved = (manifest_path.parent / path).resolve() if not path.is_absolute() else path.resolve()
    if not resolved.is_file():
        raise ManifestError(f"Ontology artifact does not exist: {resolved}")
    imports = raw.get("imports") or []
    if not isinstance(imports, list) or not all(isinstance(item, str) and item.strip() for item in imports):
        raise ManifestError(f"Manifest field 'artifacts[{artifact_id}].imports' must be a list of IRIs")
    return OntologyArtifact(
        id=artifact_id,
        iri=iri,
        path=path,
        version=raw.get("version"),
        version_iri=raw.get("version_iri"),
        imports=tuple(item.strip() for item in imports),
        checksum=raw.get("checksum"),
        media_type=raw.get("media_type"),
        layer=raw.get("layer"),
    )


def load_manifest(path: str | Path) -> OntologyManifest:
    """Load and validate an ontology manifest from YAML."""
    manifest_path = Path(path).expanduser().resolve()
    with manifest_path.open("r", encoding="utf-8") as stream:
        raw = yaml.safe_load(stream) or {}
    if not isinstance(raw, Mapping):
        raise ManifestError("Ontology manifest root must be a mapping")
    metadata = raw.get("manifest") or {}
    if not isinstance(metadata, Mapping):
        raise ManifestError("Manifest field 'manifest' must be a mapping")
    manifest_id = _require_text(metadata.get("id"), "manifest.id")
    version = _require_text(metadata.get("version"), "manifest.version")
    raw_artifacts = raw.get("artifacts") or []
    if not isinstance(raw_artifacts, list) or not raw_artifacts:
        raise ManifestError("Manifest must define at least one artifact")
    artifacts = tuple(_artifact(item, manifest_path) for item in raw_artifacts)
    ids = [item.id for item in artifacts]
    iris = [item.iri for item in artifacts]
    if len(set(ids)) != len(ids):
        raise ManifestError("Ontology artifact IDs must be unique")
    if len(set(iris)) != len(iris):
        raise ManifestError("Ontology artifact IRIs must be unique")
    return OntologyManifest(
        id=manifest_id,
        version=version,
        artifacts=artifacts,
        default_profile=metadata.get("default_profile"),
        source_path=manifest_path,
    )
