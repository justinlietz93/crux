"""Metrics exporter interface and default implementation.

Purpose
-------
- Provide a stable, tiny contract for emitting provider streaming metrics to
  external systems without coupling core code to any particular backend.

Design
------
- Protocol-like simple class with a single `emit_stream_metrics` method.
- Default `NoOpMetricsExporter` safely ignores calls.
- `get_default_exporter()` returns a process-wide singleton no-op exporter;
  future work may return a configured concrete exporter based on env flags.

Failure Modes
-------------
- Exporters must not raise; they return `None` and swallow internal errors.
- Callers should treat emission as best-effort and proceed regardless.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional


@dataclass
class StreamMetricsPayload:
    """Serialized streaming metrics payload for external emission.

    This mirrors the internal `StreamMetrics` but uses only JSON-serializable
    primitives so exporters can forward directly without extra translation.

    Attributes:
        provider: Provider identifier.
        model: Model name/identifier.
        emitted_count: Number of delta events emitted.
        time_to_first_token_ms: Latency to first token in milliseconds.
        total_duration_ms: Total streaming duration in milliseconds.
        tokens: Mapping with keys `prompt`, `completion`, `total` when known.
        error: Optional error string if the stream ended in error.
        extra: Optional additional fields for future extension.
    """

    provider: str
    model: str
    emitted_count: int
    time_to_first_token_ms: Optional[float]
    total_duration_ms: Optional[float]
    tokens: Optional[Mapping[str, Any]]
    error: Optional[str] = None
    extra: Optional[Mapping[str, Any]] = None


class MetricsExporter:
    """Minimal metrics exporter contract.

    Concrete implementations should be side-effect-only and never raise.
    """

    def emit_stream_metrics(self, payload: StreamMetricsPayload) -> None:  # pragma: no cover - interface
        """Emit a single streaming metrics payload downstream.

        Implementations MUST swallow exceptions and avoid raising to callers.
        """
        raise NotImplementedError


class NoOpMetricsExporter(MetricsExporter):
    """Default exporter that does nothing (safe baseline)."""

    def emit_stream_metrics(self, payload: StreamMetricsPayload) -> None:  # noqa: D401 - trivial
        """Accept payload and do nothing."""
        return


_DEFAULT_EXPORTER: MetricsExporter | None = None


def get_default_exporter() -> MetricsExporter:
    """Return process-wide default exporter (no-op by default).

    Future: swap to a Prometheus or OTEL exporter based on environment flags.
    """
    global _DEFAULT_EXPORTER
    if _DEFAULT_EXPORTER is None:
        _DEFAULT_EXPORTER = NoOpMetricsExporter()
    return _DEFAULT_EXPORTER


__all__ = [
    "StreamMetricsPayload",
    "MetricsExporter",
    "NoOpMetricsExporter",
    "get_default_exporter",
]
