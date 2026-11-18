#!/usr/bin/env python3
"""Validate IRIs in ontology profile YAML files against local RDF/OWL files."""

from __future__ import annotations

import argparse
from pathlib import Path
from urllib.parse import urlsplit

import yaml
from rdflib import Graph


def local_iris(ontology_root: Path) -> set[str]:
    values: set[str] = set()
    for suffix in ("*.rdf", "*.owl", "*.ttl"):
        for path in sorted(ontology_root.rglob(suffix)):
            graph = Graph()
            graph.parse(path)
            for subject, predicate, obj in graph:
                values.update(str(value) for value in (subject, predicate, obj) if str(value).startswith(("http://", "https://", "urn:")))
    return values


def is_iri(value: str) -> bool:
    parsed = urlsplit(value)
    return bool(parsed.scheme and (parsed.netloc or parsed.scheme == "urn"))


def profile_iris(path: Path):
    for document in yaml.compose_all(path.read_text(encoding="utf-8")):
        if document is None:
            continue
        stack = [document]
        while stack:
            node = stack.pop()
            if isinstance(node, yaml.MappingNode):
                for key, value in node.value:
                    key_name = str(key.value).casefold() if isinstance(key, yaml.ScalarNode) else ""
                    if (
                        isinstance(value, yaml.ScalarNode)
                        and isinstance(value.value, str)
                        and ("iri" in key_name or value.value.startswith(("http://", "https://", "urn:")))
                    ):
                        yield value.value, value.start_mark.line + 1
                    stack.append(value)
                    stack.append(key)
            elif isinstance(node, yaml.SequenceNode):
                stack.extend(node.value)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--profiles",
        type=Path,
        default=Path("backend/src/Ontology/profiles/Industrial_Ontologies_Foundry"),
    )
    parser.add_argument("--ontologies", type=Path, default=Path("backend/src/Ontology/ontologies"))
    args = parser.parse_args()

    known = local_iris(args.ontologies)
    issues = 0
    for path in sorted(args.profiles.rglob("*.yaml")):
        for iri, line in profile_iris(path):
            if not is_iri(iri):
                print(f"{path}:{line}: invalid IRI syntax: {iri}")
                issues += 1
            elif iri not in known:
                print(f"{path}:{line}: IRI not found in local RDF/OWL files: {iri}")
                issues += 1

    if issues:
        print(f"Found {issues} invalid or unknown IRI(s).")
        return 1
    print("All profile IRIs are valid and found in the local RDF/OWL files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
