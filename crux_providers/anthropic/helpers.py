"""Anthropic helpers module.

Purpose:
- Provide reusable, side-effect-free utilities for the Anthropic provider
  (parameter building, text extraction, invocation wrappers, retry config,
  stream translation) to keep `client.py` lean and compliant with the
  file-size policy.

External dependencies:
- Optional runtime dependency on ``anthropic`` SDK through the caller; this
  module does not import the SDK directly except for type-stub Protocols
  located in ``providers.base.stubs`` which are safe to import even when the
  SDK is missing.

Fallback & timeout strategy:
- Timeouts are not enforced in these helpers directly; the caller (client)
  guards blocking start phases using ``operation_timeout`` from the shared
  timeouts module. Retries are constructed via ``build_retry_config`` to be
  consumed by ``retry`` at the call site.
"""

from __future__ import annotations

from typing import Any, Optional, Tuple

from ..base.errors import ErrorCode, ProviderError
from ..base.logging import LogContext, normalized_log_event
from ..base.models import ChatRequest
from ..base.resilience.retry import RetryConfig
from ..config import get_provider_config
from ..base.streaming import ChatStreamEvent
from ..base.streaming import BaseStreamingAdapter, streaming_supported
from ..base.utils.messages import extract_system_and_user
from ..base.timeouts import get_timeout_config, operation_timeout
from ..base.capabilities import record_observation
from ..base.constants import STRUCTURED_STREAMING_UNSUPPORTED, MISSING_API_KEY_ERROR
import time
from ..base.resilience.retry import retry
from .stream_helpers import start_stream_context, translate_stream_chunk, iterate_stream


def build_params(
    model: str,
    request: ChatRequest,
    system_message: Optional[str],
    user_content: str,
) -> Tuple[dict, bool]:
    """Build Anthropic ``messages`` parameters and structured flag.

    Parameters:
        model: Target model name.
        request: Normalized chat request object.
        system_message: Optional system string to include.
        user_content: User message content (already extracted/flattened).

    Returns:
        (params, is_structured): Mapping of parameters for
        ``client.messages.create`` / ``.stream`` and a boolean indicating if
        structured output was requested via ``json_object`` or ``json_schema``.

    Notes:
        - Tools take precedence if provided; otherwise a one-off tool is
          synthesized from ``json_schema`` to request JSON output.
        - ``max_tokens`` is bounded only by caller-provided value or a sane
          default (512) to avoid accidental infinite completions.
    """
    is_structured = request.response_format == "json_object" or bool(
        request.json_schema
    )
    params: dict[str, Any] = {
        "model": model,
        "max_tokens": request.max_tokens or 512,
        "temperature": request.temperature,
        "system": system_message,
        "messages": [{"role": "user", "content": user_content}],
    }
    if request.tools:
        params["tools"] = request.tools
    elif request.json_schema:
        params["tools"] = [
            {
                "name": "json_output",
                "description": "Return JSON adhering to provided schema",
                "input_schema": request.json_schema,
            }
        ]
        params["tool_choice"] = {"type": "tool", "name": "json_output"}
    return params, is_structured


## extract_text now lives in anthropic.chat_helpers


## invoke_messages_create now lives in anthropic.chat_helpers


def build_retry_config(
    provider_name: str, logger, ctx: LogContext, *, phase: Optional[str] = None
) -> RetryConfig:
    """Construct a retry configuration for Anthropic operations.

    Builds a ``RetryConfig`` instance using provider settings with a structured
    attempt logger that emits normalized retry events.

    Parameters:
        provider_name: Name of the provider ("anthropic").
        logger: Logger instance used for emitting normalized events.
        ctx: Immutable logging context (provider/model correlation).
        phase: Optional logical phase name propagated to logs.

    Returns:
        RetryConfig: Policy with max attempts, backoff base, and attempt logger.
    """
    retry_cfg_raw: dict = {}
    try:
        retry_cfg_raw = get_provider_config(provider_name).get("retry", {}) or {}
    except Exception:
        retry_cfg_raw = {}

    max_attempts = int(retry_cfg_raw.get("max_attempts", 3))
    delay_base = float(retry_cfg_raw.get("delay_base", 2.0))

    def _attempt_logger(*, attempt: int, max_attempts: int, delay, error: ProviderError | None):  # type: ignore[override]
        normalized_log_event(
            logger,
            "retry.attempt",
            ctx,
            phase=(phase or "retry"),
            attempt=attempt,
            max_attempts=max_attempts,
            delay=delay,
            error_code=(error.code.value if error else None),
            will_retry=bool(error and delay is not None),
            tokens=None,
            emitted=None,
        )

    return RetryConfig(
        max_attempts=max_attempts,
        delay_base=delay_base,
        attempt_logger=_attempt_logger,
    )


## chat_impl moved to anthropic.chat_helpers.chat_impl to satisfy file-size policy


