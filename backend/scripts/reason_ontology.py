#!/usr/bin/env python3
"""Run optional Owlready2/HermiT reasoning for a manifest ontology profile."""

from __future__ import annotations

import argparse
from pathlib import Path

from src.ontology_registry import OntologyRepository
from src.ontology_registry.reasoner import reason_over_ontology


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--manifest",
        default="backend/src/Ontology/manifest.yaml",
        help="Path to the ontology manifest",
    )
    parser.add_argument("--root", default=None, help="Check one manifest artifact id")
    args = parser.parse_args()

    repository = OntologyRepository.from_manifest(Path(args.manifest))
    root_ids = [args.root] if args.root else [
        "business",
        "manufacturing",
        "order-to-cash",
        "plant-fulfillment",
        "revenue-recognition",
    ]

    for root_id in root_ids:
        root = reason_over_ontology(repository, root_id)
        print(f"Reasoned ontology: {root_id} ({root.base_iri or root.name})")
        print(f"Classes: {len(list(root.classes()))}")
        print(f"Object properties: {len(list(root.object_properties()))}")


if __name__ == "__main__":
    main()
