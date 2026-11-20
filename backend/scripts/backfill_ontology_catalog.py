"""Backfill ontology classes and hierarchy without rerunning LLM extraction."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from langchain_neo4j import Neo4jGraph
from dotenv import load_dotenv

SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPT_DIR.parent
sys.path.insert(0, str(BACKEND_DIR))
load_dotenv(BACKEND_DIR / ".env")

from src.ontology_registry.reasoner import (  # noqa: E402
    ontology_catalog_from_reasoner,
    reason_over_all_local_ontologies,
)
from src.ontology_registry.repository import OntologyRepository  # noqa: E402
from src.shared.common_fn import save_ontology_catalog_in_neo4j  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", default="backend/src/Ontology/manifest.yaml")
    parser.add_argument("--uri", default=os.getenv("NEO4J_URI"))
    parser.add_argument("--username", default=os.getenv("NEO4J_USERNAME"))
    parser.add_argument("--password", default=os.getenv("NEO4J_PASSWORD"))
    parser.add_argument("--database", default=os.getenv("NEO4J_DATABASE"))
    args = parser.parse_args()
    missing = [name for name, value in (("--uri", args.uri), ("--username", args.username), ("--password", args.password)) if not value]
    if missing:
        parser.error(f"missing Neo4j connection values: {', '.join(missing)}")

    repository = OntologyRepository.from_manifest(args.manifest)
    ontologies = reason_over_all_local_ontologies(repository)
    rows = ontology_catalog_from_reasoner(ontologies)
    graph = Neo4jGraph(
        url=args.uri,
        username=args.username,
        password=args.password,
        database=args.database,
        refresh_schema=False,
        sanitize=True,
    )
    save_ontology_catalog_in_neo4j(graph, rows)
    print(f"Synchronized {len(rows)} ontology hierarchy rows without LLM extraction.")


if __name__ == "__main__":
    main()
