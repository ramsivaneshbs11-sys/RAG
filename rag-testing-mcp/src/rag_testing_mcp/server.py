"""
RAG Testing MCP Server — FastMCP implementation.

Registers 11 MCP tools for evaluating, benchmarking, and auditing
a live RAG application.  Transport: stdio (default).

Usage:
    python -m rag_testing_mcp.server        # starts the MCP server
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from mcp.server.fastmcp import FastMCP

from rag_testing_mcp.config import get_settings, Settings
from rag_testing_mcp.models import (
    DatasetItem,
    RAGQueryResponse,
)
from rag_testing_mcp.clients.rag_client import RAGClient
from rag_testing_mcp.runners.single import run_single
from rag_testing_mcp.runners.dataset import run_dataset
from rag_testing_mcp.runners.comparison import compare_versions
from rag_testing_mcp.evaluators.retrieval import evaluate_retrieval
from rag_testing_mcp.evaluators.generation import evaluate_generation
from rag_testing_mcp.evaluators.citation import evaluate_citations
from rag_testing_mcp.evaluators.latency import calculate_latency
from rag_testing_mcp.evaluators.routing import evaluate_routing
from rag_testing_mcp.reporting.json_report import save_json_report
from rag_testing_mcp.reporting.csv_report import save_csv_report
from rag_testing_mcp.reporting.html_report import save_html_report
from rag_testing_mcp.evaluators.frontend import test_frontend_ui

logger = logging.getLogger(__name__)

# ── Create the FastMCP server ──────────────────────────────────────────
mcp = FastMCP(
    "rag-testing",
    description=(
        "RAG Testing MCP Server — evaluates retrieval quality, answer faithfulness, "
        "citation correctness, latency, routing, and cache performance of a live RAG API."
    ),
)


def _settings() -> Settings:
    return get_settings()


def _client(settings: Settings | None = None) -> RAGClient:
    return RAGClient(settings or _settings())


# ════════════════════════════════════════════════════════════════════════
# Tool 1: rag_health_check
# ════════════════════════════════════════════════════════════════════════

@mcp.tool()
async def rag_health_check() -> dict[str, Any]:
    """Check whether the RAG API is running.

    Returns status, URL, response time, and useful error information.
    """
    client = _client()
    result = await client.health_check()
    await client.close()
    return result


# ════════════════════════════════════════════════════════════════════════
# Tool 1.5: rag_warmup
# ════════════════════════════════════════════════════════════════════════

@mcp.tool()
async def rag_warmup() -> dict[str, Any]:
    """Pre-warm the RAG embedding and reranker models.

    Run this BEFORE rag_run_dataset or rag_measure_latency to avoid
    cold-start inflation. The BGE embedding model and cross-encoder
    reranker load on the first query; this query pre-loads them so
    subsequent evaluation queries get accurate latency readings.
    """
    client = _client()
    result = await client.warmup_query()
    await client.close()
    return result


# ════════════════════════════════════════════════════════════════════════
# Tool 2: rag_run_query
# ════════════════════════════════════════════════════════════════════════

@mcp.tool()
async def rag_run_query(
    question: str,
    mode: str = "prelims",
    sub_mode: str = "summary",
    top_k: int = 5,
) -> dict[str, Any]:
    """Run one question against the actual RAG API.

    Returns the full response including answer, sources, retrieved chunks,
    latency, and metadata.  Fields that are unavailable are set to 'not_available'.
    """
    client = _client()
    resp = await client.run_query(question, mode=mode, sub_mode=sub_mode, top_k=top_k)
    await client.close()
    return resp.model_dump()


# ════════════════════════════════════════════════════════════════════════
# Tool 3: rag_test_retrieval
# ════════════════════════════════════════════════════════════════════════

@mcp.tool()
async def rag_test_retrieval(
    question: str,
    expected_sources: list[str] | None = None,
    expected_pages: list[int] | None = None,
    mode: str = "prelims",
) -> dict[str, Any]:
    """Evaluate retrieval quality for a single question.

    Calculates Recall@1, Recall@3, Recall@5, Precision@K, and MRR.
    Provide expected_sources and/or expected_pages for comparison.
    """
    client = _client()
    resp = await client.run_query(question, mode=mode)
    await client.close()
    item = DatasetItem(
        id="manual",
        question=question,
        expected_sources=expected_sources,
        expected_pages=expected_pages,
        mode=mode,
    )
    metrics = evaluate_retrieval(resp, item)
    return metrics.model_dump()


# ════════════════════════════════════════════════════════════════════════
# Tool 4: rag_evaluate_answer
# ════════════════════════════════════════════════════════════════════════

@mcp.tool()
async def rag_evaluate_answer(
    question: str,
    reference_answer: str | None = None,
    mode: str = "prelims",
) -> dict[str, Any]:
    """Evaluate answer quality: relevance, faithfulness, groundedness, hallucination risk.

    Distinguishes FACTUALLY CORRECT from SUPPORTED BY RETRIEVED CONTEXT.
    A correct statement not backed by retrieved sources is flagged as a grounding problem.
    """
    client = _client()
    resp = await client.run_query(question, mode=mode)
    await client.close()
    item = DatasetItem(id="manual", question=question, reference_answer=reference_answer, mode=mode)
    metrics, failures = evaluate_generation(resp, item)
    return {
        "metrics": metrics.model_dump(),
        "failures": [f.model_dump() for f in failures],
        "answer": resp.answer,
        "answered": resp.answered,
        "gated": resp.gated,
    }


# ════════════════════════════════════════════════════════════════════════
# Tool 5: rag_check_citation
# ════════════════════════════════════════════════════════════════════════

@mcp.tool()
async def rag_check_citation(
    question: str,
    expected_sources: list[str] | None = None,
    mode: str = "prelims",
) -> dict[str, Any]:
    """Check whether citations/sources in the answer actually support the claims.

    Returns citation_score, supported_claims, unsupported_claims, and missing_sources.
    """
    client = _client()
    resp = await client.run_query(question, mode=mode)
    await client.close()
    item = DatasetItem(id="manual", question=question, expected_sources=expected_sources, mode=mode)
    metrics, failures = evaluate_citations(resp, item)
    return {
        "metrics": metrics.model_dump(),
        "failures": [f.model_dump() for f in failures],
    }


# ════════════════════════════════════════════════════════════════════════
# Tool 6: rag_run_dataset
# ════════════════════════════════════════════════════════════════════════

@mcp.tool()
async def rag_run_dataset(dataset_path: str) -> dict[str, Any]:
    """Run an entire evaluation dataset against the RAG API.

    One failed question does NOT stop the whole run.
    Results are stored in evaluation/results/.

    Supports JSON and CSV dataset formats.
    """
    settings = _settings()
    run = await run_dataset(settings, dataset_path)

    # Save reports
    results_dir = settings.results_dir
    json_path = save_json_report(run, results_dir)
    csv_path = save_csv_report(run, results_dir)
    html_path = save_html_report(run, results_dir)

    summary = run.model_dump()
    summary["report_files"] = {
        "json": str(json_path),
        "csv": str(csv_path),
        "html": str(html_path),
    }
    # Remove verbose per-question results from the MCP response
    # (they are in the report files)
    summary.pop("results", None)
    return summary


# ════════════════════════════════════════════════════════════════════════
# Tool 7: rag_measure_latency
# ════════════════════════════════════════════════════════════════════════

@mcp.tool()
async def rag_measure_latency(
    questions: list[str],
    mode: str = "prelims",
) -> dict[str, Any]:
    """Measure latency distribution across multiple queries.

    Returns Average, Median, P95, P99, Min, Max.
    Never invents unavailable timings.
    """
    client = _client()
    timings: list[float] = []
    for q in questions:
        resp = await client.run_query(q, mode=mode)
        if resp.latency_ms > 0:
            timings.append(resp.latency_ms)
    await client.close()
    stats = calculate_latency(timings)
    return stats.model_dump()


# ════════════════════════════════════════════════════════════════════════
# Tool 8: rag_compare
# ════════════════════════════════════════════════════════════════════════

@mcp.tool()
async def rag_compare(
    url_a: str,
    url_b: str,
    dataset_path: str,
) -> dict[str, Any]:
    """Compare two RAG versions using the exact same dataset.

    Compares retrieval, answer quality, faithfulness, citation, latency,
    errors, cache hits, and web searches.
    Does NOT select a winner using only one metric.
    """
    settings = _settings()
    result = await compare_versions(settings, url_a, url_b, dataset_path)
    return result.model_dump()


# ════════════════════════════════════════════════════════════════════════
# Tool 9: rag_check_cache
# ════════════════════════════════════════════════════════════════════════

@mcp.tool()
async def rag_check_cache() -> dict[str, Any]:
    """Check cache performance metrics from the RAG API.

    Returns cache hit count, miss count, and hit rate if available.
    If unavailable, reports cache_metrics: unavailable.  Never guesses.
    """
    client = _client()
    stats = await client.get_cache_stats()
    await client.close()
    return stats


# ════════════════════════════════════════════════════════════════════════
# Tool 10: rag_check_retrieval_router
# ════════════════════════════════════════════════════════════════════════

@mcp.tool()
async def rag_check_retrieval_router(
    questions: list[str],
    modes: list[str] | None = None,
) -> dict[str, Any]:
    """Analyse retrieval routing distribution across queries.

    Identifies routing paths (cache, qdrant, web, hybrid) and detects
    unnecessary web-search usage for textbook queries.
    """
    client = _client()
    pairs = []
    for i, q in enumerate(questions):
        mode = modes[i] if modes and i < len(modes) else "prelims"
        resp = await client.run_query(q, mode=mode)
        item = DatasetItem(id=f"rt_{i}", question=q, mode=mode)
        pairs.append((resp, item))
    await client.close()

    stats, failures = evaluate_routing(pairs)
    return {
        "stats": stats.model_dump(),
        "failures": [f.model_dump() for f in failures],
    }


# ════════════════════════════════════════════════════════════════════════
# Tool 11: rag_generate_report
# ════════════════════════════════════════════════════════════════════════

@mcp.tool()
async def rag_generate_report(dataset_path: str) -> dict[str, Any]:
    """Run dataset evaluation and generate JSON, CSV, and HTML reports.

    Reports include: Executive Summary, Retrieval Metrics, Generation Metrics,
    Faithfulness, Answer Relevance, Citation Accuracy, Latency, Cache Performance,
    Web Search Usage, Error Analysis, Failed/Worst/Best Questions, Recommendations,
    and Overall Assessment.
    """
    settings = _settings()
    run = await run_dataset(settings, dataset_path)

    results_dir = settings.results_dir
    json_path = save_json_report(run, results_dir)
    csv_path = save_csv_report(run, results_dir)
    html_path = save_html_report(run, results_dir)

    return {
        "run_id": run.run_id,
        "total_questions": run.total_questions,
        "successful": run.successful,
        "failed": run.failed,
        "error_count": run.error_count,
        "total_failures": len(run.failures),
        "report_files": {
            "json": str(json_path),
            "csv": str(csv_path),
            "html": str(html_path),
        },
        "retrieval_summary": run.retrieval_summary.model_dump(),
        "generation_summary": run.generation_summary.model_dump(),
        "latency": run.latency.model_dump(),
        "routing": run.routing.model_dump(),
    }


# ════════════════════════════════════════════════════════════════════════
# Tool 12: rag_test_frontend
# ════════════════════════════════════════════════════════════════════════

@mcp.tool()
async def rag_test_frontend(
    frontend_url: str = "http://localhost:5173/home",
    test_question: str = "What is cultural ecology?",
    timeout_ms: int = 45000,
) -> dict[str, Any]:
    """Automate end-to-end browser testing of the live React/Vite chatbot UI.

    Uses Playwright (Chromium) to:
      1. Verify Page Load & HTTP status
      2. Validate Core DOM Structure & Input elements
      3. Verify Tab Navigation (MCQ, News, Chat)
      4. Test Chat Mode Switcher (Prelims / Mains)
      5. Perform End-to-End Chat Query & verify real-time response rendering
      6. Capture full-page screenshot and measure UI latency
    """
    settings = _settings()
    screenshots_dir = Path(settings.results_dir) / "screenshots"
    return await test_frontend_ui(
        frontend_url=frontend_url,
        test_question=test_question,
        screenshot_dir=screenshots_dir,
        timeout_ms=timeout_ms,
    )


# ── Entry point ────────────────────────────────────────────────────────

def main():
    """Start the MCP server on stdio transport."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
