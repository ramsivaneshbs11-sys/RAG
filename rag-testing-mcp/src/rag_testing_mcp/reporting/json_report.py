"""
JSON report generator.
"""

from __future__ import annotations

import json
from pathlib import Path

from rag_testing_mcp.models import EvaluationRun


def save_json_report(run: EvaluationRun, output_dir: Path) -> Path:
    """Save the full evaluation run as a structured JSON file."""
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{run.run_id}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(run.model_dump(), f, indent=2, default=str)
    return path
