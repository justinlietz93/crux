"""Focused tests for ProviderInvocationCounters behavior.

Covers lifecycle counters, latency aggregation, failure code bucketing,
snapshot reset semantics, and the monotonic_ms helper.
"""
from __future__ import annotations

from crux_providers.base.metrics import ProviderInvocationCounters


def test_counters_lifecycle_and_latency_aggregation():
    c = ProviderInvocationCounters(provider="openai")

    c.record_start()
    # Simulate retry
    c.record_retry()
    c.record_start()

    # one success with latency
    c.record_success(latency_ms=120)
    # one failure with latency and classification code
    c.record_failure("RATE_LIMIT", latency_ms=80)
    # one cancellation and one timeout
    c.record_cancelled()
    c.record_timeout()

    snap = c.snapshot(reset=False)
    assert snap.provider == "openai"
    assert snap.total == 2  # two starts
    assert snap.retry == 1
    assert snap.success == 1
    assert snap.failure == 1
    assert snap.cancelled == 1
    assert snap.timeout == 1
    assert snap.in_flight == 0
    assert snap.failure_by_code.get("RATE_LIMIT") == 1

    # latency: min=80, max=120, total=200, count=2, avg=100
    lat = snap.latency
    assert lat.count == 2 and lat.total_ms == 200
    assert lat.min_ms == 80 and lat.max_ms == 120
    assert abs((lat.avg_ms or 0) - 100.0) < 1e-9


def test_snapshot_reset_zeroes_counters_but_preserves_inflight():
    c = ProviderInvocationCounters(provider="anthropic")
    c.record_start()
    # leave one in-flight, then take snapshot with reset
    snap = c.snapshot(reset=True)
    assert snap.total == 1 and snap.in_flight == 1
    # after reset, counters are zero but in-flight remains 1 until terminal event
    after = c.snapshot(reset=False)
    assert after.total == 0 and after.in_flight == 1
    # finalize the in-flight
    c.record_success(latency_ms=10)
    final = c.snapshot(reset=False)
    assert final.in_flight == 0 and final.success == 1 and final.total == 0


def test_monotonic_ms_is_non_decreasing():
    c = ProviderInvocationCounters(provider="xai")
    a = c.monotonic_ms()
    b = c.monotonic_ms()
    assert isinstance(a, int) and isinstance(b, int)
    assert b >= a
