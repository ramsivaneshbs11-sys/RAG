"""
Routing and cache performance evaluator.

Analyses the routing distribution (cache / qdrant / web / hybrid)
and detects unnecessary web-search usage.
"""

from __future__ import annotations

from rag_testing_mcp.models import (
    RAGQueryResponse,
    DatasetItem,
    RoutingStats,
    FailureRecord,
    FailureType,
)


def evaluate_routing(
    responses: list[tuple[RAGQueryResponse, DatasetItem]],
) -> tuple[RoutingStats, list[FailureRecord]]:
    """Evaluate routing distribution and cache performance across a batch.

    Args:
        responses: list of (response, dataset_item) tuples.

    Returns (routing_stats, failures).
    """
    failures: list[FailureRecord] = []

    if not responses:
        return RoutingStats(status="not_available"), failures

    distribution: dict[str, int] = {}
    cache_hits = 0
    cache_misses = 0
    unnecessary_web = 0

    for resp, item in responses:
        routing = resp.routing or "unknown"
        distribution[routing] = distribution.get(routing, 0) + 1

        if resp.cache_hit:
            cache_hits += 1
        else:
            cache_misses += 1

        # Detect unnecessary web searches:
        # If mode is prelims/mains (textbook query) but routing went to web
        if item.mode in ("prelims", "mains") and "web" in routing.lower():
            unnecessary_web += 1
            failures.append(FailureRecord(
                question_id=item.id,
                failure_type=FailureType.ROUTING_FAILURE,
                reason=(
                    f"Textbook query (mode={item.mode}) was routed to web search "
                    f"(routing={routing}). Expected Qdrant vector search."
                ),
            ))

    total = len(responses)
    hit_rate = round(cache_hits / total, 4) if total > 0 else None

    return (
        RoutingStats(
            total_queries=total,
            routing_distribution=distribution,
            cache_hits=cache_hits,
            cache_misses=cache_misses,
            cache_hit_rate=hit_rate,
            unnecessary_web_searches=unnecessary_web,
        ),
        failures,
    )
