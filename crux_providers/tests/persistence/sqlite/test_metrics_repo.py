"""Metrics repository aggregation and recent errors tests."""
from __future__ import annotations

from crux_providers.persistence.sqlite.repos import MetricsRepoSqlite
from crux_providers.persistence.interfaces.repos import MetricEntry


def test_metrics_repo_aggregate_and_recent_errors(conn):
    """Validate aggregate latency and recent_errors filter behavior."""
    metrics = MetricsRepoSqlite(conn)

    entries = [
        MetricEntry(
            provider="openai",
            model="gpt-4o-mini",
            latency_ms=120,
            tokens_prompt=10,
            tokens_completion=50,
            success=True,
            error_code=None,
            created_at="2025-01-01 00:00:00",
        ),
        MetricEntry(
            provider="openai",
            model="gpt-4o-mini",
            latency_ms=80,
            tokens_prompt=None,
            tokens_completion=None,
            success=False,
            error_code="Timeout",
            created_at="2025-01-01 00:00:01",
        ),
        MetricEntry(
            provider="openai",
            model="gpt-4o-mini",
            latency_ms=100,
            tokens_prompt=5,
            tokens_completion=20,
            success=True,
            error_code=None,
            created_at="2025-01-01 00:00:02",
        ),
    ]
    for e in entries:
        metrics.add_metric(e)
    conn.commit()

    count, avg = metrics.aggregate_latency("openai")
    assert count == 3  # nosec B101
    assert 99 <= avg <= 101  # approximate average  # nosec B101

    errors = list(metrics.recent_errors(limit=10))
    assert len(errors) == 1  # nosec B101
    assert errors[0].error_code == "Timeout"  # nosec B101


def test_metrics_repo_summary(conn):
    """Validate the shape and counts returned by summary()."""
    metrics = MetricsRepoSqlite(conn)

    entries = [
        MetricEntry(
            provider="openai",
            model="gpt-4o-mini",
            latency_ms=100,
            tokens_prompt=None,
            tokens_completion=None,
            success=True,
            error_code=None,
            created_at="2025-01-02 00:00:00",
        ),
        MetricEntry(
            provider="openai",
            model="gpt-4o-mini",
            latency_ms=150,
            tokens_prompt=None,
            tokens_completion=None,
            success=True,
            error_code=None,
            created_at="2025-01-02 00:00:01",
        ),
        MetricEntry(
            provider="anthropic",
            model="claude-3-sonnet",
            latency_ms=200,
            tokens_prompt=None,
            tokens_completion=None,
            success=True,
            error_code=None,
            created_at="2025-01-02 00:00:02",
        ),
    ]
    for e in entries:
        metrics.add_metric(e)
    conn.commit()

    summary = metrics.summary()
    assert summary["total"] == len(entries)  # nosec B101
    assert {row["provider"] for row in summary["by_provider"]} == {"openai", "anthropic"}  # nosec B101
    openai_row = next(r for r in summary["by_provider"] if r["provider"] == "openai")
    assert openai_row["count"] == 2  # nosec B101
    assert {row["model"] for row in summary["by_model"]} == {"gpt-4o-mini", "claude-3-sonnet"}  # nosec B101
