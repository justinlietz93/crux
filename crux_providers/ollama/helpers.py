"""Ollama helpers module.

Purpose:
- Provide reusable, side-effect-free utilities for the Ollama provider
  (prompt building, payload construction, retry config, HTTP invocations,
  and streaming orchestration) to keep `client.py` lean and under the
  file-size policy.

External dependencies:
- Uses the shared `httpx` client via `get_httpx_client` (no SDK). No API key
  is required since Ollama is a local daemon.

Timeout & retry strategy:
- Blocking start phases are guarded by `operation_timeout` using durations
  from `get_timeout_config()`.
- Retries use `RetryConfig` from provider settings through `build_retry_config`.

Failure semantics:
- Exceptions are classified to `ErrorCode` and wrapped in `ProviderError`.
- Non-streaming chat returns a `ChatResponse` with error metadata.
"""

from __future__ import annotations

import json
import time
from contextlib import suppress
from typing import Any, Dict, Optional

from ..base.capabilities import record_observation
from ..base.constants import STRUCTURED_STREAMING_UNSUPPORTED
from ..base.errors import ErrorCode, ProviderError, classify_exception
from ..base.http import get_httpx_client
from ..base.logging import LogContext, normalized_log_event
from ..base.models import ChatRequest, ChatResponse, ContentPart, ProviderMetadata
from ..base.resilience.retry import RetryConfig, retry
from ..base.streaming import ChatStreamEvent
from ..base.streaming.streaming_adapter import BaseStreamingAdapter
from ..base.timeouts import get_timeout_config, operation_timeout
from ..base.utils.messages import extract_system_and_user
from ..config import get_provider_config


def build_retry_config(provider_name: str, logger, ctx: LogContext, *, phase: Optional[str] = None) -> RetryConfig:
    """Construct a retry configuration for Ollama operations.

    Parameters:
        provider_name: Stable provider identifier ("ollama").
        logger: Logger used to emit normalized events.
        ctx: Correlation context for logs.
        phase: Optional phase label for attempt logs.

    Returns:
        RetryConfig with attempt logging and backoff parameters from config.
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

    return RetryConfig(max_attempts=max_attempts, delay_base=delay_base, attempt_logger=_attempt_logger)


def prepare_prompt(request: ChatRequest) -> tuple[str, bool]:
    """Build a plain prompt from messages and flag structured output intent.

    Returns (prompt, is_structured) where `is_structured` is True when the
    request uses `response_format=="json_object"`.
    """
    system_message, user_content = extract_system_and_user(request.messages)
    parts: list[str] = []
    if system_message:
        parts.append(f"[SYSTEM]\n{system_message}")
    if user_content:
        parts.append(user_content)
    prompt = "\n".join(parts)
    is_structured = request.response_format == "json_object"
    return prompt, is_structured


def build_payload(*, model: str, prompt: str, stream: bool, structured: bool, has_schema: bool) -> Dict[str, Any]:
    """Construct the JSON payload for Ollama's `/api/generate` endpoint."""
    payload: Dict[str, Any] = {"model": model, "prompt": prompt, "stream": stream}
    if has_schema or structured:
        payload["format"] = "json"
    return payload


def invoke_non_stream(provider, payload: Dict[str, Any], *, model: str, ctx: LogContext):
    """Invoke the non-streaming endpoint under retry; return httpx.Response."""

    def _call():
        try:
            client = get_httpx_client(provider._host, purpose="ollama.chat")
            return client.post("/api/generate", json=payload)
        except Exception as e:  # pragma: no cover - classified below
            code = classify_exception(e)
            raise ProviderError(
                code=code,
                message=str(e),
                provider=provider.provider_name,
                model=model,
                retryable=code in (ErrorCode.TRANSIENT, ErrorCode.RATE_LIMIT, ErrorCode.TIMEOUT),
                raw=e,
            )

    cfg = build_retry_config(provider.provider_name, provider._logger, ctx, phase="chat.start")
    return retry(cfg)(_call)()


def build_meta(provider, *, model: str, latency_ms: float | None, is_structured: bool) -> ProviderMetadata:
    """Assemble provider metadata for a completed non-streaming call."""
    return ProviderMetadata(
        provider_name=provider.provider_name,
        model_name=model,
        latency_ms=latency_ms,
        token_param_used=None,
        extra={"is_structured": is_structured},
    )


def error_chat_response(provider, error: ProviderError, *, model: str, ctx: LogContext) -> ChatResponse:
    """Create a normalized ChatResponse for error scenarios."""
    normalized_log_event(
        provider._logger,
        "chat.error",
        ctx,
        phase="finalize",
        attempt=None,
        emitted=False,
        tokens=None,
        error=str(error),
        error_code=error.code.value,
    )
    meta = ProviderMetadata(
        provider_name=provider.provider_name,
        model_name=model,
        latency_ms=None,
        extra={"error": error.message, "code": error.code.value},
    )
    return ChatResponse(text=None, parts=None, raw=None, meta=meta)


def should_reject_stream(request: ChatRequest) -> bool:
    """Return True when structured streaming is requested and unsupported."""
    return bool(request.response_format == "json_object" or request.json_schema or request.tools)


def build_stream_payload(request: ChatRequest, *, model: str) -> Dict[str, Any]:
    """Create the HTTP payload for streaming generation (no JSON format)."""
    prompt, _ = prepare_prompt(request)
    return build_payload(model=model, prompt=prompt, stream=True, structured=False, has_schema=False)


