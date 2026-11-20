from pathlib import Path

import pytest

from src.ontology_registry.adapter import (
    ALWAYS_LOADED,
    OntologyExtractionAdapter,
    PROFILE_IMPORTS,
    YAML_PROFILE_FILES,
    resolve_profile_closure,
)


MANIFEST = Path(__file__).parents[1] / "backend" / "src" / "Ontology" / "manifest.yaml"


def test_empty_selection_loads_core_and_annotation_vocabulary():
    profile = OntologyExtractionAdapter.build_selected(MANIFEST, [])
    assert profile.ontology_id == "core-selected,annotation-vocabulary-selected"


def test_manufacturing_execution_resolves_transitive_dependencies():
    selected = resolve_profile_closure(
        ("core-selected", "annotation-vocabulary-selected", "biopharma-manufacturing-execution-complete")
    )
    assert selected == (
        "core-selected",
        "annotation-vocabulary-selected",
        "biopharma-manufacturing-system-organization-complete",
        "reference-ontology-candidates-complete",
        "biopharma-recipe-complete",
        "biopharma-reference-ontology-attributes-complete",
        "molecular-entity-complete",
        "biopharma-material-complete",
        "targets-limits-ranges-complete",
        "biopharma-parameter-complete",
        "biopharma-monitoring-and-control-complete",
        "biopharma-equipment-complete",
        "biopharma-manufacturing-execution-complete",
    )


def test_circular_dependency_raises_value_error(monkeypatch):
    monkeypatch.setitem(PROFILE_IMPORTS, "core-selected", ("annotation-vocabulary-selected",))
    monkeypatch.setitem(PROFILE_IMPORTS, "annotation-vocabulary-selected", ("core-selected",))
    with pytest.raises(ValueError, match="core-selected -> annotation-vocabulary-selected -> core-selected"):
        resolve_profile_closure(("core-selected",))


def test_unknown_profile_raises_value_error():
    with pytest.raises(ValueError, match="Unknown ontology profile"):
        resolve_profile_closure(("does-not-exist",))


def test_resolved_profiles_are_unique():
    selected = resolve_profile_closure(("recipe-ontology-complete", "biopharma-recipe-complete"))
    assert len(selected) == len(set(selected))
