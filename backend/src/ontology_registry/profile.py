"""Optional deployment-profile hooks for non-ontology operational rules."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


class ProfileValidator(Protocol):
    def validate(self, graph_documents: list[Any]) -> tuple[list[Any], dict[str, Any]]: ...


@dataclass(frozen=True)
class NoOpProfileValidator:
    """Default validator for ontology-only deployments."""

    def validate(self, graph_documents: list[Any]) -> tuple[list[Any], dict[str, Any]]:
        return graph_documents, {"profile_validation": "not_configured", "violations": []}


def validate_with_optional_profile(
    graph_documents: list[Any], validator: ProfileValidator | None = None,
) -> tuple[list[Any], dict[str, Any]]:
    """Run an optional deployment validator without importing company YAML."""
    return (validator or NoOpProfileValidator()).validate(graph_documents)
