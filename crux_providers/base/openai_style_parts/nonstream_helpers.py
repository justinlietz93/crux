"""Helpers for non-streaming chat orchestration in OpenAI-style providers.

Purpose
-------
- Encapsulate timeout + retry + logging for non-streaming chat calls.
- Centralize success and error response shaping with consistent metadata.
- Keep the base provider class concise to satisfy method LOC targets.

External Dependencies
---------------------
- Uses the providers base logging, errors, timeouts, and retry utilities.
- Pure orchestration utilities only; no direct network I/O is performed here.

Fallback & Timeout Strategy
---------------------------
- Start phase is wrapped using ``operation_timeout(get_timeout_config())``.
- Timeout exceptions are surfaced to error shaper for uniform handling.

Note
----
These helpers are provider-agnostic in logic but accept concrete context
objects (``ctx``) and a logger instance to emit normalized logs.
"""

from __future__ import annotations

import time
from typing import Any, Callable, Tuple

from ..errors import ErrorCode, ProviderError, classify_exception
from ..logging import normalized_log_event
from ..models import ChatResponse, ContentPart, ProviderMetadata
from ..resilience.retry import retry
from ..timeouts import operation_timeout
from ..capabilities import record_observation


def run_nonstream_with_timeout_and_retry(
    *,
    invoke_fn: Callable[[], Any],
    ctx,
    logger,
    retry_config_factory: Callable[[], Any],
    start_timeout_seconds: float,
) -> Tuple[Any, float]:
    """Invoke a non-streaming chat call under timeout + retry with logging.

    Parameters
    ----------
    invoke_fn: Callable[[], Any]
        Zero-argument callable that performs the underlying SDK call.
    ctx: Any
        Log context carrying provider/model fields.
    logger: Any
        Structured logger used by ``normalized_log_event``.
    retry_config_factory: Callable[[], Any]
        Callable returning a ``RetryConfig`` instance for the start phase.
    start_timeout_seconds: float
        Timeout in seconds for the start/first-byte phase.

    Returns
    -------
    tuple[Any, float]
        The raw SDK response and the measured latency in milliseconds.

    Raises
    ------
    TimeoutError
        When the start phase exceeds the configured timeout.
    ProviderError
        When the SDK call fails with a classified provider error.
    Exception
        For any other unexpected exception types.
    """
    t0 = time.perf_counter()
    with operation_timeout(start_timeout_seconds):
        retry_cfg = retry_config_factory()
        resp = retry(retry_cfg)(invoke_fn)()
    latency_ms = (time.perf_counter() - t0) * 1000.0
    normalized_log_event(
        logger,
        "chat.end",
        ctx,
        phase="finalize",
        latency_ms=latency_ms,
        tokens=None,
        emitted=None,
        attempt=None,
        error_code=None,
    )
    return resp, latency_ms


def nonstream_error_response(*, provider_name: str, model: str, ctx, logger, exc: Exception) -> ChatResponse:
    """Construct a ``ChatResponse`` for non-stream errors with logging.

    Logs a normalized ``chat.error`` event and returns a response embedding
    the error information in ``meta.extra`` for downstream visibility.

    Parameters
    ----------
    provider_name: str
        Canonical provider identifier.
    model: str
        Model name used for the request.
    ctx: Any
        Logging context.
    logger: Any
        Structured logger used by ``normalized_log_event``.
    exc: Exception
        The exception that occurred during the call.

    Returns
    -------
    ChatResponse
        A response carrying error details in metadata.
    """
    if isinstance(exc, TimeoutError):
        normalized_log_event(
            logger,
            "chat.error",
            ctx,
            phase="finalize",
            error=str(exc),
            error_code=ErrorCode.TIMEOUT.value,
            tokens=None,
            emitted=None,
            attempt=None,
        )
        meta = ProviderMetadata(
            provider_name=provider_name,
            model_name=model,
            latency_ms=None,
            extra={"error": str(exc), "code": ErrorCode.TIMEOUT.value, "phase": "start_timeout"},
        )
        return ChatResponse(text=None, parts=None, raw=None, meta=meta)

    if isinstance(exc, ProviderError):
        normalized_log_event(
            logger,
            "chat.error",
            ctx,
            phase="finalize",
            error=str(exc),
            error_code=exc.code.value,
            tokens=None,
            emitted=None,
            attempt=None,
        )
        meta = ProviderMetadata(
            provider_name=provider_name,
            model_name=model,
            latency_ms=None,
            extra={"error": exc.message, "code": exc.code.value},
        )
        return ChatResponse(text=None, parts=None, raw=None, meta=meta)

    code = classify_exception(exc)
    normalized_log_event(
        logger,
        "chat.error",
        ctx,
        phase="finalize",
        error=str(exc),
        error_code=code.value,
        tokens=None,
        emitted=None,
        attempt=None,
    )
    meta = ProviderMetadata(
        provider_name=provider_name,
        model_name=model,
        latency_ms=None,
        extra={"error": str(exc), "code": code.value},
    )
    return ChatResponse(text=None, parts=None, raw=None, meta=meta)


def build_nonstream_success_response(
    *,
    provider_name: str,
    model: str,
    text: str,
    is_structured: bool,
    latency_ms: float,
) -> ChatResponse:
    """Create a successful non-stream ``ChatResponse`` with metadata.

    Records a capability observation when structured output was requested and
    returns a response containing the assistant text and a single text part
    (when non-empty).

    Parameters
    ----------
    provider_name: str
        Canonical provider identifier.
    model: str
        Model name used for the request.
    text: str
        Assistant text extracted from the raw SDK response.
    is_structured: bool
        Whether a structured response was requested.
    latency_ms: float
        Latency measured for the request.

    Returns
    -------
    ChatResponse
        A populated response with metadata and optional text part.
    """
    meta = ProviderMetadata(
        provider_name=provider_name,
        model_name=model,
        latency_ms=latency_ms,
        token_param_used="max_tokens",  # nosec B106 - benign generation parameter
        extra={"is_structured": is_structured},
    )
    try:
        if is_structured:
            record_observation(provider_name, model, "json_output", True)
    except Exception:  # pragma: no cover - observation is best-effort
        ...
    parts = [ContentPart(type="text", text=text)] if text else None
    return ChatResponse(text=(text or None), parts=parts, raw=None, meta=meta)


__all__ = [
    "run_nonstream_with_timeout_and_retry",
    "nonstream_error_response",
    "build_nonstream_success_response",
]
