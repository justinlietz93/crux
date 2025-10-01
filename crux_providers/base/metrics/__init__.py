"""Lightweight metrics exporter interfaces for providers layer.

Defines a minimal protocol and a default no-op exporter. Concrete exporters
(e.g., Prometheus, OTEL) can be added behind optional dependencies without
impacting the core providers architecture.
"""
from __future__ import annotations

from .exporter import MetricsExporter, NoOpMetricsExporter, get_default_exporter

__all__ = [
    "MetricsExporter",
    "NoOpMetricsExporter",
    "get_default_exporter",
]
"""Provider metrics package.

Exports provider invocation counters and snapshots.
"""

from .counters import (
    ProviderInvocationCounters,
    ProviderCountersSnapshot,
    LatencyStatsSnapshot,
)

__all__ = [
    "ProviderInvocationCounters",
    "ProviderCountersSnapshot",
    "LatencyStatsSnapshot",
]