def stream_chat_impl(provider, request: ChatRequest):
    """Unified streaming implementation for Anthropic providers.

    This function encapsulates the streaming flow used by ``AnthropicProvider``
    and yields ``ChatStreamEvent`` items. It uses ``BaseStreamingAdapter`` and
    adheres to the standardized logging and metrics policy.

    Parameters:
        provider: The provider instance exposing ``_logger``, ``_api_key``,
            ``_model``, ``_counters``, ``provider_name``, and ``_create_client``.
        request: Structured chat request with messages/options.

    Yields:
        ChatStreamEvent: Streaming events with deltas and terminal finalize.
    """
    model = request.model or provider._model
    ctx = LogContext(provider=provider.provider_name, model=model)
    normalized_log_event(
        provider._logger,
        "stream.start",
        ctx,
        phase="start",
        temperature=request.temperature,
        max_tokens=request.max_tokens,
        tokens=None,
        emitted=None,
        attempt=None,
        error_code=None,
    )
    provider._counters.record_start()
    _t0 = time.perf_counter()
    _emitted_count = 0
    _first_token_time_ms: Optional[float] = None

    # SDK and key checks
    try:
        import anthropic as _anth  # type: ignore
    except Exception:  # pragma: no cover
        _anth = None  # type: ignore
    if not streaming_supported(
        _anth,
        require_api_key=True,
        api_key_getter=lambda: (provider._api_key or ""),
    ):
        normalized_log_event(
            provider._logger,
            "stream.error",
            ctx,
            phase="start",
            error=("anthropic SDK not installed" if _anth is None else MISSING_API_KEY_ERROR),
        )
        yield ChatStreamEvent(
            provider=provider.provider_name,
            model=model,
            delta=None,
            finish=True,
            error=(
                "anthropic SDK not installed" if _anth is None else MISSING_API_KEY_ERROR
            ),
        )
        return

    client = provider._create_client()
    system_message, user_content = extract_system_and_user(request.messages)

    if (
        request.response_format == "json_object" or request.json_schema or request.tools
    ):
        normalized_log_event(
            provider._logger,
            "stream.error",
            ctx,
            phase="start",
            error=STRUCTURED_STREAMING_UNSUPPORTED,
        )
        yield ChatStreamEvent(
            provider=provider.provider_name,
            model=model,
            delta=None,
            finish=True,
            error=STRUCTURED_STREAMING_UNSUPPORTED,
        )
        try:
            record_observation(provider.provider_name, model, "structured_streaming", False)
        except Exception:
            ...
        return

    params, _ = build_params(model, request, system_message, user_content)

    def _starter():
        retry_cfg = build_retry_config(
            provider.provider_name, provider._logger, ctx, phase="stream.start"
        )
        return retry(retry_cfg)(
            lambda: start_stream_context(client, params, model, provider.provider_name)
        )()

    def _starter_iterable():
        stream_ctx = _starter()
        try:
            timeout_cfg = get_timeout_config()
            try:
                with operation_timeout(timeout_cfg.start_timeout_seconds):
                    with stream_ctx as stream:
                        # Structural iteration helper; avoids getattr chains
                        yield from iterate_stream(stream)
            except TimeoutError as e:
                raise ProviderError(
                    code=ErrorCode.TIMEOUT,
                    message=str(e),
                    provider=provider.provider_name,
                    model=model,
                    retryable=True,
                    raw=e,
                ) from e
        finally:
            pass

    adapter = BaseStreamingAdapter(
        ctx=ctx,
        provider_name=provider.provider_name,
        model=model,
        starter=_starter_iterable,
        translator=translate_stream_chunk,
        retry_config_factory=lambda phase: build_retry_config(
            provider.provider_name, provider._logger, ctx, phase=phase
        ),
        logger=provider._logger,
    )

    for ev in adapter.run():
        if ev is not None and ev.delta:
            if _first_token_time_ms is None:
                _first_token_time_ms = (time.perf_counter() - _t0) * 1000.0
                try:
                    record_observation(provider.provider_name, model, "streaming", True)
                except Exception:
                    ...
            _emitted_count += 1
        yield ev
        if ev.finish:
            duration_ms = (time.perf_counter() - _t0) * 1000.0
            normalized_log_event(
                provider._logger,
                "stream.end",
                ctx,
                phase="finalize",
                tokens=None,
                emitted=_emitted_count,
                attempt=None,
                error_code=None,
                metrics={
                    "time_to_first_token_ms": _first_token_time_ms,
                    "total_duration_ms": duration_ms,
                    "emitted_count": _emitted_count,
                },
            )
            if ev.error:
                try:
                    provider._counters.record_failure("stream_error")
                except Exception as counter_exc:  # pragma: no cover
                    normalized_log_event(
                        provider._logger,
                        "metrics.error",
                        ctx,
                        phase="finalize",
                        error=str(counter_exc),
                        error_code=None,
                        tokens=None,
                        emitted=_emitted_count,
                        attempt=None,
                    )
            else:
                try:
                    provider._counters.record_success(int(duration_ms))
                except Exception as counter_exc:  # pragma: no cover
                    normalized_log_event(
                        provider._logger,
                        "metrics.error",
                        ctx,
                        phase="finalize",
                        error=str(counter_exc),
                        error_code=None,
                        tokens=None,
                        emitted=_emitted_count,
                        attempt=None,
                    )
