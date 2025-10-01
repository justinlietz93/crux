"""Streaming adapter helper functions (within streaming package)."""

from __future__ import annotations

from contextlib import suppress, ExitStack
from typing import Any, Dict, Iterable, Iterator, Mapping, Optional, Tuple, Protocol, runtime_checkable, TYPE_CHECKING
import time

from ..errors import ProviderError, classify_exception, ErrorCode
from .streaming import ChatStreamEvent
from .streaming_finalize import finalize_stream
from ..timeouts import get_timeout_config, operation_timeout
from ..tracing import start_span

if TYPE_CHECKING:
    from ..dto.structured_output import StructuredOutputDTO


def attempt_start_with_timeout(adapter) -> Tuple[bool, Optional[Iterable], Optional[ChatStreamEvent]]:
    """Start the provider stream under a start-phase timeout and retry policy."""
    timeout_cfg = get_timeout_config()
    with start_span("providers.stream.start") as stspan:
        with suppress(Exception):
            stspan.set_attribute("provider", adapter.provider_name)
            stspan.set_attribute("model", adapter.model)
            stspan.set_attribute("stage", "start")
        try:
            with operation_timeout(timeout_cfg.start_timeout_seconds):
                result = start_with_retry(adapter)
            stream, extra_meta = coerce_stream_start_result(result)
            if extra_meta:
                req_id = extra_meta.get("request_id")
                resp_id = extra_meta.get("response_id")
                if req_id and not adapter.ctx.request_id:
                    adapter.ctx.request_id = req_id
                if resp_id and not _has_response_id(adapter):
                    _set_response_id(adapter, resp_id)
            return True, stream, None
        except ProviderError as e:  # Already classified
            with suppress(Exception):
                stspan.record_exception(e)
            return False, None, terminal_error(adapter, f"{e.code.value}:{e.message[:260]}")
        except Exception as e:  # Unexpected
            with suppress(Exception):
                stspan.record_exception(e)
            code = classify_exception(e)
            return False, None, terminal_error(adapter, f"{code.value}:{str(e)[:260]}")


def process_chunk(adapter, chunk, t0: float, first_emitted: bool) -> Iterator[ChatStreamEvent]:
    """Translate a native chunk and yield an event if there is content.

    Behavior
    - Prefer a textual ``delta`` via ``adapter._translator``.
    - Optionally attach a ``StructuredOutputDTO`` via ``_structured_translator``.
    - Record time to first token on the first emission and increment metrics.
    - No event is yielded when neither textual nor structured output exists.
    """
    _maybe_set_response_id_from_chunk(adapter, chunk, first_emitted)
    delta, structured = _extract_translations(adapter, chunk)
    if not delta and not structured:
        return
    _record_first_token_if_needed(adapter, t0, first_emitted)
    adapter.metrics.emitted += 1
    _log_delta_debug(adapter, delta)
    yield ChatStreamEvent(
        provider=adapter.provider_name,
        model=adapter.model,
        delta=delta,
        structured=structured,
        finish=False,
    )


def handle_midstream_error(adapter, exc: Exception, t0: float) -> Iterator[ChatStreamEvent]:
    """Handle an exception raised during iteration."""
    code = classify_exception(exc)
    adapter.metrics.total_duration_ms = (time.perf_counter() - t0) * 1000.0
    yield terminal_error(adapter, f"{code.value}:{str(exc)[:260]}")
    if adapter._on_complete:
        with suppress(Exception):
            adapter._on_complete(adapter.metrics.emitted > 0)


def handle_cancellation(adapter, exc, t0: float) -> Iterator[ChatStreamEvent]:
    """Map cooperative cancellation to a terminal CANCELLED event."""
    adapter.metrics.total_duration_ms = (time.perf_counter() - t0) * 1000.0
    error_message = exc.args[0] if exc.args else "operation cancelled"
    yield terminal_error(adapter, f"{ErrorCode.CANCELLED.value}:{error_message[:260]}")
    if adapter._on_complete:
        with suppress(Exception):
            adapter._on_complete(adapter.metrics.emitted > 0)


def finalize_success(adapter, t0: float) -> Iterator[ChatStreamEvent]:
    """Emit a successful terminal event and finalize metrics."""
    adapter.metrics.total_duration_ms = (time.perf_counter() - t0) * 1000.0
    yield finalize_stream(
        logger=adapter._logger,
        ctx=adapter.ctx,
        provider=adapter.provider_name,
        model=adapter.model,
        metrics=adapter.metrics,
    )
    if adapter._on_complete:
        with suppress(Exception):
            adapter._on_complete(adapter.metrics.emitted > 0)


def start_with_retry(adapter):
    """Start the provider stream with retry and error classification."""

    def _invoke():
        try:
            return adapter._starter()
        except ProviderError:
            raise
        except Exception as e:  # classify into ProviderError for uniform handling
            code = classify_exception(e)
            raise ProviderError(
                code=code,
                message=str(e),
                provider=adapter.provider_name,
                model=adapter.model,
                retryable=code in (ErrorCode.TRANSIENT, ErrorCode.RATE_LIMIT, ErrorCode.TIMEOUT),
                raw=e,
            )

    retry_cfg = adapter._retry_config_factory("stream.start")
    from ..resilience.retry import retry  # local import to avoid cycles

    return retry(retry_cfg)(_invoke)()


def terminal_error(adapter, error: str) -> ChatStreamEvent:
    """Create a terminal error event with current metrics."""
    return finalize_stream(
        logger=adapter._logger,
        ctx=adapter.ctx,
        provider=adapter.provider_name,
        model=adapter.model,
        metrics=adapter.metrics,
        error=error,
    )


