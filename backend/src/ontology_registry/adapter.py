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
    # IOF Core
    "core-selected": (
        "Industrial_Ontologies_Foundry/core.yaml",
    ),
    "annotation-vocabulary-selected": (
        "Industrial_Ontologies_Foundry/AnnotationVocabulary.yaml",
    ),

    # General IOF ontologies
    "production-planning-complete": (
        "Industrial_Ontologies_Foundry/production.yaml",
    ),
    "maintenance-complete": (
        "Industrial_Ontologies_Foundry/maintenance.yaml",
    ),
    "certification-complete": (
        "Industrial_Ontologies_Foundry/certification.yaml",
    ),
    "product-service-system-complete": (
        "Industrial_Ontologies_Foundry/product_service_system.yaml",
    ),
    "sensor-selected": (
        "Industrial_Ontologies_Foundry/sensor.yaml",
    ),
    "sensor-complete": (
        "Industrial_Ontologies_Foundry/sensor.yaml",
    ),
    "supply-chain-complete": (
        "Industrial_Ontologies_Foundry/SupplyChain.yaml",
    ),

    # BioPharma: Agent
    "biopharma-agent-complete": (
        "Industrial_Ontologies_Foundry/BioPharma/BioPharmaAgent.yaml",
    ),

    # BioPharma: Equipment
    "biopharma-equipment-complete": (
        "Industrial_Ontologies_Foundry/BioPharma/BioPharmaEquipment.yaml",
    ),

    # BioPharma: Material
    "biopharma-material-complete": (
        "Industrial_Ontologies_Foundry/BioPharma/BioPharmaMaterial.yaml",
    ),

    # BioPharma: Parameter
    "biopharma-parameter-complete": (
        "Industrial_Ontologies_Foundry/BioPharma/BiopharmaParameter.yaml",
    ),

    # BioPharma: Monitoring and Control
    "biopharma-monitoring-and-control-complete": (
        "Industrial_Ontologies_Foundry/BioPharma/BiopharmaMonitoringAndControl.yaml",
    ),

    # BioPharma: Manufacturing System Organization
    "biopharma-manufacturing-system-organization-complete": (
        "Industrial_Ontologies_Foundry/BioPharma/ManufacturingSystemOrganization.yaml",
    ),

    # BioPharma: Recipe
    "recipe-ontology-complete": (
        "Industrial_Ontologies_Foundry/BioPharma/Recipe.yaml",
    ),
    "biopharma-recipe-complete": (
        "Industrial_Ontologies_Foundry/BioPharma/Recipe.yaml",
    ),

    # BioPharma: Manufacturing Execution
    "biopharma-manufacturing-execution-complete": (
        "Industrial_Ontologies_Foundry/BioPharma/BioPharmaManufacturingExecution.yaml",
    ),

    # BioPharma: Material Procurement and Storage
    "biopharma-material-procurement-and-storage-complete": (
        "Industrial_Ontologies_Foundry/BioPharma/BiopharmaMaterialProcurementAndStorage.yaml",
    ),

    # BioPharma: Reference Ontologies
    "reference-ontology-candidates-complete": (
        "Industrial_Ontologies_Foundry/BioPharma/ReferenceOntologyCandidates.yaml",
    ),

    "biopharma-reference-ontology-attributes-complete": (
        "Industrial_Ontologies_Foundry/BioPharma/BiopharmaReferenceOntologyAttributes.yaml",
    ),

    "molecular-entity-complete": (
        "Industrial_Ontologies_Foundry/BioPharma/MolecularEntity.yaml",
    ),

    "targets-limits-ranges-complete": (
        "Industrial_Ontologies_Foundry/BioPharma/TargetsLimitsRanges.yaml",
    ),
}


