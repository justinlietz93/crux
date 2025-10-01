"""
Tests for MetricsRepoSqlite.summary() shape and averages.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from crux_providers.persistence.sqlite.engine import init_schema
from crux_providers.persistence.sqlite.repos import UnitOfWorkSqlite
from crux_providers.persistence.interfaces.repos import MetricEntry


def _conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    init_schema(c)
    return c


def test_metrics_summary_shape_and_averages():
    conn = _conn()
    now = datetime.now(timezone.utc)
    data = [
        MetricEntry("openai", "gpt-4o", 100, 1, 2, True, None, now),
        MetricEntry("openai", "gpt-4o", 200, 1, 2, True, None, now),
        MetricEntry("openai", "gpt-4o-mini", 300, 1, 2, False, "timeout", now),
        MetricEntry("anthropic", "claude-3", 400, 1, 2, True, None, now),
    ]

    with UnitOfWorkSqlite(conn) as uow:
        for e in data:
            uow.metrics.add_metric(e)

    with UnitOfWorkSqlite(conn) as uow:
        summary = uow.metrics.summary()
        assert isinstance(summary, dict) # nosec B101 test assertion
        assert set(summary.keys()) == {"total", "by_provider", "by_model"} # nosec B101 test assertion
        assert summary["total"] == 4 # nosec B101 test assertion

        by_provider = {row["provider"]: row for row in summary["by_provider"]}
        assert by_provider["openai"]["count"] == 3 # nosec B101 test assertion
        # avg of 100,200,300 => 200.0
        assert abs(by_provider["openai"]["avg_ms"] - 200.0) < 0.001 # nosec B101 test assertion

        by_model = {row["model"]: row for row in summary["by_model"]}
        assert by_model["gpt-4o"]["count"] == 2 # nosec B101 test assertion
        assert abs(by_model["gpt-4o"]["avg_ms"] - 150.0) < 0.001 # nosec B101 test assertion
    # Close connection
    conn.close()
