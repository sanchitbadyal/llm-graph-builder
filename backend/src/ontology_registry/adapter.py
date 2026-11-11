"""Opt-in adapter from YAML ontology profiles to LangChain graph-transformer inputs."""

from __future__ import annotations

import os
import re
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import yaml

from .context import OntologyContext, OntologyContextBuilder
from .imports import LocalImportResolver
from .repository import OntologyRepository
from .semantic import SemanticResolver, _label_key


class _ExpandedYamlDumper(yaml.SafeDumper):
    def ignore_aliases(self, data):
        return True


YAML_PROFILE_FILES = {
    "business-core-selected": ("business.yaml",),
    "core-selected": ("core.yaml",),
    "production-planning-complete": ("production.yaml",),
    "maintenance-complete": ("maintenance.yaml",),
    "certification-complete": ("certification.yaml",),
    "manufacturing-system-organization-complete": ("manufacturing_system_organiztion.yaml",),
}

PROFILE_DESCRIPTIONS = {
    "production-planning-complete": (
        "Select ONLY when the document describes how production is planned and executed: "
        "production plans and production orders (what to make and how much), process plans, "
        "manufacturing operations and process steps, changeovers, inspection plans for products, "
        "material handling plans, work-in-progress transfers, machines, tools and operators. "
        "Do NOT select for sales orders, purchase orders, shipping, invoicing or revenue; "
        "'order' alone is not a reason to select it."
    ),
    "maintenance-complete": (
        "Select ONLY when the document describes keeping equipment working: failures and failure "
        "modes, failure effects, operating, degraded and failed states, maintenance strategies, "
        "maintenance work order records, maintenance activities and qualified maintenance staff. "
        "Do NOT select for product quality inspection, production runs or accounting."
    ),
    "certification-complete": (
        "Select ONLY when the document describes verifying something against a standard and "
        "issuing a certificate: attesting (verification) processes, certificates, certifying "
        "bodies and the agents who attest for them. "
        "Do NOT select for internal approvals, credit checks, audits of records, or ordinary "
        "business documents such as invoices and delivery notes."
    ),
    "manufacturing-system-organization-complete": (
        "Select ONLY when the document describes the physical structure of a manufacturing "
        "enterprise: enterprise, physical sites and areas, work centers, work cells, production "
        "lines, production units, process cells, storage zones and units, equipment and control "
        "modules. "
        "Do NOT select for departments, cost centers, legal entities or reporting lines; "
        "those are in the business profile."
    ),
}


ALWAYS_LOADED = ["business-core-selected", "core-selected"]

DEFAULT_PROFILE_NOTES = {
    "business-core-selected": (
        "Always loaded. Organizations, units, cost centers, positions, roles, documents, "
        "order-to-cash, plant fulfillment, revenue recognition, approvals, accounting, "
        "business rules and policies."
    ),
    "core-selected": (
        "Always loaded. Generic industrial concepts: agents, material artifacts, equipment, "
        "planned processes, roles, capabilities and measurement."
    ),
}

BASE_PROFILE_IDS = tuple(ALWAYS_LOADED)

# The prompt uses one canonical direction for these inverse predicates.  The
# complete relationship allowlist remains available to the transformer.
INVERSE_RELATIONSHIP_PAIRS = {
    "account posting of": "posted to account",
    "position in": "has position",
    "sub-unit of": "has sub-unit",
    "governs": "governed by",
    "step of": "has step",
    "assessment of": "has assessment",
    "role of": "has business role",
    "sells to": "buys from",
    "supplies": "supplied by",
}

def _yaml_entries(profile: dict, key: str) -> Iterable[tuple[str, dict]]:
    for group_name, entries in profile.get("groups", {}).items():
        if not isinstance(entries, list):
            raise ValueError(f"YAML profile group '{group_name}' must be a list")
        for entry in entries:
            if not isinstance(entry, dict) or not entry.get("label") or not entry.get("iri"):
                raise ValueError(f"Invalid {key} entry in YAML profile group '{group_name}'")
            yield group_name, entry


