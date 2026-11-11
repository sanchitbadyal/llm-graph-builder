import pytest
from src.ontology_registry import AuthorityPolicy, build_migration_plan, check_compatibility, compare_labels


def test_phase13_keeps_ontology_and_yaml_ownership_explicit():
    policy = AuthorityPolicy()
    assert "class_identity" in policy.ontology_authority
    assert "business_rules" in policy.yaml_authority


def test_phase13_reports_drift_without_rewriting_sources():
    drift = compare_labels(["Plant", "Order"], ["Plant", "Product"])
    assert drift.yaml_only == ("Order",)
    assert drift.ontology_only == ("Product",)


def test_phase13_checks_version_and_optional_drift_policy():
    report = check_compatibility("1.2.0", ["Plant"], ["Plant", "Product"], expected_version="1.1.0", fail_on_drift=True)
    assert report.compatible is False
    assert len(report.errors) == 2


def test_phase13_builds_non_destructive_iri_migration_plan():
    plan = build_migration_plan("1.2.0", [{"old_iri": "urn:old", "new_iri": "urn:new", "reason": "rename"}])
    assert plan.migrations[0].status == "planned"
    with pytest.raises(ValueError):
        build_migration_plan("1.2.0", [{"old_iri": "urn:same", "new_iri": "urn:same"}])
