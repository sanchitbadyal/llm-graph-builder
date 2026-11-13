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
    "business-common": ("business.yaml",),
    "core-selected": ("Industrial_Ontologies_Foundry/core.yaml",),
    "business-order-to-cash": ("business_order_to_cash.yaml",),
    "business-procurement-supplier-management": ("business_procurement_supplier_management.yaml",),
    "business-fulfillment-logistics": ("business_fulfillment_logistics.yaml",),
    "business-revenue-accounting": ("business_revenue_accounting.yaml",),
    "business-governance-risk-compliance": ("business_governance_risk_compliance.yaml",),
    "business-products-inventory": ("business_products_inventory.yaml",),
    "production-planning-complete": ("Industrial_Ontologies_Foundry/production.yaml",),
    "maintenance-complete": ("Industrial_Ontologies_Foundry/maintenance.yaml",),
    "certification-complete": ("Industrial_Ontologies_Foundry/certification.yaml",),
    "manufacturing-system-organization-complete": ("Industrial_Ontologies_Foundry/manufacturing_system_organiztion.yaml",),
    "product-service-system-complete": ("Industrial_Ontologies_Foundry/product_service_system.yaml",),
    "sensor-selected": ("Industrial_Ontologies_Foundry/sensor.yaml",),
}

PROFILE_DESCRIPTIONS = {
    "business-order-to-cash": (
        "Select ONLY for the seller-side process of taking and billing customer orders: sales orders "
        "or contracts, quotes, customer credit checks, discount approvals, invoices, billing, or "
        "payment collection. Do NOT select for purchasing from suppliers, shipment or warehouse "
        "operations, or revenue accounting unless those are also substantive parts of the document. "
        "The word 'order' alone is not a reason to select it."
    ),
    "business-procurement-supplier-management": (
        "Select ONLY for the buyer-side process of requesting, sourcing, or purchasing goods or "
        "services from suppliers: purchase requisitions or purchase orders, procurement activities, "
        "supplier terms, and purchase receipt. Do NOT select for customer sales orders, outbound "
        "shipments, or general supplier mentions that are not part of a purchasing workflow."
    ),
    "business-fulfillment-logistics": (
        "Select ONLY when the document describes preparing, moving, shipping, or handing over goods: "
        "shipments, deliveries, carriers, shipping documents, proof of shipment or delivery, or "
        "plant-to-plant and warehouse transfers. Do NOT select for production planning or execution, "
        "facility layout, or inventory/product descriptions without a goods-movement workflow."
    ),
    "business-revenue-accounting": (
        "Select ONLY when the document describes recording, recognizing, or allocating financial "
        "amounts: accounting or revenue entries, accruals, deferred revenue, fiscal periods, ledger "
        "accounts, or profit centers. Do NOT select for routine invoice issuance, payment collection, "
        "or purchase orders unless accounting treatment or revenue recognition is also in scope."
    ),
    "business-governance-risk-compliance": (
        "Select ONLY when governance, risk, or compliance is a substantive subject: business policies "
        "or rules, internal controls, identified risks, compliance obligations, formal assessments, "
        "or audits of processes or controls. Do NOT select for a routine transaction approval "
        "(including a discount approval), a credit check, or certification against an external "
        "standard unless governance or control requirements are also described."
    ),
    "business-products-inventory": (
        "Select ONLY for product identity, specification, categorization, packaging, inventory, "
        "storage status, or product composition (components). Do NOT select for production schedules, "
        "manufacturing operations, or process execution; use the production-planning profile for "
        "those. Do NOT select for shipment and delivery workflows or facility layout unless product "
        "or inventory information is also substantive."
    ),
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
    "product-service-system-complete": (
        "Select ONLY when the document describes a product-service system: its products, "
        "commercial services, providers, customers, requirements, specifications, resources, "
        "product families, variants, or PSS business processes."
    ),
    "sensor-selected": (
        "Select ONLY when the document describes sensors or measurement instrumentation, including "
        "detecting devices, transducers, observers, observations, sensing processes, sensor roles, "
        "or sensor specifications."
    ),
}


ALWAYS_LOADED = ["business-common", "core-selected"]