def chat_impl(provider, request: ChatRequest) -> ChatResponse:
    """Unified non-streaming chat implementation for Ollama providers."""
    model = request.model or provider._model
    ctx = LogContext(provider=provider.provider_name, model=model)
    prompt, is_structured = prepare_prompt(request)
    payload = build_payload(
        model=model,
        prompt=prompt,
        stream=False,
        structured=is_structured,
        has_schema=bool(request.json_schema),
    )
    normalized_log_event(
        provider._logger,
        "chat.start",
        ctx,
        phase="start",
        attempt=None,
        emitted=None,
        tokens=None,
        has_tools=bool(request.tools),
        has_schema=bool(request.json_schema),
        max_tokens=request.max_tokens,
        temperature=request.temperature,
    )

    t0 = time.perf_counter()
    try:
        timeout_cfg = get_timeout_config()
        with operation_timeout(timeout_cfg.start_timeout_seconds):
            resp = invoke_non_stream(provider, payload, model=model, ctx=ctx)
        latency_ms = (time.perf_counter() - t0) * 1000.0
        resp.raise_for_status()
        data = resp.json()
        text = data.get("response")
        normalized_log_event(
            provider._logger,
            "chat.end",
            ctx,
            phase="finalize",
            attempt=None,
            emitted=True,
            tokens=None,
            latency_ms=latency_ms,
        )
        meta = build_meta(provider, model=model, latency_ms=latency_ms, is_structured=is_structured)
        parts = [ContentPart(type="text", text=text)] if text else None
        if is_structured:
            with suppress(Exception):
                record_observation(provider.provider_name, model, "json_output", True)
        return ChatResponse(text=text or None, parts=parts, raw=None, meta=meta)
    except TimeoutError as e:  # start-phase timeout
        normalized_log_event(
            provider._logger,
            "chat.error",
            ctx,
            phase="finalize",
            attempt=None,
            emitted=None,
            tokens=None,
            error=str(e),
            error_code=ErrorCode.TIMEOUT.value,
        )
        meta = ProviderMetadata(
            provider_name=provider.provider_name,
            model_name=model,
            latency_ms=None,
            extra={"error": str(e), "code": ErrorCode.TIMEOUT.value, "phase": "start_timeout"},
        )
        return ChatResponse(text=None, parts=None, raw=None, meta=meta)
    except ProviderError as e:  # pragma: no cover
        return error_chat_response(provider, e, model=model, ctx=ctx)
    except Exception as e:  # pragma: no cover
        code = classify_exception(e)
        return error_chat_response(
            provider,
            ProviderError(
                code=code,
                message=str(e),
                provider=provider.provider_name,
                model=model,
                retryable=False,
                raw=e,
            ),
            model=model,
            ctx=ctx,
        )


def stream_chat_impl(provider, request: ChatRequest):
    """Unified streaming implementation for Ollama providers.

    Uses `BaseStreamingAdapter` to provide standardized retries, timeouts,
    and finalize metrics. Maps streamed JSON lines to text deltas.
    """
    model = request.model or provider._model
    ctx = LogContext(provider=provider.provider_name, model=model)
    normalized_log_event(
        provider._logger,
        "stream.start",
        ctx,
        phase="start",
        attempt=None,
        emitted=None,
        tokens=None,
        temperature=request.temperature,
        max_tokens=request.max_tokens,
    )

    if should_reject_stream(request):
        with suppress(Exception):
            record_observation(provider.provider_name, model, "structured_streaming", False)
        yield ChatStreamEvent(
            provider=provider.provider_name,
            model=model,
            delta=None,
            finish=True,
            error=STRUCTURED_STREAMING_UNSUPPORTED,
        )
        return

    payload = build_stream_payload(request, model=model)

    def _starter():
        cfg = build_retry_config(provider.provider_name, provider._logger, ctx, phase="stream.start")

        def _open():
            try:
                client = get_httpx_client(provider._host, purpose="ollama.stream")
                return client.stream("POST", "/api/generate", json=payload)
            except Exception as e:  # pragma: no cover
                code = classify_exception(e)
                raise ProviderError(
                    code=code,
                    message=str(e),
                    provider=provider.provider_name,
                    model=model,
                    retryable=code in (ErrorCode.TRANSIENT, ErrorCode.RATE_LIMIT, ErrorCode.TIMEOUT),
                    raw=e,
                )

        return retry(cfg)(_open)()

    def _starter_iterable():
        resp_ctx = _starter()
        try:
            timeout_cfg = get_timeout_config()
            try:
                with operation_timeout(timeout_cfg.start_timeout_seconds):
                    with resp_ctx as resp:
                        resp.raise_for_status()
                        for line in resp.iter_lines():
                            if not line:
                                continue
                            try:
                                yield json.loads(line)
                            except json.JSONDecodeError as e:
                                normalized_log_event(
                                    provider._logger,
                                    "stream.decode_error",
                                    ctx,
                                    phase="mid_stream",
                                    attempt=None,
                                    emitted=None,
                                    tokens=None,
                                    error=str(e),
                                    line=line,
                                )
                                continue
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

    def _translator(obj: Dict[str, Any]) -> Optional[str]:
        if not isinstance(obj, dict):
            return None
        return None if obj.get("done") is True else obj.get("response") or None

    # Metrics for finalize event
    _t0 = time.perf_counter()
    _emitted_count = 0
    _first_token_time_ms: Optional[float] = None

    adapter = BaseStreamingAdapter(
        ctx=ctx,
        provider_name=provider.provider_name,
        model=model,
        starter=_starter_iterable,
        translator=_translator,
        retry_config_factory=lambda phase: build_retry_config(provider.provider_name, provider._logger, ctx, phase=phase),
        logger=provider._logger,
    )

    for ev in adapter.run():
        if ev is not None and ev.delta:
            if _first_token_time_ms is None:
                _first_token_time_ms = (time.perf_counter() - _t0) * 1000.0
            _emitted_count += 1
            with suppress(Exception):
                record_observation(provider.provider_name, model, "streaming", True)
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
