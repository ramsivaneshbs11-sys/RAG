"""
Test suite for latency calculator and reporting.
"""

from rag_testing_mcp.evaluators.latency import calculate_latency


def test_empty_timings():
    stats = calculate_latency([])
    assert stats.status == "not_available"
    assert stats.sample_count == 0


def test_single_timing():
    stats = calculate_latency([500.0])
    assert stats.average_ms == 500.0
    assert stats.median_ms == 500.0
    assert stats.min_ms == 500.0
    assert stats.max_ms == 500.0
    assert stats.sample_count == 1


def test_multiple_timings():
    timings = [100.0, 200.0, 300.0, 400.0, 500.0, 600.0, 700.0, 800.0, 900.0, 1000.0]
    stats = calculate_latency(timings)
    assert stats.average_ms == 550.0
    assert stats.min_ms == 100.0
    assert stats.max_ms == 1000.0
    assert stats.sample_count == 10
    assert stats.p95_ms is not None
    assert stats.p99_ms is not None


def test_p95_calculation():
    timings = list(range(1, 101))  # 1 to 100
    stats = calculate_latency([float(t) for t in timings])
    assert stats.p95_ms >= 95.0
