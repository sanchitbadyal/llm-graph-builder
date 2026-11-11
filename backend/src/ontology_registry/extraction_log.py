"""Persistent JSONL logging for ontology extraction envelopes."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
from typing import Any

from .envelope import OntologyExtractionEnvelope


def write_extraction_log(
    envelope: OntologyExtractionEnvelope, *, source_name: str, stage: str,
    report: dict[str, Any] | None = None, path: str | Path | None = None,
) -> Path:
    """Append one structured extraction event and return the log path."""
    configured_path = os.getenv("ONTOLOGY_EXTRACTION_LOG")
    default_path = Path(__file__).resolve().parents[3] / "logs" / "ontology-extraction.log"
    log_path = Path(path or configured_path or default_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).isoformat()
    event = {
        "timestamp": timestamp,
        "source_name": source_name,
        "stage": stage,
        "report": report or {},
        "envelope": envelope.as_dict(),
    }
    with log_path.open("a", encoding="utf-8") as stream:
        stream.write("\n" + "=" * 100 + "\n")
        stream.write("ONTOLOGY EXTRACTION EVENT\n")
        stream.write("=" * 100 + "\n")
        stream.write(f"Timestamp: {timestamp}\n")
        stream.write(f"Source: {source_name}\n")
        stream.write(f"Stage: {stage}\n\n")
        stream.write("Validation report:\n")
        stream.write(json.dumps(report or {}, indent=2, ensure_ascii=False) + "\n\n")
        stream.write("Extraction envelope:\n")
        stream.write(json.dumps(envelope.as_dict(), indent=2, ensure_ascii=False) + "\n")
        stream.write("-" * 100 + "\n")
    return log_path
