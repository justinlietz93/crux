from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from crux_providers.persistence.sqlite.repos import MetricsRepoSqlite  # type: ignore  # pragma: no cover
from crux_providers.persistence.interfaces.repos import MetricEntry  # type: ignore  # pragma: no cover
from crux_providers.tests.utils import assert_true

_assert = assert_true


def _conn_latency() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.execute(
        """CREATE TABLE metrics (
        provider TEXT, model TEXT, latency_ms INTEGER, tokens_prompt INTEGER,
        tokens_completion INTEGER, success INTEGER, error_code TEXT, created_at TEXT
        )"""
    )
    return conn


def _conn_duration() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.execute(
        """CREATE TABLE metrics (
        provider TEXT, model TEXT, duration_ms INTEGER, tokens_prompt INTEGER,
        tokens_completion INTEGER, success INTEGER, error_code TEXT, created_at TEXT
        )"""
    )
    return conn


def _add(repo: MetricsRepoSqlite, provider: str, model: str, latency: int, success: bool, err: str | None = None) -> None:
    repo.add_metric(
        MetricEntry(
            provider=provider,
            model=model,
            latency_ms=latency,
            tokens_prompt=10,
            tokens_completion=5,
            success=success,
            error_code=err,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
    )


def test_empty_summary_latency() -> None:
    conn = _conn_latency()
    repo = MetricsRepoSqlite(conn)
    summary = repo.summary()
    _assert(summary["total"] == 0, f"Expected total 0: {summary}")
    _assert(summary["by_provider"] == [], f"Expected empty by_provider: {summary}")
    _assert(summary["by_model"] == [], f"Expected empty by_model: {summary}")
    # Explicitly close the SQLite connection to avoid ResourceWarning
    conn.close()


def test_basic_aggregation_latency() -> None:
    conn = _conn_latency()
    repo = MetricsRepoSqlite(conn)
    _add(repo, "openai", "gpt-4o", 100, True)
    _add(repo, "openai", "gpt-4o", 200, True)
    _add(repo, "anthropic", "claude", 300, False, "429")
    summary = repo.summary()
    _assert(summary["total"] == 3, f"Wrong total: {summary}")
    prov = {p['provider']: p for p in summary["by_provider"]}
    _assert(prov["openai"]["count"] == 2, f"OpenAI count mismatch: {prov}")
    mod = {m['model']: m for m in summary["by_model"]}
    _assert(mod["gpt-4o"]["count"] == 2, f"Model aggregate mismatch: {mod}")
    # Explicitly close the SQLite connection to avoid ResourceWarning
    conn.close()


def test_recent_errors_ordering() -> None:
    conn = _conn_latency()
    repo = MetricsRepoSqlite(conn)
    _add(repo, "openai", "gpt-4o", 50, True)
    _add(repo, "openai", "gpt-4o", 60, False, "400")
    _add(repo, "openai", "gpt-4o", 70, False, "401")
    errors = list(repo.recent_errors())
    _assert(len(errors) == 2, f"Expected 2 errors: {errors}")
    # Ensure newest (last inserted) appears first due to DESC created_at ordering
    _assert(errors[0].error_code == "401", f"Ordering incorrect: {[e.error_code for e in errors]}")
    # Explicitly close the SQLite connection to avoid ResourceWarning
    conn.close()


def test_duration_ms_fallback() -> None:
    conn = _conn_duration()
    repo = MetricsRepoSqlite(conn)
    # Manually insert rows using duration_ms column; add_metric expects latency_ms
    conn.execute(
        "INSERT INTO metrics(provider, model, duration_ms, tokens_prompt, tokens_completion, success, error_code, created_at) VALUES(?,?,?,?,?,?,?,?)",
        ("openai", "gpt-4o", 150, 1, 1, 1, None, datetime.now(timezone.utc).isoformat()),
    )
    summary = repo.summary()
    _assert(summary["total"] == 1, f"Fallback total mismatch: {summary}")
    _assert(summary["by_provider"][0]["provider"] == "openai", f"Provider missing: {summary}")
    # Explicitly close the SQLite connection to avoid ResourceWarning
    conn.close()