PROFILE_IMPORTS: dict[str, tuple[str, ...]] = {
    "biopharma-reference-ontology-attributes-complete": (
        "reference-ontology-candidates-complete",
    ),
    "targets-limits-ranges-complete": ("reference-ontology-candidates-complete",),
    "biopharma-equipment-complete": (
        "biopharma-reference-ontology-attributes-complete",
        "reference-ontology-candidates-complete",
    ),
    "biopharma-material-complete": (
        "biopharma-reference-ontology-attributes-complete",
        "molecular-entity-complete",
        "reference-ontology-candidates-complete",
    ),
    "biopharma-parameter-complete": (
        "biopharma-material-complete",
        "targets-limits-ranges-complete",
        "reference-ontology-candidates-complete",
    ),
    "biopharma-monitoring-and-control-complete": (
        "biopharma-parameter-complete",
        "biopharma-manufacturing-system-organization-complete",
        "reference-ontology-candidates-complete",
    ),
    "biopharma-recipe-complete": (
        "biopharma-manufacturing-system-organization-complete",
        "reference-ontology-candidates-complete",
    ),
    "biopharma-manufacturing-execution-complete": (
        "biopharma-recipe-complete",
        "biopharma-material-complete",
        "biopharma-monitoring-and-control-complete",
        "biopharma-equipment-complete",
        "biopharma-manufacturing-system-organization-complete",
        "biopharma-agent-complete",
    ),
    "biopharma-material-procurement-and-storage-complete": (
        "reference-ontology-candidates-complete",
        "certification-complete",
        "supply-chain-complete",
    ),
    "sensor-complete": ("supply-chain-complete",),
    "product-service-system-complete": ("supply-chain-complete",),
}


PROFILE_ALIASES = {
    "sensor-selected": "sensor-complete",
    "recipe-ontology-complete": "biopharma-recipe-complete",
}


def resolve_profile_closure(profile_ids: Iterable[str]) -> tuple[str, ...]:
    """Resolve profile imports with dependencies before their dependents."""
    resolved: list[str] = []
    visiting: list[str] = []

    def visit(profile_id: str) -> None:
        profile_id = PROFILE_ALIASES.get(profile_id, profile_id)
        if profile_id in visiting:
            cycle = visiting[visiting.index(profile_id):] + [profile_id]
            raise ValueError(f"Circular ontology profile import: {' -> '.join(cycle)}")
        if profile_id in resolved:
            return
        if profile_id not in YAML_PROFILE_FILES:
            raise ValueError(f"Unknown ontology profile(s): [{profile_id!r}]")
        visiting.append(profile_id)
        for dependency in PROFILE_IMPORTS.get(profile_id, ()):
            visit(dependency)
        visiting.pop()
        resolved.append(profile_id)

    for profile_id in profile_ids:
        visit(profile_id)
    return tuple(resolved)


def _validate_yaml_profile_files(profile_dir: Path) -> None:
    missing = sorted({
        str(profile_dir / profile_file)
        for profile_files in YAML_PROFILE_FILES.values()
        for profile_file in profile_files
        if not (profile_dir / profile_file).is_file()
    })
    if missing:
        raise FileNotFoundError(
            "Configured ontology YAML profile file(s) not found: "
            + ", ".join(missing)
        )