def _relation_endpoints(
    expression: object, classes_by_label: dict[str, str],
) -> tuple[str, ...] | None:
    if expression is None:
        return None
    expressions = expression if isinstance(expression, list) else [expression]
    endpoints: set[str] = set()
    for value in expressions:
        if not isinstance(value, str):
            continue
        value = re.sub(r";\s*plus\s+", "|", value, flags=re.IGNORECASE)
        parts = re.split(r"\s+or\s+|\s*\|\s*|\s*,\s*", value, flags=re.IGNORECASE)
        for part in filter(None, (item.strip() for item in parts)):
            label = classes_by_label.get(_label_key(part))
            if label is None:
                return ()
            endpoints.add(label)
    return tuple(sorted(endpoints)) if endpoints else ()


def _has_group_rule(expression: object) -> bool:
    values = expression if isinstance(expression, list) else [expression]
    return any(
        isinstance(value, str) and re.search(r"\bany\s+.+?\s+class\b", value, re.IGNORECASE)
        for value in values
    )


@dataclass(frozen=True)
class OntologyExtractionProfile:
    """Transformer-compatible labels plus the canonical prompt context."""

    allowed_nodes: tuple[str, ...]
    allowed_relationships: tuple[tuple[str, str, str] | str, ...]
    prompt_context: str
    human_prompt_context: str
    yaml_context: str = ""
    node_properties: tuple[str, ...] = ()
    relationship_properties: tuple[str, ...] = ()
    ontology_id: str = "business"
    class_iri_lookup: tuple[tuple[str, str], ...] = ()
    relationship_iri_lookup: tuple[tuple[str, str], ...] = ()
    inverse_relationships: tuple[tuple[str, str], ...] = ()


