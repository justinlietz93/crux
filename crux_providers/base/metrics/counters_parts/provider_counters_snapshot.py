"""Provider counters snapshot dataclass.

Immutable snapshot of provider invocation counters, designed for serialization
and logging. Split into its own file to satisfy one-class-per-file governance.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Dict, Any

from .latency_stats_snapshot import LatencyStatsSnapshot


@dataclass(frozen=True)
class ProviderCountersSnapshot:
    """Immutable point-in-time snapshot of provider invocation counters.

    Includes overall counters, classified failure counts, and latency stats.
    Designed for serialization / logging (e.g., converting to dict via `asdict`).
    """

    provider: str
    total: int
    success: int
    failure: int
    retry: int
    cancelled: int
    timeout: int
    in_flight: int
    failure_by_code: Dict[str, int]
    latency: LatencyStatsSnapshot
    generated_at_ms: int

    def to_dict(self) -> Dict[str, Any]:  # convenience
        """Return a dictionary representation suitable for JSON serialization."""
        return asdict(self)


__all__ = ["ProviderCountersSnapshot"]