def coerce_stream_start_result(result) -> Tuple[Iterable, Dict[str, Any]]:
    """Normalize the `starter()` return value into `(stream, meta)`.

    Accepted forms:
    - stream_iterable
    - {"stream": stream_iterable, ...meta}
    - (stream_iterable, {..meta}) or [stream_iterable, {..meta}]

    Defensive behavior:
    - If a sequence of length 2 is provided but the second element is not a
      mapping, treat the entire object as the stream (best-effort) instead of
      raising. This avoids misclassifying a plain list of chunks as a
      `(stream, meta)` pair in tests and simple adapters.
    """
    from ..errors import ProviderError  # local import to avoid import cycles
    if isinstance(result, Mapping):
        stream_obj = result.get("stream")
        if stream_obj is None:
            raise ProviderError(
                code=ErrorCode.INTERNAL,
                message="starter() mapping missing 'stream' key",
                provider=str(result.get("provider", "unknown")),
                model=str(result.get("model", "unknown")),
            )
        meta = {k: v for k, v in result.items() if k != "stream"}
        return stream_obj, meta
    if isinstance(result, (tuple, list)) and len(result) == 2:
        stream_obj, meta = result
        return (stream_obj, dict(meta)) if isinstance(meta, Mapping) else (result, {})
    return result, {}


def register_stream_cleanup(stream, stack: ExitStack) -> None:
    """Register best-effort cleanup callbacks for the native stream."""
    close_fn = getattr(stream, "close", None)
    if callable(close_fn):
        def _safe_close():  # noqa: D401 - simple internal callback
            with suppress(Exception):
                close_fn()
        stack.callback(_safe_close)


def set_span_metrics(adapter, span) -> None:
    """Record current streaming metrics on the active tracing span."""
    with suppress(Exception):
        span.set_attribute("emitted_count", adapter.metrics.emitted)
        span.set_attribute("time_to_first_token_ms", adapter.metrics.time_to_first_token_ms)
        span.set_attribute("total_duration_ms", adapter.metrics.total_duration_ms)


# Internal helpers -----------------------------------------------------------

@runtime_checkable
class _HasResponseId(Protocol):
    response_id: Optional[str]


def _has_response_id(adapter) -> bool:
    """Return True if the adapter's ctx has a non-empty response_id.

    Defensive: tolerates ctx objects without the `response_id` attribute.
    """
    try:
        ctx = adapter.ctx
        if isinstance(ctx, _HasResponseId):  # type: ignore[misc]
            return bool(ctx.response_id)
        # Fallback best-effort
        return bool(getattr(ctx, "response_id", None))
    except Exception:
        return False


def _set_response_id(adapter, value: str) -> None:
    """Set the ctx.response_id best-effort, ignoring errors."""
    with suppress(Exception):
        adapter.ctx.response_id = value  # type: ignore[attr-defined]


def _get_chunk_id(chunk: Any) -> Optional[str]:
    """Extract string id from a chunk if present; otherwise return None."""
    try:
        possible_id = getattr(chunk, "id", None)
        return possible_id if isinstance(possible_id, str) and possible_id else None
    except Exception:
        return None


def _is_logger_debug(adapter) -> bool:
    """Check whether adapter logger is in debug with minimal getattr usage."""
    try:
        logger = adapter._logger
        isEnabledFor = getattr(logger, "isEnabledFor", None)
        return bool(isEnabledFor and logger.isEnabledFor(10))
    except Exception:
        return False


# Small internal helpers extracted for readability and LOC limits ------------

def _maybe_set_response_id_from_chunk(adapter, chunk: Any, first_emitted: bool) -> None:
    """Derive and set a response id from the first chunk when applicable.

    Side effects are best-effort and errors are suppressed; failure to extract
    an id should not impact streaming correctness.
    """
    if first_emitted or _has_response_id(adapter):
        return
    with suppress(Exception):
        if possible_id := _get_chunk_id(chunk):
            _set_response_id(adapter, possible_id)


def _extract_translations(adapter, chunk: Any) -> Tuple[Optional[str], Optional["StructuredOutputDTO"]]:
    """Run text and structured translators with defensive guards.

    Returns a tuple ``(delta, structured)`` where either may be ``None`` on
    translation failure or absence of configured translators.
    """
    delta: Optional[str] = None
    structured: Optional["StructuredOutputDTO"] = None
    try:
        delta = adapter._translator(chunk)
    except Exception:
        delta = None
    try:
        translator = getattr(adapter, "_structured_translator", None)
        if translator:
            structured = translator(chunk)
    except Exception:
        structured = None
    return delta, structured


def _record_first_token_if_needed(adapter, t0: float, first_emitted: bool) -> None:
    """Set ``time_to_first_token_ms`` when the first content is emitted."""
    if not first_emitted:
        adapter.metrics.time_to_first_token_ms = (time.perf_counter() - t0) * 1000.0


def _log_delta_debug(adapter, delta: Optional[str]) -> None:
    """Emit a normalized debug event for the delta if debug logging is enabled."""
    with suppress(Exception):
        if _is_logger_debug(adapter):
            from ..logging import normalized_log_event  # local import to avoid cycles
            normalized_log_event(
                adapter._logger,
                "stream.delta",
                adapter.ctx,
                phase="mid_stream",
                attempt=None,
                emitted=True,
                tokens=None,
                error_code=None,
                delta_len=len(delta) if isinstance(delta, str) else None,
            )


__all__ = [
    "attempt_start_with_timeout",
    "process_chunk",
    "handle_midstream_error",
    "handle_cancellation",
    "finalize_success",
    "start_with_retry",
    "terminal_error",
    "coerce_stream_start_result",
    "register_stream_cleanup",
    "set_span_metrics",
]
