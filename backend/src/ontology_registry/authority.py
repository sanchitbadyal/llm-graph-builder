"""Phase 13 authority boundary between OWL identity and YAML operations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable


@dataclass(frozen=True)
class AuthorityPolicy:
    """Explicit ownership policy; it does not silently rewrite either source."""
    ontology_authority: tuple[str, ...] = ("class_identity", "property_identity", "hierarchy", "domain_range")
    yaml_authority: tuple[str, ...] = ("extraction_configuration", "business_rules", "kpis", "conflicts", "source_mappings")

    def as_dict(self) -> dict[str, list[str]]:
        return {"ontology": list(self.ontology_authority), "yaml": list(self.yaml_authority)}


@dataclass(frozen=True)
class AuthorityDrift:
    yaml_only: tuple[str, ...] = ()
    ontology_only: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, list[str]]:
        return {"yaml_only": list(self.yaml_only), "ontology_only": list(self.ontology_only)}


@dataclass(frozen=True)
class CompatibilityReport:
    manifest_version: str
    expected_version: str | None
    drift: AuthorityDrift
    compatible: bool
    errors: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {"manifest_version": self.manifest_version, "expected_version": self.expected_version,
                "compatible": self.compatible, "drift": self.drift.as_dict(), "errors": list(self.errors)}


@dataclass(frozen=True)
class IriMigration:
    old_iri: str
    new_iri: str
    reason: str
    status: str = "planned"


@dataclass(frozen=True)
class MigrationPlan:
    ontology_version: str
    migrations: tuple[IriMigration, ...] = ()


def compare_labels(yaml_labels: Iterable[str], ontology_labels: Iterable[str]) -> AuthorityDrift:
    yaml_set, ontology_set = {str(value) for value in yaml_labels}, {str(value) for value in ontology_labels}
    return AuthorityDrift(tuple(sorted(yaml_set - ontology_set)), tuple(sorted(ontology_set - yaml_set)))


def check_compatibility(manifest_version: str, yaml_labels: Iterable[str], ontology_labels: Iterable[str], *, expected_version: str | None = None, fail_on_drift: bool = False) -> CompatibilityReport:
    drift = compare_labels(yaml_labels, ontology_labels)
    errors: list[str] = []
    if expected_version and manifest_version != expected_version:
        errors.append(f"Ontology version {manifest_version} does not match expected {expected_version}")
    if fail_on_drift and (drift.yaml_only or drift.ontology_only):
        errors.append("OWL/YAML label drift detected")
    return CompatibilityReport(manifest_version, expected_version, drift, not errors, tuple(errors))


def build_migration_plan(ontology_version: str, mappings: Iterable[dict[str, str]]) -> MigrationPlan:
    migrations = tuple(IriMigration(str(item["old_iri"]), str(item["new_iri"]), str(item.get("reason", "ontology evolution"))) for item in mappings)
    if any(item.old_iri == item.new_iri for item in migrations):
        raise ValueError("IRI migration cannot map an IRI to itself")
    if len({item.old_iri for item in migrations}) != len(migrations):
        raise ValueError("IRI migration old_iri values must be unique")
    return MigrationPlan(ontology_version, migrations)
