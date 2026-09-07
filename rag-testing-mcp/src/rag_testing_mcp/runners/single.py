"""
Single test case runner.

Runs one question through the full evaluation pipeline:
  query → retrieval eval → generation eval → citation eval → result
"""

from __future__ import annotations

from rag_testing_mcp.models import (
    RAGQueryResponse,
    DatasetItem,
    QuestionResult,
    FailureRecord,
    FailureType,
)
from rag_testing_mcp.evaluators.retrieval import evaluate_retrieval
from rag_testing_mcp.evaluators.generation import evaluate_generation
from rag_testing_mcp.evaluators.citation import evaluate_citations
from rag_testing_mcp.clients.rag_client import RAGClient


async def run_single(
    client: RAGClient,
    item: DatasetItem,
) -> QuestionResult:
    """Execute and evaluate a single dataset question.

    Never raises — errors are captured into the QuestionResult.
    """
    all_failures: list[FailureRecord] = []

    try:
        response = await client.run_query(
            question=item.question,
            mode=item.mode,
            sub_mode=item.sub_mode,
        )
    except Exception as exc:
        return QuestionResult(
            id=item.id,
            question=item.question,
            error=f"API_FAILURE: {exc}",
            failures=[FailureRecord(
                question_id=item.id,
                failure_type=FailureType.API_FAILURE,
                reason=str(exc),
            )],
        )

    # Check for API-level error in the response
    if response.answer.startswith("API_ERROR:"):
        return QuestionResult(
            id=item.id,
            question=item.question,
            answer=response.answer,
            error=response.answer,
            latency_ms=response.latency_ms,
            failures=[FailureRecord(
                question_id=item.id,
                failure_type=FailureType.API_FAILURE,
                reason=response.answer,
            )],
        )

    # ── Evaluate retrieval ─────────────────────────────────────────────
    retrieval_metrics = evaluate_retrieval(response, item)

    # ── Evaluate generation / faithfulness ──────────────────────────────
    generation_metrics, gen_failures = evaluate_generation(response, item)
    all_failures.extend(gen_failures)

    # ── Evaluate citations ─────────────────────────────────────────────
    citation_metrics, cite_failures = evaluate_citations(response, item)
    all_failures.extend(cite_failures)

    # ── Latency failure check (tier-based) ────────────────────────────
    # Different routing paths have different expected latencies.
    # Note: RAG marks cache_hit=True on first write too, so allow up to 2s
    # for cache hits (genuine served-from-cache hits return in <100ms).
    if response.cache_hit:
        threshold_ms = 2_000      # cache_hit=True on write is ~1600ms; served hits <100ms
        tier = "cache_hit"
    elif "current_affairs" in (response.routing or ""):
        threshold_ms = 15_000     # current affairs: web search + rerank
        tier = "current_affairs"
    elif "cross_collection" in (response.routing or ""):
        threshold_ms = 10_000     # cross-collection fallback: 2 Qdrant queries
        tier = "cross_collection"
    else:
        threshold_ms = 8_000      # standard high_confidence: embed + rerank + LLM
        tier = "standard"

    if response.latency_ms > threshold_ms:
        sla_s = threshold_ms / 1000
        all_failures.append(FailureRecord(
            question_id=item.id,
            failure_type=FailureType.LATENCY_FAILURE,
            reason=(
                f"[{tier}] Response took {response.latency_ms:.0f}ms "
                f"(>{sla_s:.1f}s threshold for this routing path)."
            ),
        ))

    return QuestionResult(
        id=item.id,
        question=item.question,
        mode=response.mode,
        answer=response.answer,
        answered=response.answered,
        latency_ms=response.latency_ms,
        retrieval=retrieval_metrics,
        generation=generation_metrics,
        citation=citation_metrics,
        routing=response.routing,
        cache_hit=response.cache_hit,
        failures=all_failures,
    )
