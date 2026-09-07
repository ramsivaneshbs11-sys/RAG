"""
CSV report generator.
"""

from __future__ import annotations

import csv
from pathlib import Path

from rag_testing_mcp.models import EvaluationRun


def save_csv_report(run: EvaluationRun, output_dir: Path) -> Path:
    """Save per-question results as a CSV file."""
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{run.run_id}.csv"

    fieldnames = [
        "id", "question", "mode", "answered", "latency_ms",
        "recall_at_1", "recall_at_3", "recall_at_5", "precision_at_k", "mrr",
        "answer_relevance", "faithfulness", "groundedness", "hallucination_risk",
        "citation_score", "routing", "cache_hit",
        "failure_count", "failure_types", "error",
    ]

    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in run.results:
            writer.writerow({
                "id": r.id,
                "question": r.question[:100],
                "mode": r.mode,
                "answered": r.answered,
                "latency_ms": r.latency_ms,
                "recall_at_1": r.retrieval.recall_at_1,
                "recall_at_3": r.retrieval.recall_at_3,
                "recall_at_5": r.retrieval.recall_at_5,
                "precision_at_k": r.retrieval.precision_at_k,
                "mrr": r.retrieval.mrr,
                "answer_relevance": r.generation.answer_relevance,
                "faithfulness": r.generation.faithfulness,
                "groundedness": r.generation.groundedness,
                "hallucination_risk": r.generation.hallucination_risk,
                "citation_score": r.citation.citation_score,
                "routing": r.routing,
                "cache_hit": r.cache_hit,
                "failure_count": len(r.failures),
                "failure_types": "; ".join(f.failure_type.value for f in r.failures),
                "error": r.error or "",
            })
    return path
