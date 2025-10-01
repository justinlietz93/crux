from __future__ import annotations

from datetime import datetime

from crux_providers.persistence.sqlite.engine import create_connection, init_schema  # type: ignore  # pragma: no cover
from crux_providers.persistence.interfaces import MetricEntry  # type: ignore  # pragma: no cover
from crux_providers.persistence.sqlite.repos import MetricsRepoSqlite  # type: ignore  # pragma: no cover
from crux_providers.tests.utils import assert_true

_assert = assert_true


def test_naive_metric_datetime_coerced_and_aware_on_read() -> None:
    conn = create_connection(":memory:")
    init_schema(conn)
    repo = MetricsRepoSqlite(conn)

    naive_dt = datetime(2025, 9, 17, 10, 30, 0)  # naive
    entry = MetricEntry(
        provider="openai",
        model="gpt-4",
        latency_ms=123,
        tokens_prompt=None,
        tokens_completion=None,
        success=False,
        error_code="ERR",
        created_at=naive_dt,
    )
    repo.add_metric(entry)

    # Use recent_errors to fetch the entry
    errors = list(repo.recent_errors(limit=5))
    _assert(len(errors) == 1, f"Expected one error metric: {errors}")
    fetched = errors[0]
    _assert(fetched.created_at.tzinfo is not None, f"Timestamp not tz-aware: {fetched.created_at}")
    # Ensure either identical instant when coerced or same date/time components
    _assert(
        fetched.created_at.replace(tzinfo=None) == naive_dt,
        f"Coerced datetime mismatch: {fetched.created_at} vs {naive_dt}",
    )
    # Ensure string form matches ISO (contains 'T' and timezone offset or 'Z')
    iso_str = fetched.created_at.isoformat()
    _assert("T" in iso_str, f"ISO formatting missing 'T': {iso_str}")
    _assert(iso_str.endswith("+00:00") or iso_str.endswith("Z"), f"Not UTC timezone: {iso_str}")
    # Explicitly close the SQLite connection to avoid ResourceWarning
    conn.close()
