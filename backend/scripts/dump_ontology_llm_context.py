#!/usr/bin/env python3
"""Save the exact ontology-guided extraction context for inspection.

This script builds the same default ontology profile used by ``src.llm``. It
does not call a model, read a document, or connect to Neo4j.

Usage:
    PYTHONPATH=backend python backend/scripts/dump_ontology_llm_context.py
    PYTHONPATH=backend python backend/scripts/dump_ontology_llm_context.py --output /tmp/context.log
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

from src.ontology_registry import default_adapter
from src.shared.constants import ADDITIONAL_INSTRUCTIONS


def _environment_value(name: str, default: str = "") -> str:
    value = os.getenv(name)
    return value if value else default


def _environment_flag(name: str) -> bool:
    return _environment_value(name).strip().lower() in {"true", "1", "yes"}


def _format_relationship(relationship: tuple[str, str, str] | str) -> str:
    if isinstance(relationship, str):
        return f"{relationship} [YAML domain/range rule; see property details below]"
    source, predicate, target = relationship
    return f"{source} --[{predicate}]--> {target}"


def build_reference_context() -> str:
    ontology_guided = _environment_flag("ONTOLOGY_GUIDED_EXTRACTION")
    ontology_only = _environment_flag("ONTOLOGY_ONLY_MODE")
    ontology_enabled = ontology_guided or ontology_only
    lines = [
        "Ontology-guided LLM extraction context reference",
        f"Generated at: {datetime.now(timezone.utc).isoformat()}",
        f"Manifest: {_environment_value('ONTOLOGY_MANIFEST_PATH', 'default')}",
        f"Ontology root: {_environment_value('ONTOLOGY_ROOT_ID', 'business')}",
        f"Ontology-guided extraction: {_environment_value('ONTOLOGY_GUIDED_EXTRACTION', 'false')}",
        f"Ontology-only mode: {_environment_value('ONTOLOGY_ONLY_MODE', 'false')}",
        "",
        "=== Global graph extraction instructions ===",
        ADDITIONAL_INSTRUCTIONS,
    ]
    if ontology_enabled:
        profile = default_adapter().build()
        context = json.loads(profile.prompt_context.split("\n", 1)[1])
        lines.extend([
            "",
            "=== Allowed node labels ===",
            *profile.allowed_nodes,
            "",
            "=== Allowed relationships and YAML relationship rules ===",
            *(_format_relationship(item) for item in profile.allowed_relationships),
            "",
            "=== Human-readable ontology allowlist ===",
            "Classes:",
        ])
        for item in context["classes"]:
            lines.extend([
                f"- {item['label']}",
                f"  IRI: {item['iri']}",
                f"  Layer: {item.get('layer')}",
                f"  Parents: {', '.join(item.get('parents', [])) or '(none)'}",
                f"  Ancestors: {', '.join(item.get('ancestors', [])) or '(none)'}",
            ])
        lines.append("Properties:")
        for item in context["properties"]:
            lines.extend([
                f"- {item['label']}",
                f"  IRI: {item['iri']}",
                f"  Layer: {item.get('layer')}",
                f"  Domain: {', '.join(item.get('domain', [])) or '(unrestricted)'}",
                f"  Range: {', '.join(item.get('range', [])) or '(unrestricted)'}",
                f"  Inverses: {', '.join(item.get('inverses', [])) or '(none)'}",
            ])
        lines.extend([
            "",
            "=== Raw ontology extraction context (JSON) ===",
            profile.prompt_context,
            "",
            "=== Effective instruction order ===",
            "1. Global graph extraction instructions",
            "2. Ontology context and safety instructions",
            "3. User-provided additional extraction instructions, when supplied",
            "4. The document chunk supplied as the transformer input",
        ])
    else:
        lines.extend([
            "",
            "=== Ontology context ===",
            "NOT SENT: ontology-guided extraction and ontology-only mode are both disabled.",
            "The live runtime uses the legacy compatibility extraction path when configured.",
        ])
    lines.extend([
        "",
        "Note: this file is a reference dump. It is not itself sent as a separate request; the runtime passes these instruction components to LLMGraphTransformer.",
    ])
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path,
        default=Path("logs/ontology-llm-context.log"),
        help="Output log path (default: logs/ontology-llm-context.log)",
    )
    parser.add_argument(
        "--env-file", type=Path,
        help="Optional dotenv file to load before reading flags, e.g. backend/.env",
    )
    args = parser.parse_args()
    if args.env_file:
        load_dotenv(args.env_file, override=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(build_reference_context(), encoding="utf-8")
    print(f"Saved ontology LLM context reference to {args.output.resolve()}")


if __name__ == "__main__":
    main()
