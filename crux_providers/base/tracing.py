"""Lightweight tracing facade with no-op fallback.

This module provides a tiny abstraction over tracing so the providers layer
can annotate provider calls and streaming lifecycles without taking a hard
dependency on OpenTelemetry. If ``opentelemetry.trace`` is available at
runtime, a real tracer is used; otherwise a no-op tracer keeps calls safe.

Policy notes
- No required external deps.
- No side effects on import.
- Spans expose ``set_attribute`` and context manager protocol.
"""
from __future__ import annotations

from .trace_support import _NoOpSpan, _NoOpTracer


def get_tracer(service_name: str = "providers"):
    """Return a tracer instance.

    If OpenTelemetry is installed, returns an OTEL tracer; otherwise a no-op
    tracer that safely ignores method calls.
    """
    try:  # local import to avoid hard dependency
        from opentelemetry import trace  # type: ignore

        return trace.get_tracer(service_name)
    except Exception:
        return _NoOpTracer(service_name)


def start_span(name: str, *, service_name: str = "providers"):
    """Start and return a span context manager.

    This helper abstracts over the underlying tracer implementation. Usage:

        with start_span("providers.stream") as span:
            span.set_attribute("key", "value")

    Args:
        name: Span operation name.
        service_name: Logical service name used to acquire a tracer.

    Returns:
        A context manager yielding a span-like object with ``set_attribute`` and
        ``record_exception`` methods.
    """
    tracer = get_tracer(service_name)
    # If tracer is a NoOpTracer we still return a NoOpSpan with context mgr.
    # OpenTelemetry tracers implement start_as_current_span(name) for context usage.
    if hasattr(tracer, "start_as_current_span"):
        return tracer.start_as_current_span(name)  # type: ignore[no-any-return]
    # Fallback to our no-op implementation
    return _NoOpSpan(name)


__all__ = ["get_tracer", "start_span"]
