from pathlib import Path

import yaml

from src.ontology_registry import OntologyExtractionAdapter


ROOT = Path(__file__).parents[1]
PROFILE = ROOT / "backend/src/Ontology/profiles/business.yaml"
MANIFEST = ROOT / "backend/src/Ontology/manifest.yaml"


def test_selected_business_core_profile_contains_67_classes_and_is_loadable():
    profile = yaml.safe_load(PROFILE.read_text(encoding="utf-8"))
    labels = [entry["label"] for values in profile["groups"].values() for entry in values]
    built = OntologyExtractionAdapter.build_selected(MANIFEST, [])

    assert len(labels) == 67
    assert len(set(labels)) == 67
    assert set(built.allowed_nodes) == set(labels) | {
        entry["label"]
        for values in yaml.safe_load((ROOT / "backend/src/Ontology/profiles/core.yaml").read_text())["groups"].values()
        for entry in values
    }
    assert "has position" in {item["label"] for item in profile["relationships"]}
    assert "has discount approval" in {item["label"] for item in profile["relationships"]}
    assert profile["profile"]["include_ancestors"] is True
    assert profile["profile"]["include_compatible_properties"] is True
