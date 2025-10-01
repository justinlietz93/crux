"""Latency statistics snapshot dataclass.

Defines an immutable snapshot capturing aggregate latency metrics for provider
invocations. Kept separate to enforce one-class-per-file governance.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class LatencyStatsSnapshot:
    """Immutable snapshot of aggregated latency statistics.

    Attributes:
        count: Number of completed invocations with recorded latency.
        total_ms: Sum of all observed latencies in milliseconds.
        min_ms: Minimum observed latency (ms) or None if no samples.
        max_ms: Maximum observed latency (ms) or None if no samples.
        avg_ms: Pre-computed arithmetic mean (ms) or None if no samples.
    """

    count: int
    total_ms: int
    min_ms: Optional[int]
    max_ms: Optional[int]
    avg_ms: Optional[float]


__all__ = ["LatencyStatsSnapshot"]