DEFAULT_PROFILE_NOTES = {
    "business-common": (
        "Always loaded. Shared business context: organizations, organizational units, cost centers, "
        "legal entities, roles, positions, locations, and general business relationships. Select an "
        "optional business profile for the document's specialized business workflow."
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
    "performs": "performed by",
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
    expression: object,
    classes_by_label: dict[str, str],
    known_class_labels: set[str],
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
            key = _label_key(part)
            label = classes_by_label.get(key)
            if label is not None:
                endpoints.add(label)
            elif key not in known_class_labels:
                return None
    return tuple(sorted(endpoints)) if endpoints else ()


def _filter_prompt_endpoints(
    value: object, selected_class_labels: set[str], known_class_labels: set[str]
) -> tuple[object, bool]:
    if isinstance(value, list):
        filtered = [
            item
            for item in value
            if not isinstance(item, str)
            or _label_key(item) not in known_class_labels
            or _label_key(item) in selected_class_labels
        ]
        return filtered, bool(value) and not filtered
    if isinstance(value, str):
        key = _label_key(value)
        return value, key in known_class_labels and key not in selected_class_labels
    return value, False


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
    yaml_class_parents: tuple[tuple[str, tuple[str, ...]], ...] = ()
    yaml_relationship_constraints: tuple[
        tuple[str, str, tuple[str, ...] | None, tuple[str, ...] | None], ...
    ] = ()


class OntologyExtractionAdapter:
    """Build LLM context and semantic validation constraints from YAML profiles."""

    def __init__(
        self,
        manifest_path: str | Path,
        root_id: str = "business-common",
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
        self.profile_dir = profile_dir
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
        known_class_labels: set[str] = set()
        profile_dir = self.profile_dir
        configured_files = dict.fromkeys(
            profile_file
            for profile_files in YAML_PROFILE_FILES.values()
            for profile_file in profile_files
        )
        for profile_file in configured_files:
            profile_path = profile_dir / profile_file
            configured_profile = yaml.safe_load(profile_path.read_text(encoding="utf-8"))
            if not isinstance(configured_profile, dict):
                raise ValueError(f"YAML ontology profile must be a mapping: {profile_path}")
            known_class_labels.update(
                _label_key(str(entry["label"]))
                for _, entry in _yaml_entries(configured_profile, "class")
            )
        property_payloads: dict[str, dict] = {}
        inherited_property_iris: set[str] = set()
        descriptions: list[str] = []
        yaml_documents: list[str] = []
        yaml_prompt_profiles: list[tuple[Path, dict]] = []
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
            yaml_prompt_profiles.append((path, profile_for_prompt))
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
                        "domain": (
                            [str(item) for item in domain]
                            if isinstance(domain, list)
                            else [str(domain)] if domain is not None else []
                        ),
                        "range": (
                            [str(item) for item in range_]
                            if isinstance(range_, list)
                            else [str(range_)] if range_ is not None else []
                        ),
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

        selected_class_label_keys = set(classes_by_label)
        for path, profile_for_prompt in yaml_prompt_profiles:
            for key in ("relationships", "inherited_relationships"):
                filtered_relationships = []
                for relation in profile_for_prompt.get(key, []) or []:
                    endpoints = {}
                    unavailable = False
                    for endpoint in ("domain", "range"):
                        endpoints[endpoint], endpoint_unavailable = _filter_prompt_endpoints(
                            relation.get(endpoint),
                            selected_class_label_keys,
                            known_class_labels,
                        )
                        unavailable = unavailable or endpoint_unavailable
                    if not unavailable:
                        relation.update(endpoints)
                        filtered_relationships.append(relation)
                if key in profile_for_prompt:
                    profile_for_prompt[key] = filtered_relationships
            expanded_yaml = yaml.dump(
                profile_for_prompt,
                Dumper=_ExpandedYamlDumper,
                sort_keys=False,
                default_flow_style=None,
                width=10000,
                allow_unicode=True,
            )
            yaml_documents.append(f"# Source profile: {path.name}\n{expanded_yaml.rstrip()}")

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
            domains = _relation_endpoints(
                prop["domain"], classes_by_label, known_class_labels
            )
            ranges = _relation_endpoints(
                prop["range"], classes_by_label, known_class_labels
            )
            if domains == () or ranges == ():
                continue
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
            yaml_class_parents=tuple(sorted(
                (
                    str(item["label"]),
                    tuple(str(parent) for parent in item.get("parents", ()) if parent),
                )
                for item in class_payloads.values()
            )),
            yaml_relationship_constraints=tuple(sorted(
                (
                    str(item["iri"]),
                    str(item["label"]),
                    _relation_endpoints(item["domain"], classes_by_label, known_class_labels),
                    _relation_endpoints(item["range"], classes_by_label, known_class_labels),
                )
                for item in properties
            )),
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
            yaml_class_parents=profile.yaml_class_parents,
            yaml_relationship_constraints=profile.yaml_relationship_constraints,
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
