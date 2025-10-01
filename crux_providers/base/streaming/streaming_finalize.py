"""Finalize stream helper.

Located within the streaming package to localize terminal event creation and
normalized logging of metrics.
"""
from __future__ import annotations

import os
from typing import Optional, Dict, Any

from .streaming import ChatStreamEvent
from ..logging import LogContext, normalized_log_event
from .streaming_metrics import StreamMetrics
# Import the exporter module (not the symbol) so tests can monkeypatch
# `get_default_exporter` on the module path and have it take effect here.
from ..metrics import exporter as metrics_exporter


def finalize_stream(
    *,
    logger,
    ctx: LogContext,
    provider: str,
    model: str,
    metrics: StreamMetrics,
    error: Optional[str] = None,
) -> ChatStreamEvent:
    """Create the terminal `ChatStreamEvent` and emit consolidated logging."""
    error_code: Optional[str] = None
    if error and ":" in error:
        error_code = error.split(":", 1)[0].strip() or None

    if metrics.tokens is not None:
        tokens_payload: Dict[str, Any] = metrics.tokens
    else:
        tokens_payload = {
            "prompt": metrics.prompt_tokens,
            "completion": metrics.completion_tokens,
            "total": metrics.total_tokens
            if metrics.total_tokens is not None
            else (
                (metrics.prompt_tokens + metrics.completion_tokens)
                if (metrics.prompt_tokens is not None and metrics.completion_tokens is not None)
                else None
            ),
        }

    normalized_log_event(
        logger,
        "stream.adapter.end" if error is None else "stream.adapter.error",
        ctx,
        phase="finalize",
        attempt=None,
        emitted=metrics.emitted > 0,
        tokens=tokens_payload,
        error_code=error_code,
        emitted_count=metrics.emitted,
        time_to_first_token_ms=metrics.time_to_first_token_ms,
        total_duration_ms=metrics.total_duration_ms,
        error=error,
    )
    # Feature-flagged external metrics emission (best-effort, never raises)
    if os.getenv("PROVIDERS_METRICS_EXPORT", "0").strip() in {"1", "true", "True"}:
        try:
            exporter = metrics_exporter.get_default_exporter()
            payload = metrics_exporter.StreamMetricsPayload(
                provider=provider,
                model=model,
                emitted_count=metrics.emitted,
                time_to_first_token_ms=metrics.time_to_first_token_ms,
                total_duration_ms=metrics.total_duration_ms,
                tokens=tokens_payload,
                error=error,
            )
            exporter.emit_stream_metrics(payload)
        except Exception as exc:  # pragma: no cover - defensive; emission must not break finalize
            # Structured one-time log for emission failure (no fallback besides skip)
            normalized_log_event(
                logger,
                "metrics.export.error",
                ctx,
                phase="finalize",
                attempt=None,
                error_code=exc.__class__.__name__,
                emitted=None,
                tokens=None,
                failure_class=exc.__class__.__name__,
                fallback_used=True,
            )
    return ChatStreamEvent(
        provider=provider,
        model=model,
        delta=None,
        finish=True,
        error=error,
    )


__all__ = ["finalize_stream"]
