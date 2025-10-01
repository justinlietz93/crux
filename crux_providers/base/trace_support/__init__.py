"""Auxiliary tracing helpers used by base.tracing when OTEL is absent."""

from .tracing_noop_span import _NoOpSpan
from .tracing_noop_tracer import _NoOpTracer

__all__ = ["_NoOpSpan", "_NoOpTracer"]
