import hashlib
import json
from pathlib import Path

import yaml

from src.ontology_registry import OntologyExtractionAdapter


ROOT = Path(__file__).parents[1]
PROFILES_DIR = ROOT / "backend/src/Ontology/profiles"
PROFILE = PROFILES_DIR / "business.yaml"
MANIFEST = ROOT / "backend/src/Ontology/manifest.yaml"
OPTIONAL_BUSINESS_PROFILE_IDS = (
    "business-order-to-cash",
    "business-procurement-supplier-management",
    "business-fulfillment-logistics",
    "business-revenue-accounting",
    "business-governance-risk-compliance",
    "business-products-inventory",
)


def _business_profile_data():
    profiles = [
        yaml.safe_load(path.read_text(encoding="utf-8"))
        for path in sorted(PROFILES_DIR.glob("business*.yaml"))
    ]
    classes = {
        entry["label"]: entry
        for profile in profiles
        for values in profile["groups"].values()
        for entry in values
    }
    relationships = {
        entry["type"]: entry
        for profile in profiles
        for entry in profile.get("relationships", [])
    }
    return profiles, classes, relationships


def test_business_profiles_preserve_all_67_classes_and_64_relationships():
    profiles, classes, relationships = _business_profile_data()
    common = yaml.safe_load(PROFILE.read_text(encoding="utf-8"))
    common_labels = {
        entry["label"]
        for values in common["groups"].values()
        for entry in values
    }
    built = OntologyExtractionAdapter.build_selected(
        MANIFEST, OPTIONAL_BUSINESS_PROFILE_IDS
    )

    assert len(classes) == 67
    assert len(relationships) == 64
    assert hashlib.sha256(
        json.dumps(classes, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest() == "371d7da4735f8c1f2938a871ae5d488de24fdb78fa2ea7e417578b92c3dd2091"
    assert hashlib.sha256(
        json.dumps(relationships, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest() == "35d392c2712d6e7293a13099be20dabe0f78f349e1e7407ff11e0cb992a79fa2"
    assert len(classes) == sum(
        len(entries)
        for profile in profiles
        for entries in profile["groups"].values()
    )
    assert len(relationships) == sum(
        len(profile.get("relationships", [])) for profile in profiles
    )
    assert set(built.allowed_nodes) == set(classes) | {
        entry["label"]
        for values in yaml.safe_load((ROOT / "backend/src/Ontology/profiles/Industrial_Ontologies_Foundry/core.yaml").read_text())["groups"].values()
        for entry in values
    }
    relationship_labels = {
        item if isinstance(item, str) else item[1]
        for item in built.allowed_relationships
    }
    business_relationship_labels = {
        item["label"]
        for profile in profiles
        for item in profile.get("relationships", [])
    }
    core = yaml.safe_load(
        (ROOT / "backend/src/Ontology/profiles/Industrial_Ontologies_Foundry/core.yaml").read_text()
    )
    core_relationship_labels = {
        item["label"] for item in core.get("relationships", [])
    }
    assert business_relationship_labels <= relationship_labels
    assert relationship_labels <= business_relationship_labels | core_relationship_labels
    assert "has position" in {
        relationship["label"] for relationship in relationships.values()
    }
    assert "HAS_DISCOUNT_APPROVAL" in relationships
    assert common["profile"]["id"] == "business-common"
    assert len(common_labels) == 11
    assert common["profile"]["include_ancestors"] is True
    assert common["profile"]["include_compatible_properties"] is True


def test_optional_product_profile_filters_relationship_endpoints_to_loaded_classes():
    built = OntologyExtractionAdapter.build_selected(
        MANIFEST, ["business-products-inventory"]
    )

    assert ("Packaged Unit", "stored at", "Warehouse") in built.allowed_relationships
    assert ("Packaged Unit", "stored at", "Plant") not in built.allowed_relationships
    assert "label: Sales Order" not in built.yaml_context
    assert "range: [Warehouse]" in built.yaml_context
    assert "range: [Warehouse, Plant]" not in built.yaml_context


def test_default_selection_loads_business_common_and_core_only():
    built = OntologyExtractionAdapter.build_selected(MANIFEST, [])
    common = yaml.safe_load(PROFILE.read_text(encoding="utf-8"))
    core = yaml.safe_load(
        (ROOT / "backend/src/Ontology/profiles/Industrial_Ontologies_Foundry/core.yaml").read_text()
    )
    expected_nodes = {
        entry["label"]
        for profile in (common, core)
        for entries in profile["groups"].values()
        for entry in entries
    }

    assert set(built.allowed_nodes) == expected_nodes
    assert {"Sales Order", "Shipment", "Revenue Entry"}.isdisjoint(
        built.allowed_nodes
    )
    assert "Non-Conformance Record" not in built.allowed_nodes
    assert "has customer" not in {
        item if isinstance(item, str) else item[1]
        for item in built.allowed_relationships
    }
