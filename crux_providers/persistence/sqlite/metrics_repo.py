"""SQLite-backed implementation of ``IMetricsRepo``.

Persists provider invocation metrics and exposes simple aggregations. Timestamps
are stored as ISO8601 strings (UTC assumed for naive datetimes) to avoid
sqlite's deprecated datetime adapter and ensure explicit semantics.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, Optional, Tuple

from ..interfaces.repos import IMetricsRepo, MetricEntry
from .helpers import _metric_from_row


class MetricsRepoSqlite(IMetricsRepo):
    """SQLite-backed repository for metrics capture and aggregation.

    Writes persist invocation metrics and support simple aggregations.
    No implicit commits; Unit of Work governs transactions.
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def add_metric(self, entry: MetricEntry) -> None:
        """Persist a metric entry with normalized timestamp semantics.

        Datetime Normalization:
            Stores ``created_at`` as an ISO8601 string to avoid the deprecated
            sqlite3 datetime adapter (Python 3.12+ warning). Naive datetimes are
            treated as UTC for backward compatibility.

        Parameters
        ----------
        entry:
            The metric entry to persist.
        """
        created_at = entry.created_at
        if isinstance(created_at, datetime) and created_at.tzinfo is None:
            # Treat legacy naive datetimes as UTC
            created_at = created_at.replace(tzinfo=timezone.utc)
        created_at_str = created_at.isoformat() if isinstance(created_at, datetime) else str(created_at)
        self.conn.execute(
            """
            INSERT INTO metrics(provider, model, latency_ms, tokens_prompt, tokens_completion, success, error_code, created_at)
            VALUES(?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                entry.provider,
                entry.model,
                entry.latency_ms,
                entry.tokens_prompt,
                entry.tokens_completion,
                1 if entry.success else 0,
                entry.error_code,
                created_at_str,
            ),
        )

    def aggregate_latency(self, provider: str, model: Optional[str] = None) -> Tuple[int, int]:
        """Return ``(count, avg_latency_ms)`` aggregated by scope.

        Parameters
        ----------
        provider:
            Provider identifier to filter rows.
        model:
            Optional model filter; when provided restricts aggregation to that model.
        """
        if model:
            cur = self.conn.execute(
                "SELECT COUNT(*), AVG(latency_ms) FROM metrics WHERE provider = ? AND model = ?",
                (provider, model),
            )
        else:
            cur = self.conn.execute(
                "SELECT COUNT(*), AVG(latency_ms) FROM metrics WHERE provider = ?",
                (provider,),
            )
        row = cur.fetchone() or (0, 0)
        count = int(row[0]) if row[0] is not None else 0
        avg = int(row[1]) if row[1] is not None else 0
        return count, avg

    def recent_errors(self, limit: int = 50) -> Iterable[MetricEntry]:
        """Yield most recent error metric entries up to a limit.

        Parameters
        ----------
        limit:
            Maximum number of rows to scan (default 50).
        """
        cur = self.conn.execute(
            """
            SELECT provider, model, latency_ms, tokens_prompt, tokens_completion, success, error_code, created_at
            FROM metrics WHERE success = 0 ORDER BY created_at DESC LIMIT ?
            """,
            (limit,),
        )
        for r in cur.fetchall():
            yield _metric_from_row(r)

    def summary(self) -> Dict[str, Any]:
        """Compute aggregate metrics summary (total, by_provider, by_model).

        Mirrors the legacy helper contract to preserve compatibility.
        Average latency is derived from ``latency_ms`` and may be null when no
        rows exist for a group.
        """
        # Determine latency column name (backward compatibility: legacy table used duration_ms)
        cur = self.conn.execute("PRAGMA table_info(metrics)")
        cols = {r[1] for r in cur.fetchall()}
        latency_col = "latency_ms" if "latency_ms" in cols else ("duration_ms" if "duration_ms" in cols else "latency_ms")

        # Total row count (all metrics).
        cur = self.conn.execute("SELECT COUNT(*) FROM metrics")
        total_row = cur.fetchone()
        total = int(total_row[0]) if total_row and total_row[0] is not None else 0

        query_provider = (
            f"SELECT provider, COUNT(*) as c, AVG({latency_col}) as avg_ms "
            "FROM metrics GROUP BY provider ORDER BY c DESC"  # nosec B608 - latency_col validated via schema
        )
        cur = self.conn.execute(query_provider)
        by_provider = [
            {
                "provider": r[0],
                "count": int(r[1]) if r[1] is not None else 0,
                "avg_ms": float(r[2]) if r[2] is not None else None,
            }
            for r in cur.fetchall()
        ]

        query_model = (
            f"SELECT model, COUNT(*) as c, AVG({latency_col}) as avg_ms "
            "FROM metrics GROUP BY model ORDER BY c DESC LIMIT 10"  # nosec B608 - latency_col validated via schema
        )
        cur = self.conn.execute(query_model)
        by_model = [
            {
                "model": r[0],
                "count": int(r[1]) if r[1] is not None else 0,
                "avg_ms": float(r[2]) if r[2] is not None else None,
            }
            for r in cur.fetchall()
        ]
        return {"total": total, "by_provider": by_provider, "by_model": by_model}
