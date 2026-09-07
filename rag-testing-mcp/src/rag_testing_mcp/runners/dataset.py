"""
Full dataset runner with controlled concurrency.

Key rules from the spec:
  - One failed question must NOT stop the entire run
  - Controlled concurrency via MAX_CONCURRENCY
  - Stores results in evaluation/results/
"""

from __future__ import annotations

import asyncio
import json
import csv
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from rag_testing_mcp.config import Settings
from rag_testing_mcp.models import (
    DatasetItem,
    EvaluationRun,
    QuestionResult,
    RetrievalMetrics,
    GenerationMetrics,
    FailureRecord,
)
from rag_testing_mcp.clients.rag_client import RAGClient
from rag_testing_mcp.runners.single import run_single
from rag_testing_mcp.evaluators.latency import calculate_latency
from rag_testing_mcp.evaluators.routing import evaluate_routing

logger = logging.getLogger(__name__)


def load_dataset(path: str) -> list[DatasetItem]:
    """Load evaluation dataset from JSON or CSV file."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Dataset not found: {path}")

    if p.suffix == ".json":
        with open(p, "r", encoding="utf-8") as f:
            raw = json.load(f)
        return [DatasetItem(**item) for item in raw]

    elif p.suffix == ".csv":
        items = []
        with open(p, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Handle expected_sources and expected_pages as JSON arrays
                if "expected_sources" in row and row["expected_sources"]:
                    try:
                        row["expected_sources"] = json.loads(row["expected_sources"])
                    except json.JSONDecodeError:
                        row["expected_sources"] = [row["expected_sources"]]
                if "expected_pages" in row and row["expected_pages"]:
                    try:
                        row["expected_pages"] = json.loads(row["expected_pages"])
                    except json.JSONDecodeError:
                        row["expected_pages"] = None
                items.append(DatasetItem(**row))
        return items

    else:
        raise ValueError(f"Unsupported dataset format: {p.suffix}. Use .json or .csv")


async def run_dataset(
    settings: Settings,
    dataset_path: str,
) -> EvaluationRun:
    """Run the full evaluation dataset with fault isolation and concurrency control."""
    items = load_dataset(dataset_path)
    client = RAGClient(settings)
    semaphore = asyncio.Semaphore(settings.max_concurrency)

    now = datetime.now(timezone.utc)
    run_id = now.strftime("run_%Y%m%d_%H%M%S")

    # ── Auto-warmup: pre-load BGE embedding + reranker models ─────────
    # This eliminates cold-start inflation on the first question's latency.
    logger.info(f"[{run_id}] Warming up models (BGE embedding + cross-encoder)...")
    await client.warmup_query()
    logger.info(f"[{run_id}] Warmup complete. Starting dataset evaluation of {len(items)} questions...")

    results: list[QuestionResult] = []

    async def _eval_one(item: DatasetItem) -> QuestionResult:
        async with semaphore:
            logger.info(f"[{run_id}] Evaluating: {item.id} — {item.question[:50]}")
            return await run_single(client, item)

    # Run all questions concurrently (with semaphore limiting)
    tasks = [_eval_one(item) for item in items]
    results = await asyncio.gather(*tasks)

    await client.close()

    # ── Aggregate metrics ──────────────────────────────────────────────
    all_failures: list[FailureRecord] = []
    timings: list[float] = []
    retrieval_scores: dict[str, list[float]] = {
        "recall_at_1": [], "recall_at_3": [], "recall_at_5": [],
        "precision_at_k": [], "mrr": [],
    }
    gen_scores: dict[str, list[float]] = {
        "answer_relevance": [], "faithfulness": [],
        "groundedness": [], "hallucination_risk": [],
    }
    routing_pairs = []

    successful = 0
    error_count = 0

    for r in results:
        all_failures.extend(r.failures)
        if r.error:
            error_count += 1
        else:
            successful += 1
        if r.latency_ms > 0:
            timings.append(r.latency_ms)

        # Collect retrieval metrics
        if r.retrieval.status == "evaluated":
            for key in retrieval_scores:
                val = getattr(r.retrieval, key)
                if val is not None:
                    retrieval_scores[key].append(val)

        # Collect generation metrics
        if r.generation.status == "evaluated":
            for key in gen_scores:
                val = getattr(r.generation, key)
                if val is not None:
                    gen_scores[key].append(val)

        # Collect routing info — need to reconstruct the response for routing eval
        # We just store routing and cache_hit from the result
        from rag_testing_mcp.models import RAGQueryResponse
        mock_resp = RAGQueryResponse(routing=r.routing, cache_hit=r.cache_hit)
        mock_item = DatasetItem(id=r.id, question=r.question, mode=r.mode)
        routing_pairs.append((mock_resp, mock_item))

    # Average metrics
    def _avg(vals: list[float]) -> float | None:
        return round(sum(vals) / len(vals), 4) if vals else None

    retrieval_summary = RetrievalMetrics(
        recall_at_1=_avg(retrieval_scores["recall_at_1"]),
        recall_at_3=_avg(retrieval_scores["recall_at_3"]),
        recall_at_5=_avg(retrieval_scores["recall_at_5"]),
        precision_at_k=_avg(retrieval_scores["precision_at_k"]),
        mrr=_avg(retrieval_scores["mrr"]),
        status="evaluated" if any(retrieval_scores.values()) else "not_available",
    )

    generation_summary = GenerationMetrics(
        answer_relevance=_avg(gen_scores["answer_relevance"]),
        faithfulness=_avg(gen_scores["faithfulness"]),
        groundedness=_avg(gen_scores["groundedness"]),
        hallucination_risk=_avg(gen_scores["hallucination_risk"]),
        status="evaluated" if any(gen_scores.values()) else "not_available",
    )

    latency_stats = calculate_latency(timings, results=list(results))
    routing_stats, routing_failures = evaluate_routing(routing_pairs)
    all_failures.extend(routing_failures)

    return EvaluationRun(
        run_id=run_id,
        timestamp=now.isoformat(),
        dataset_path=dataset_path,
        total_questions=len(items),
        successful=successful,
        failed=len(items) - successful,
        error_count=error_count,
        results=list(results),
        retrieval_summary=retrieval_summary,
        generation_summary=generation_summary,
        latency=latency_stats,
        routing=routing_stats,
        failures=all_failures,
    )