class OntologyExtractionAdapter:
    """Build LLM context from curated YAML profiles and retain OWL validation access."""

    def __init__(
        self,
        manifest_path: str | Path,
        root_id: str = "business-core-selected",
        selected_class_labels=None,
        profile_files: Iterable[str | Path] | None = None,
    ):
        manifest_path = Path(manifest_path)
        repository = OntologyRepository.from_manifest(manifest_path)
        self.imports = LocalImportResolver(repository)
        self.root_id = root_id
        self.selected_class_labels = (
            tuple(selected_class_labels) if selected_class_labels is not None else None
        )
        self._builder: OntologyContextBuilder | None = None

        if profile_files is None:
            try:
                profile_files = YAML_PROFILE_FILES[root_id]
            except KeyError as exc:
                raise ValueError(f"No YAML ontology profile configured for root '{root_id}'") from exc
        profile_dir = manifest_path.resolve().parent / "profiles"
        self.profile_paths = tuple(
            path if (path := Path(profile)).is_absolute() else profile_dir / path
            for profile in profile_files
        )

    @property
    def builder(self) -> OntologyContextBuilder:
        if self._builder is None:
            self._builder = OntologyContextBuilder.from_import_resolver(
                self.imports, self.root_id
            )
        return self._builder

    @property
    def resolver(self) -> SemanticResolver:
        return self.builder.resolver

    def build(self, root_id: str | None = None, max_prompt_chars: int | None = None) -> OntologyExtractionProfile:
        root_id = root_id or self.root_id
        class_payloads: dict[str, dict] = {}
        classes_by_label: dict[str, str] = {}
        property_payloads: dict[str, dict] = {}
        inherited_property_iris: set[str] = set()
        descriptions: list[str] = []
        yaml_documents: list[str] = []
        unoptimized_yaml_documents: list[str] = []
        class_iri_lookup: dict[str, str] = {}
        relationship_iri_lookup: dict[str, str] = {}
        node_properties: set[str] = set()
        relationship_properties: set[str] = set()

        for path in self.profile_paths:
            yaml_text = path.read_text(encoding="utf-8")
            profile = yaml.safe_load(yaml_text)
            if not isinstance(profile, dict):
                raise ValueError(f"YAML ontology profile must be a mapping: {path}")
            # Keep the prompt semantic and compact.  Canonical labels and
            # definitions are sufficient for extraction; IRIs remain in the
            # lookup tables used by the post-extraction ontology pipeline.
            profile_for_prompt = dict(profile)
            unoptimized_profile_for_prompt = dict(profile)
            unoptimized_profile_for_prompt.pop("type_sets", None)
            unoptimized_yaml_documents.append(yaml.dump(
                unoptimized_profile_for_prompt,
                Dumper=_ExpandedYamlDumper,
                sort_keys=False,
                default_flow_style=None,
                width=10000,
                allow_unicode=True,
            ).rstrip())
            profile_for_prompt["groups"] = {
                group: [{key: value for key, value in entry.items() if key != "iri"}
                        for entry in entries]
                for group, entries in profile.get("groups", {}).items()
            }
            for key in ("relationships", "inherited_relationships"):
                if key in profile_for_prompt:
                    profile_for_prompt[key] = [
                        {item_key: value for item_key, value in relation.items() if item_key != "iri"}
                        for relation in profile_for_prompt[key]
                        if str(relation.get("label", "")) not in INVERSE_RELATIONSHIP_PAIRS
                    ]
            profile_for_prompt.pop("type_sets", None)
            expanded_yaml = yaml.dump(
                profile_for_prompt,
                Dumper=_ExpandedYamlDumper,
                sort_keys=False,
                default_flow_style=None,
                width=10000,
                allow_unicode=True,
            )
            yaml_documents.append(f"# Source profile: {path.name}\n{expanded_yaml.rstrip()}")
            profile_metadata = profile.get("profile", {})
            node_properties.update(str(item) for item in profile.get("entity_properties", []) or [])
            relationship_properties.update(str(item) for item in profile.get("relationship_properties", []) or [])
            descriptions.append(str(profile_metadata.get("description", "")).strip())
            artifact_id = str(profile_metadata.get("ontology_artifact", path.stem))

            for _, entry in _yaml_entries(profile, "class"):
                label = str(entry["label"])
                iri = str(entry["iri"])
                if (
                    self.selected_class_labels is not None
                    and not any(_label_key(label) == _label_key(value) for value in self.selected_class_labels)
                ):
                    continue
                parent = entry.get("parent")
                payload = {
                    "iri": iri,
                    "label": label,
                    "labels": [label],
                    "parents": [str(parent)] if parent else [],
                    "ancestors": [],
                    "layer": artifact_id,
                }
                if entry.get("definition"):
                    payload["definition"] = str(entry["definition"])
                class_payloads.setdefault(iri, payload)
                classes_by_label.setdefault(_label_key(label), label)
                class_iri_lookup.setdefault(label, iri)

            for key in ("relationships", "inherited_relationships"):
                for relation in profile.get(key, []) or []:
                    if not isinstance(relation, dict):
                        raise ValueError(f"Invalid relationship in YAML ontology profile: {path}")
                    if any(
                        str(source).casefold() == "manufacturing"
                        for source in (relation.get("ends_defined_in_other_files") or {}).values()
                    ):
                        continue
                    if not relation.get("iri") or not relation.get("label"):
                        raise ValueError(f"Relationship missing label or IRI in YAML profile: {path}")
                    iri = str(relation["iri"])
                    if key == "inherited_relationships":
                        inherited_property_iris.add(iri)
                    domain = relation.get("domain")
                    range_ = relation.get("range")
                    payload = {
                        "iri": iri,
                        "label": str(relation["label"]),
                        "labels": [str(relation["label"])],
                        "domain": [str(domain)] if domain is not None else [],
                        "range": [str(range_)] if range_ is not None else [],
                        "inverses": list(relation.get("inverses", []) or []),
                        "layer": artifact_id,
                    }
                    if relation.get("definition"):
                        payload["definition"] = str(relation["definition"])
                    property_payloads.setdefault(iri, payload)
                    relationship_iri_lookup.setdefault(str(relation["label"]), iri)

        if self.selected_class_labels is not None:
            available = {_label_key(item["label"]) for item in class_payloads.values()}
            missing = [
                label for label in self.selected_class_labels
                if _label_key(label) not in available
            ]
            if missing:
                raise KeyError(f"Selected classes are not defined by the YAML profiles: {missing}")

        classes = tuple(sorted(class_payloads.values(), key=lambda item: item["iri"]))
        properties = tuple(sorted(property_payloads.values(), key=lambda item: item["iri"]))
        nodes = tuple(sorted({item["label"] for item in classes}, key=str.casefold))
        relationships: set[tuple[str, str, str]] = set()
        group_rule_relationships: set[str] = set()
        for prop in properties:
            if (
                prop["iri"] in inherited_property_iris
                or _has_group_rule(prop["domain"])
                or _has_group_rule(prop["range"])
            ):
                group_rule_relationships.add(prop["label"])
                continue
            domains = _relation_endpoints(prop["domain"], classes_by_label)
            ranges = _relation_endpoints(prop["range"], classes_by_label)
            if not domains or not ranges:
                group_rule_relationships.add(prop["label"])
                continue
            relationships.update(
                (source, prop["label"], target)
                for source in domains
                for target in ranges
            )

        instructions = OntologyContextBuilder.DEFAULT_INSTRUCTIONS + tuple(
            description for description in descriptions if description
        )
        context = OntologyContext(
            ontology_id=root_id,
            classes=classes,
            properties=properties,
            instructions=instructions,
        )
        result = OntologyExtractionProfile(
            allowed_nodes=nodes,
            allowed_relationships=tuple(sorted(relationships)) + tuple(sorted(group_rule_relationships)),
            prompt_context=context.to_prompt(),
            human_prompt_context=context.to_human_prompt(),
            yaml_context="\n\n".join(yaml_documents),
            node_properties=tuple(sorted(node_properties)),
            relationship_properties=tuple(sorted(relationship_properties)),
            ontology_id=root_id,
            class_iri_lookup=tuple(sorted(class_iri_lookup.items())),
            relationship_iri_lookup=tuple(sorted(relationship_iri_lookup.items())),
            inverse_relationships=tuple(sorted(INVERSE_RELATIONSHIP_PAIRS.items())),
        )
        if max_prompt_chars is not None and len(result.yaml_context) > max_prompt_chars:
            raise ValueError(
                f"Ontology YAML context is {len(result.yaml_context)} characters, "
                f"above configured limit {max_prompt_chars}; narrow the ontology root/profile"
            )
        logging.info(
            "Ontology YAML context length before prompt optimization: %d characters; after: %d characters",
            len("\n\n".join(unoptimized_yaml_documents)),
            len(result.yaml_context),
        )
        return result

    @staticmethod
    def profile_catalog() -> dict[str, str]:
        return dict(PROFILE_DESCRIPTIONS)

    @classmethod
    def build_selected(
        cls, manifest_path: str | Path, profile_ids: Iterable[str], max_prompt_chars: int | None = None
    ) -> OntologyExtractionProfile:
        selected = tuple(dict.fromkeys((*ALWAYS_LOADED, *profile_ids)))
        unknown = [profile_id for profile_id in selected if profile_id not in YAML_PROFILE_FILES]
        if unknown:
            raise ValueError(f"Unknown ontology profile(s): {unknown}")
        paths = [YAML_PROFILE_FILES[profile_id][0] for profile_id in selected]
        profile = cls(manifest_path, root_id=selected[0], profile_files=paths).build(
            max_prompt_chars=max_prompt_chars
        )
        return OntologyExtractionProfile(
            allowed_nodes=profile.allowed_nodes,
            allowed_relationships=profile.allowed_relationships,
            prompt_context=profile.prompt_context,
            human_prompt_context=profile.human_prompt_context,
            yaml_context=profile.yaml_context,
            node_properties=profile.node_properties,
            relationship_properties=profile.relationship_properties,
            ontology_id=",".join(selected),
            class_iri_lookup=profile.class_iri_lookup,
            relationship_iri_lookup=profile.relationship_iri_lookup,
            inverse_relationships=profile.inverse_relationships,
        )


def default_adapter() -> OntologyExtractionAdapter:
    manifest = os.getenv(
        "ONTOLOGY_MANIFEST_PATH",
        str(Path(__file__).resolve().parents[1] / "Ontology" / "manifest.yaml"),
    )
    # Profile selection is document-driven. The adapter always starts from the
    # canonical business base profile; optional profiles are merged explicitly
    # through OntologyExtractionAdapter.build_selected().
    return OntologyExtractionAdapter(
        manifest,
        # The resolver root is the manifest artifact ID; profile IDs are
        # handled separately by build_selected().
        "business",
        profile_files=("business.yaml",),
    )


def default_profile() -> OntologyExtractionProfile:
    configured_limit = os.getenv("ONTOLOGY_CONTEXT_MAX_CHARS")
    limit = int(configured_limit) if configured_limit else None
    manifest = os.getenv(
        "ONTOLOGY_MANIFEST_PATH",
        str(Path(__file__).resolve().parents[1] / "Ontology" / "manifest.yaml"),
    )
    return OntologyExtractionAdapter.build_selected(
        manifest, (), max_prompt_chars=limit
    )
