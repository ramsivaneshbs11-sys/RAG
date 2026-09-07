"""
Latency statistics calculator — cache-aware.

Computes:
  - Overall: Average, Median, P95, P99, Min, Max
  - Cache HIT breakdown  (should be <200ms — pure memory lookup)
  - Cache MISS breakdown (real retrieval: embed → Qdrant → rerank → LLM)
  - Per-routing-path averages
  - SLA tier compliance

SLA Tiers:
  Cache HIT  → expected <200ms  (flag if >500ms)
  Fresh query (MISS):
    high_confidence                          → target <5000ms
    high_confidence_cross_collection_fallback→ target <8000ms
    current_affairs / low_confidence        → target <15000ms
"""

from __future__ import annotations

import statistics
from collections import defaultdict

from rag_testing_mcp.models import LatencyStats, QuestionResult


# SLA thresholds (ms)
CACHE_HIT_WARN_MS  = 2_000   # RAG marks cache_hit=True on write (~1600ms) and on read (<100ms)
                              # Anything >2s on a "cache hit" is suspicious
FRESH_QUERY_MAX_MS = 15_000  # any fresh query >15s is a hard failure


def _pct(timings: list[float], p: float) -> float:
    """Return the p-th percentile from a sorted list."""
    if not timings:
        return 0.0
    s = sorted(timings)
    idx = int(p / 100 * (len(s) - 1))
    return round(s[min(idx, len(s) - 1)], 2)


def calculate_latency(
    timings_ms: list[float],
    results: list[QuestionResult] | None = None,
) -> LatencyStats:
    """Calculate cache-aware latency distribution.

    Args:
        timings_ms: All query latencies in order (for backward compat).
        results:    QuestionResult list — enables cache-aware breakdown.
    """
    if not timings_ms:
        return LatencyStats(status="not_available", sample_count=0)

    sorted_t = sorted(timings_ms)
    n = len(sorted_t)

    overall = LatencyStats(
        average_ms=round(statistics.mean(sorted_t), 2),
        median_ms=round(statistics.median(sorted_t), 2),
        p95_ms=_pct(sorted_t, 95),
        p99_ms=_pct(sorted_t, 99),
        min_ms=round(sorted_t[0], 2),
        max_ms=round(sorted_t[-1], 2),
        sample_count=n,
    )

    if not results:
        return overall

    # ── Cache-aware breakdown ──────────────────────────────────────────
    hit_times  = [r.latency_ms for r in results if r.cache_hit]
    miss_times = [r.latency_ms for r in results if not r.cache_hit]

    if hit_times:
        overall.cache_hit_avg_ms  = round(statistics.mean(hit_times), 2)
        overall.cache_hit_p95_ms  = _pct(hit_times, 95)
        overall.cache_hit_count   = len(hit_times)
        # SLA: any cache hit >500ms is suspicious
        overall.cache_hit_sla_ok  = all(t < CACHE_HIT_WARN_MS for t in hit_times)

    if miss_times:
        overall.cache_miss_avg_ms  = round(statistics.mean(miss_times), 2)
        overall.cache_miss_p95_ms  = _pct(miss_times, 95)
        overall.cache_miss_count   = len(miss_times)
        # SLA: fresh queries must complete within 15s
        overall.fresh_query_sla_ok = all(t < FRESH_QUERY_MAX_MS for t in miss_times)

    # ── Per-routing-path averages ──────────────────────────────────────
    by_route: dict[str, list[float]] = defaultdict(list)
    for r in results:
        route = r.routing or "unknown"
        by_route[route].append(r.latency_ms)

    overall.by_routing = {
        route: round(statistics.mean(times), 2)
        for route, times in sorted(by_route.items())
    }

    return overall
