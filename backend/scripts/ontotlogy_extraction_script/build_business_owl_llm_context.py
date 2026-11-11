#!/usr/bin/env python3
"""Build an LLM context from selected classes and relationships in business.owl.

This script is standalone: it does not read business.yaml and has no YAML
dependency. The selected labels below define the extraction scope; business.owl
is the semantic source for IRIs, labels, hierarchy, domains, ranges, and inverses.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from xml.etree import ElementTree as ET

RDF = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
OWL = "http://www.w3.org/2002/07/owl#"
RDFS = "http://www.w3.org/2000/01/rdf-schema#"
SKOS = "http://www.w3.org/2004/02/skos/core#"
DEFAULT_OWL = Path(__file__).resolve().parents[1] / "src/Ontology/business.owl"

SELECTED_CLASSES = (
    "Packaged Unit", "Warehouse", "Location", "Address", "Account", "Ledger Account", "Product Category", "Position",
    "Organization", "Organizational Unit", "Cost Center", "Legal Entity", "Supplier Role", "Employee Role", "Approver Role",
    "Purchase Order", "Quote", "Credit Note", "Receipt", "Delivery Note", "Specification", "Certificate", "Accounting Entry",
    "Approval", "Assessment", "Audit", "Billing", "Payment", "Collection", "Fulfillment", "Delivery", "Transport",
    "Stock Transfer", "Service", "Manufacturing", "Procurement", "Reconciliation", "Revenue Recognition", "Return", "Escalation", "Procedure",
    "Business Rule", "Policy", "Risk", "Milestone",
)


def tag(namespace: str, name: str) -> str:
    return f"{{{namespace}}}{name}"


def local_name(iri: str) -> str:
    return iri.rsplit("#", 1)[-1].rsplit("/", 1)[-1]


def resources(element: ET.Element, namespace: str, name: str) -> tuple[str, ...]:
    attr = tag(RDF, "resource")
    return tuple(value for child in element.findall(tag(namespace, name)) if (value := child.get(attr)))


def text_value(element: ET.Element, namespace: str, name: str) -> str | None:
    child = element.find(tag(namespace, name))
    value = "".join(child.itertext()).strip() if child is not None else ""
    return value or None


def parse_ontology(path: Path) -> tuple[dict[str, dict], list[dict]]:
    root = ET.parse(path).getroot()
    about = tag(RDF, "about")
    class_tags = {tag(OWL, "Class"), tag(RDFS, "Class")}
    property_tags = {tag(OWL, "ObjectProperty"), tag(OWL, "DatatypeProperty"), tag(RDF, "Property")}
    classes: dict[str, dict] = {}
    properties: list[dict] = []
    for element in root.iter():
        iri = element.get(about)
        if not iri:
            continue
        if element.tag in class_tags:
            label = text_value(element, RDFS, "label") or local_name(iri)
            classes[label.casefold()] = {
                "label": label, "iri": iri,
                "parents": list(resources(element, RDFS, "subClassOf")),
                "definition": text_value(element, SKOS, "definition"),
            }
        elif element.tag in property_tags:
            properties.append({
                "label": text_value(element, RDFS, "label") or local_name(iri),
                "iri": iri,
                "domain": list(resources(element, RDFS, "domain")),
                "range": list(resources(element, RDFS, "range")),
                "inverses": list(resources(element, OWL, "inverseOf")),
            })
    return classes, properties


def ancestors(iri: str, classes_by_iri: dict[str, dict]) -> list[str]:
    result: set[str] = set()
    pending = [iri]
    while pending:
        current = pending.pop()
        if current in result:
            continue
        result.add(current)
        if current in classes_by_iri:
            pending.extend(classes_by_iri[current]["parents"])
    return sorted(result)


def build_context(owl_path: Path, *, include_partial_relationships: bool = False) -> dict:
    classes_by_label, properties = parse_ontology(owl_path)
    classes_by_iri = {item["iri"]: item for item in classes_by_label.values()}
    selected: list[dict] = []
    selected_iris: set[str] = set()
    missing: list[str] = []
    for label in SELECTED_CLASSES:
        value = classes_by_label.get(label.casefold())
        if value is None:
            missing.append(label)
            continue
        selected_iris.add(value["iri"])
        selected.append({
            "label": value["label"], "iri": value["iri"], "parents": value["parents"],
            "ancestors": ancestors(value["iri"], classes_by_iri), "definition": value["definition"],
        })
    relevant = []
    for prop in properties:
        domains = [iri for iri in prop["domain"] if iri in selected_iris]
        ranges = [iri for iri in prop["range"] if iri in selected_iris]
        if (domains and ranges) or (include_partial_relationships and (domains or ranges)):
            relevant.append({
                "label": prop["label"], "type": local_name(prop["iri"]).upper(), "iri": prop["iri"],
                "domain": prop["domain"], "range": prop["range"], "inverses": prop["inverses"],
            })
    return {
        "source": str(owl_path), "selected_class_count": len(selected),
        "selected_relationship_count": len(relevant), "missing_classes": missing,
        "instructions": [
            "Use only the supplied classes and relationships.",
            "Preserve the canonical OWL IRIs.",
            "Do not invent classes, properties, or relationships.",
            "Return unsupported or ambiguous statements as unresolved candidates.",
        ],
        "classes": selected, "relationships": relevant,
    }


def human_context(context: dict) -> str:
    lines = ["Ontology extraction context from business.owl", f"Selected classes: {context['selected_class_count']}", f"Relevant relationships: {context['selected_relationship_count']}", "", "Allowed classes:"]
    for item in context["classes"]:
        lines.append(f"- {item['label']} [IRI: {item['iri']}]")
        if item["definition"]:
            lines.append(f"  Definition: {item['definition']}")
    lines.append("\nAllowed relationships:")
    for item in context["relationships"]:
        lines.append(f"- {item['label']} ({item['type']}) [IRI: {item['iri']}]; domain: {', '.join(item['domain'])}; range: {', '.join(item['range'])}")
    lines.extend(["\nInstructions:", *[f"- {value}" for value in context["instructions"]]])
    if context["missing_classes"]:
        lines.extend(["\nMissing selected classes:", *[f"- {value}" for value in context["missing_classes"]]])
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--owl", type=Path, default=DEFAULT_OWL)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args()
    context = build_context(args.owl)
    output = json.dumps(context, indent=2, ensure_ascii=False) + "\n" if args.format == "json" else human_context(context)
    if args.output:
        args.output.write_text(output, encoding="utf-8")
    else:
        print(output, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
