import json
from pathlib import Path

import pytest
import yaml

from src.ontology_registry.adapter import OntologyExtractionAdapter
from src.ontology_registry.graph_document import _class_iri, _property_iri


ROOT = Path(__file__).parents[1]
ONTOLOGY_ROOT = ROOT / "backend/src/Ontology"
MANIFEST = ONTOLOGY_ROOT / "manifest.yaml"


def _yaml_classes(path: Path) -> set[str]:
    profile = yaml.safe_load(path.read_text(encoding="utf-8"))
    return {
        entry["label"]
        for entries in profile["groups"].values()
        for entry in entries
    }


def test_business_context_uses_yaml_classes_and_relationship_rules():
    profile = OntologyExtractionAdapter(MANIFEST).build()
    context = json.loads(profile.prompt_context.split("\n", 1)[1])

    assert set(profile.allowed_nodes) == _yaml_classes(ONTOLOGY_ROOT / "profiles/business.yaml")
    assert len(profile.allowed_nodes) == 11
    assert len(context["properties"]) >= 20
    assert ("Organization", "has position", "Position") in profile.allowed_relationships
    assert any(
        item == "has business role"
        or (isinstance(item, tuple) and item[1] == "has business role")
        for item in profile.allowed_relationships
    )
    assert _class_iri(profile, "Organization") == "http://example.org/ontology/business#Organization"
    assert _property_iri(profile, "has position") == "http://example.org/ontology/business#hasPosition"
    assert all(item["iri"].startswith("http://") for item in context["classes"])
    assert {item["label"] for item in context["classes"]} == set(profile.allowed_nodes)
    assert "Manufactured Product" not in profile.allowed_nodes


def test_standalone_profile_context_does_not_require_owl_resolution():
    profile = OntologyExtractionAdapter(MANIFEST, "maintenance-complete").build()

    assert set(profile.allowed_nodes) == _yaml_classes(ONTOLOGY_ROOT / "profiles/Industrial_Ontologies_Foundry/maintenance.yaml")





def test_manufacturing_root_requires_a_yaml_profile():
    with pytest.raises(ValueError, match="No YAML ontology profile configured"):
        OntologyExtractionAdapter(MANIFEST, "manufacturing")
