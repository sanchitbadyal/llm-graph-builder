#!/usr/bin/env python3
"""Build an LLM context from selected classes in order-to-cash.owl."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import build_business_owl_llm_context as owl_context  # noqa: E402


SELECTED_CLASSES = (
    "Credit Check",
    "Discount Approval",
    "Invoice",
    "Escalation Path",
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--owl", type=Path,
        default=Path(__file__).resolve().parents[1] / "src/Ontology/order-to-cash.owl",
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args()

    owl_context.SELECTED_CLASSES = SELECTED_CLASSES
    context = owl_context.build_context(args.owl, include_partial_relationships=True)
    output = (
        json.dumps(context, indent=2, ensure_ascii=False) + "\n"
        if args.format == "json"
        else owl_context.human_context(context)
    )
    if args.output:
        args.output.write_text(output, encoding="utf-8")
    else:
        print(output, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
