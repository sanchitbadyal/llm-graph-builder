from src.ontology_registry import validate_with_optional_profile


def test_ontology_only_profile_validation_has_no_yaml_dependency():
    documents, report = validate_with_optional_profile(["document"])
    assert documents == ["document"]
    assert report["profile_validation"] == "not_configured"


def test_optional_profile_validator_can_add_deployment_rules():
    class Validator:
        def validate(self, documents):
            return documents, {"profile_validation": "custom", "violations": []}
    _, report = validate_with_optional_profile([], Validator())
    assert report["profile_validation"] == "custom"
