"""
RAG A vs RAG B comparison runner.

Runs the same dataset against two RAG API URLs and produces
a side-by-side comparison.  Does not select a winner from a single metric.
"""

from __future__ import annotations

from rag_testing_mcp.config import Settings
from rag_testing_mcp.models import ComparisonResult
from rag_testing_mcp.runners.dataset import run_dataset


async def compare_versions(
    settings: Settings,
    url_a: str,
    url_b: str,
    dataset_path: str,
) -> ComparisonResult:
    """Run dataset against two RAG versions and compare results."""

    # Run against Version A
    settings_a = settings.model_copy()
    settings_a.rag_api_url = url_a
    run_a = await run_dataset(settings_a, dataset_path)

    # Run against Version B
    settings_b = settings.model_copy()
    settings_b.rag_api_url = url_b
    run_b = await run_dataset(settings_b, dataset_path)

    # Build comparison summary (multi-metric, no single-metric winner)
    summary = {
        "retrieval": {
            "version_a_mrr": run_a.retrieval_summary.mrr,
            "version_b_mrr": run_b.retrieval_summary.mrr,
            "version_a_recall_at_5": run_a.retrieval_summary.recall_at_5,
            "version_b_recall_at_5": run_b.retrieval_summary.recall_at_5,
        },
        "generation": {
            "version_a_faithfulness": run_a.generation_summary.faithfulness,
            "version_b_faithfulness": run_b.generation_summary.faithfulness,
            "version_a_answer_relevance": run_a.generation_summary.answer_relevance,
            "version_b_answer_relevance": run_b.generation_summary.answer_relevance,
            "version_a_hallucination_risk": run_a.generation_summary.hallucination_risk,
            "version_b_hallucination_risk": run_b.generation_summary.hallucination_risk,
        },
        "latency": {
            "version_a_avg_ms": run_a.latency.average_ms,
            "version_b_avg_ms": run_b.latency.average_ms,
            "version_a_p95_ms": run_a.latency.p95_ms,
            "version_b_p95_ms": run_b.latency.p95_ms,
        },
        "reliability": {
            "version_a_errors": run_a.error_count,
            "version_b_errors": run_b.error_count,
            "version_a_failures": len(run_a.failures),
            "version_b_failures": len(run_b.failures),
        },
        "cache": {
            "version_a_hit_rate": run_a.routing.cache_hit_rate,
            "version_b_hit_rate": run_b.routing.cache_hit_rate,
        },
        "web_searches": {
            "version_a_unnecessary": run_a.routing.unnecessary_web_searches,
            "version_b_unnecessary": run_b.routing.unnecessary_web_searches,
        },
    }

    return ComparisonResult(
        version_a_url=url_a,
        version_b_url=url_b,
        dataset_path=dataset_path,
        version_a=run_a,
        version_b=run_b,
        summary=summary,
    )