PROFILE_DESCRIPTIONS = {
    "molecular-entity-complete": (
        "Select ONLY when the document describes molecular entities such as Antibody, "
        "Deoxyribonucleic Acid, Nucleic Acid, Glycoprotein, Chemical Moiety, or other molecular "
        "entity classes represented in the molecular-entity ontology. Do NOT select for materials, "
        "formulations or cell cultures as a whole; those are in the biopharma-material profile."
    ),
    "targets-limits-ranges-complete": (
        "Select ONLY when the document describes targets, limits, ranges or specification bounds "
        "for process parameters and attributes, including target values, upper or lower limits, "
        "acceptable ranges or operating ranges. Do NOT select for the parameters themselves."
    ),
    # Business profiles (commented out)
    # "business-order-to-cash": (
    #     "Select ONLY for the seller-side process of taking and billing customer orders: sales orders "
    #     "or contracts, quotes, customer credit checks, discount approvals, invoices, billing, or "
    #     "payment collection. Do NOT select for purchasing from suppliers, shipment or warehouse "
    #     "operations, or revenue accounting unless those are also substantive parts of the document. "
    #     "The word 'order' alone is not a reason to select it."
    # ),
    # "business-procurement-supplier-management": (
    #     "Select ONLY for the buyer-side process of requesting, sourcing, or purchasing goods or "
    #     "services from suppliers: purchase requisitions or purchase orders, procurement activities, "
    #     "supplier terms, and purchase receipt. Do NOT select for customer sales orders, outbound "
    #     "shipments, or general supplier mentions that are not part of a purchasing workflow."
    # ),
    # "business-fulfillment-logistics": (
    #     "Select ONLY when the document describes preparing, moving, shipping, or handing over goods: "
    #     "shipments, deliveries, carriers, shipping documents, proof of shipment or delivery, or "
    #     "plant-to-plant and warehouse transfers. Do NOT select for production planning or execution, "
    #     "facility layout, or inventory/product descriptions without a goods-movement workflow."
    # ),
    # "business-revenue-accounting": (
    #     "Select ONLY when the document describes recording, recognizing, or allocating financial "
    #     "amounts: accounting or revenue entries, accruals, deferred revenue, fiscal periods, ledger "
    #     "accounts, or profit centers. Do NOT select for routine invoice issuance, payment collection, "
    #     "or purchase orders unless accounting treatment or revenue recognition is also in scope."
    # ),
    # "business-governance-risk-compliance": (
    #     "Select ONLY when governance, risk, or compliance is a substantive subject: business policies "
    #     "or rules, internal controls, identified risks, compliance obligations, formal assessments, "
    #     "or audits of processes or controls. Do NOT select for a routine transaction approval "
    #     "(including a discount approval), a credit check, or certification against an external "
    #     "standard unless governance or control requirements are also described."
    # ),
    # "business-products-inventory": (
    #     "Select ONLY for product identity, specification, categorization, packaging, inventory, "
    #     "storage status, or product composition (components). Do NOT select for production schedules, "
    #     "manufacturing operations, or process execution; use the production-planning profile for "
    #     "those. Do NOT select for shipment and delivery workflows or facility layout unless product "
    #     "or inventory information is also substantive."
    # ),
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
    "biopharma-manufacturing-system-organization-complete": (
        "Select ONLY when the document describes the physical structure of a manufacturing "
        "enterprise: enterprise, physical sites and areas, work centers, work cells, production "
        "lines, production units, process cells, storage zones and units, equipment and control "
        "modules. "
        "Do NOT select for departments, cost centers, legal entities or reporting lines."
    ),
    "product-service-system-complete": (
        "Select ONLY when the document describes a product-service system: its products, "
        "commercial services, providers, customers, requirements, specifications, resources, "
        "product families, variants, or PSS business processes."
    ),
    "sensor-complete": (
        "Select ONLY when the document describes sensors or measurement instrumentation, including "
        "detecting devices, transducers, observers, observations, sensing processes, sensor roles, "
        "or sensor specifications."
    ),
    "supply-chain-complete": (
        "Select ONLY when the document describes supply chain networks, supply network tiers, "
        "suppliers, distributors, fulfillment nodes, or supply chains. "
        "Do NOT select for routine single-purchase requisitions or internal plant transfers."
    ),
    "biopharma-agent-complete": (
        "Select ONLY when the document describes actors, operators, or personnel specific to "
        "biopharmaceutical manufacturing: manufacturing operators, validators, operator roles, "
        "validator roles, or agent identification credentials. "
        "Do NOT select for general enterprise organizational units, business departments, or general persons."
    ),
    "biopharma-equipment-complete": (
        "Select ONLY when the document describes biopharmaceutical manufacturing equipment, holding "
        "vessels, or equipment-specific capabilities and functions: bioreactors, rocker bags, "
        "cryovials, vials, flasks (shake flask, spinner flask, T-flask), bioreactor vessels, holding "
        "capabilities, holding functions, and equipment specifications. "
        "Do NOT select for high-level facility layout or general piece of equipment without biopharma equipment specifics."
    ),
    "biopharma-manufacturing-execution-complete": (
        "Select ONLY when the document describes actual occurrences of biomanufacturing processes "
        "and biological execution: process operating modes (batch, fed-batch, continuous culture, "
        "chemostat, perfusion), upstream cell culture, cell line development, transfection, "
        "transduction, clone selection, cell banking, cell proliferation, harvest, purification, "
        "filtration, chromatography, viral clearance, or solution preparation. "
        "Do NOT select for high-level production schedules or recipe specifications alone."
    ),
    "biopharma-material-procurement-and-storage-complete": (
        "Select ONLY when the document describes biopharmaceutical material procurement, tracking, "
        "and storage status: CAS registry numbers, catalog numbers, ERP item codes, Certificates "
        "of Analysis (CoA), Certificates of Conformance (CoC), material expiration dates, shelf life, "
        "first use timestamps, or expired states. "
        "Do NOT select for routine general purchasing or shipping logistics unless biopharma material compliance or storage attributes are substantive."
    ),
    "biopharma-monitoring-and-control-complete": (
        "Select ONLY when the document describes process monitoring, sampling, or control strategies "
        "in biomanufacturing: inline, atline, online, and offline monitoring processes, material "
        "sampling plans and sampling processes, material aliquots, retention samples, quality plans, "
        "and control strategies. "
        "Do NOT select for general physical sensor hardware or routine equipment maintenance."
    ),
    "biopharma-parameter-complete": (
        "Select ONLY when the document describes biopharmaceutical process parameters, quality attributes, "
        "or biological rate metrics: Critical Process Parameters (CPP), Critical Quality Attributes "
        "(CQA), Critical Material Attributes (CMA), agitation rate, cell doubling time, cell specific "
        "productivity, cell population growth rate, dissolution rate, carbon dioxide evolution rate, "
        "or biological activity. "
        "Do NOT select for basic physical dimensions or general sensor readings without biopharma parameter context."
    ),
    "biopharma-recipe-complete": (
        "Select ONLY when the document describes biopharmaceutical recipes or procedural batch "
        "specifications: general recipes, site recipes, master recipes, control recipes, recipe "
        "procedures, recipe operations, recipe phases, procedural elements, batch runs, or recipe "
        "derivation and lifecycle processes. "
        "Do NOT select for process execution run logs without recipe structure or for general production orders."
    ),
    "reference-ontology-candidates-complete": (
        "Select ONLY when the document describes cross-cutting manufacturing operations and roles: "
        "material addition processes, material removal processes, material transfer processes, "
        "material use processes, process intermediate materials, production consumables, acceptance "
        "criteria, or material target/impurity/withdrawal roles. "
        "Do NOT select for general business contracts or high-level material handling plans."
    ),
    "biopharma-reference-ontology-attributes-complete": (
        "Select ONLY when the document describes biopharmaceutical reference attributes such as "
        "identifiers, classifications, or other reference metadata for materials and processes. "
        "Do NOT select for the underlying materials, equipment or process execution themselves."
    ),
    "biopharma-material-complete": (
        "Select ONLY when the document describes biopharmaceutical materials, substance types, and "
        "biological entities: raw materials, active pharmaceutical ingredients (API), drug substances, "
        "process intermediates, cell cultures, cell populations, media, buffers, reagents, or "
        "formulated products. "
        "Do NOT select for general pieces of equipment, facility layout, or business inventory records."
    ),
}


ALWAYS_LOADED = ["core-selected", "annotation-vocabulary-selected"]

# Business YAML profiles remain available in the repository and profile
# catalog, but are excluded from the active LLM context until explicitly
# enabled.
BUSINESS_PROFILE_IDS = {
    "business-common",
    "business-order-to-cash",
    "business-procurement-supplier-management",
    "business-fulfillment-logistics",
    "business-revenue-accounting",
    "business-governance-risk-compliance",
    "business-products-inventory",
}


def business_profiles_enabled() -> bool:
    return os.getenv("ONTOLOGY_INCLUDE_BUSINESS_PROFILES", "false").strip().lower() in {
        "1", "true", "yes", "on"
    }

DEFAULT_PROFILE_NOTES = {
    "core-selected": (
        "Always loaded. Generic industrial concepts: agents, material artifacts, equipment, "
        "planned processes, roles, capabilities and measurement."
    ),
    "annotation-vocabulary-selected": (
        "Always loaded. IOF annotation vocabulary used to interpret ontology metadata."
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
    groups = profile.get("groups")
    if groups is None and key == "class":
        groups = {"entities": profile.get("entities", [])}
    for group_name, entries in (groups or {}).items():
        if not isinstance(entries, list):
            raise ValueError(f"YAML profile group '{group_name}' must be a list")
        for entry in entries:
            if not isinstance(entry, dict) or not entry.get("label") or not entry.get("iri"):
                raise ValueError(f"Invalid {key} entry in YAML profile group '{group_name}'")
            if key == "class" and entry.get("extractable") is False:
                continue
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
    class_profile_lookup: tuple[tuple[str, str], ...] = ()
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
        _validate_yaml_profile_files(profile_dir)
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
            if not profile_path.is_file() or profile_path.stat().st_size == 0:
                continue
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
        class_profile_lookup: dict[str, set[str]] = {}
        relationship_iri_lookup: dict[str, str] = {}
        node_properties: set[str] = set()
        relationship_properties: set[str] = set()

        for path in self.profile_paths:
            if not path.is_file() or path.stat().st_size == 0:
                continue
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
            profile_id = str(profile_metadata.get("id", path.stem))
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
                parent = entry.get("parent", entry.get("parent_class"))
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
                class_profile_lookup.setdefault(label, set()).add(profile_id)

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
            class_profile_lookup=tuple(sorted(
                (label, "core-selected" if "core-selected" in profile_ids else sorted(profile_ids)[0])
                for label, profile_ids in class_profile_lookup.items()
            )),
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
        requested = tuple(profile_ids)
        if not business_profiles_enabled():
            requested = tuple(
                profile_id for profile_id in requested
                if profile_id not in BUSINESS_PROFILE_IDS
            )
        else:
            skipped_business = tuple(
                profile_id for profile_id in requested
                if profile_id in BUSINESS_PROFILE_IDS and profile_id not in YAML_PROFILE_FILES
            )
            if skipped_business:
                logging.warning(
                    "Skipping business ontology profiles without YAML configuration: %s",
                    skipped_business,
                )
                requested = tuple(
                    profile_id for profile_id in requested if profile_id not in skipped_business
                )
        unknown = [
            profile_id for profile_id in requested
            if profile_id not in YAML_PROFILE_FILES
            and profile_id not in BUSINESS_PROFILE_IDS
        ]
        if unknown:
            raise ValueError(f"Unknown ontology profile(s): {unknown}")
        selected = resolve_profile_closure((*ALWAYS_LOADED, *requested))
        paths = list(dict.fromkeys(
            path
            for profile_id in selected
            for path in YAML_PROFILE_FILES[profile_id]
        ))
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
            class_profile_lookup=profile.class_profile_lookup,
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
    profile_files = tuple(dict.fromkeys(
        path
        for profile_id in resolve_profile_closure(ALWAYS_LOADED)
        for path in YAML_PROFILE_FILES[profile_id]
    ))
    return OntologyExtractionAdapter(
        manifest,
        ALWAYS_LOADED[0],
        profile_files=profile_files,
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
