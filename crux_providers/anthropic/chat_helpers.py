"""Anthropic non-streaming chat helpers.

Purpose:
- Encapsulate the non-streaming chat flow used by the Anthropic provider to
  keep ``helpers.py`` under the file-size policy. This module delegates to
  shared parameter builders and retry/timeouts utilities.

External dependencies:
- Optional runtime dependency on ``anthropic`` SDK (imported lazily via the
  provider). This module itself does not import the SDK directly.

Timeouts & Retries:
- Start phase is wrapped with ``operation_timeout`` derived from
  ``get_timeout_config``. Retries are configured via ``build_retry_config``
  and executed using the shared ``retry`` helper.
"""

from __future__ import annotations

import time
from typing import Any

from ..base.constants import MISSING_API_KEY_ERROR
from ..base.errors import ErrorCode, ProviderError, classify_exception
from ..base.logging import LogContext, normalized_log_event
from ..base.models import ChatRequest, ChatResponse, ContentPart, ProviderMetadata
from ..base.resilience.retry import retry
from ..base.timeouts import get_timeout_config, operation_timeout
from ..base.tokens import (
    extract_anthropic_token_usage,
    PLACEHOLDER_USAGE,
)
from ..base.utils.messages import extract_system_and_user
from ..base.capabilities import record_observation

from .helpers import (
    build_params,
    build_retry_config,
)


def extract_text(resp: Any) -> str:
    """Extract newline-joined text content from an Anthropic response object.

    Parameters:
        resp: The raw response returned by the Anthropic SDK.

    Returns:
        A single string containing the joined text parts. Returns an empty
        string if the response has no textual parts or if access fails.

    Failure modes:
        - Any exception during extraction is swallowed and results in an empty
          string to keep consumers resilient.
    """
    try:
        from ..base.stubs import AnthropicResponse  # local import, safe stub

        typed: AnthropicResponse = resp  # type: ignore[assignment]
        parts = [
            p.text or ""
            for p in typed.content
            if p.type == "text" and (p.text or "")
        ]
        return "\n".join(parts)
    except Exception:
        return ""


def invoke_messages_create(client: Any, params: dict, model: str, provider_name: str):
    """Call ``client.messages.create`` with robust error mapping.

    Translates unexpected exceptions into ``ProviderError`` with classified
    error codes for consistent handling upstream.

    Parameters:
        client: Anthropic SDK client (already constructed by caller).
        params: Mapping of request parameters.
        model: Target model name for error context.
        provider_name: Provider identifier for error context.

    Returns:
        The raw SDK response object representing the created message.

    Raises:
        ProviderError: On any underlying SDK exception. ``retryable`` is set
        for transient/rate-limit/timeout classes.
    """
    try:
        return client.messages.create(**params)
    except Exception as e:  # pragma: no cover
        code = classify_exception(e)
        raise ProviderError(
            code=code,
            message=str(e),
            provider=provider_name,
            model=model,
            retryable=code
            in (ErrorCode.TRANSIENT, ErrorCode.RATE_LIMIT, ErrorCode.TIMEOUT),
            raw=e,
        ) from e


def chat_impl(provider, request: ChatRequest) -> ChatResponse:
    """Unified non-streaming chat implementation for Anthropic providers.

    Parameters:
        provider: The provider instance exposing ``_logger``, ``_api_key``,
            ``_model``, ``_counters``, ``provider_name``, and ``_create_client``.
        request: Structured chat request with messages/options.

    Returns:
        ChatResponse: Normalized response including text, parts, and metadata.
    """
    model = request.model or provider._model
    ctx = LogContext(provider=provider.provider_name, model=model)
    provider._counters.record_start()

    # SDK availability check
    try:
        import anthropic as _anth  # type: ignore
    except Exception:  # pragma: no cover
        _anth = None  # type: ignore
    if _anth is None:
        normalized_log_event(
            provider._logger,
            "chat.error",
            ctx,
            phase="start",
            error="anthropic SDK not installed",
            error_code=None,
            tokens=None,
            emitted=None,
            attempt=None,
        )
        meta = ProviderMetadata(
            provider_name=provider.provider_name,
            model_name=model,
            extra={"error": "anthropic SDK not installed"},
        )
        return ChatResponse(text=None, parts=None, raw=None, meta=meta)

    if not provider._api_key:
        normalized_log_event(
            provider._logger,
            "chat.error",
            ctx,
            phase="start",
            error=MISSING_API_KEY_ERROR,
            error_code=None,
            tokens=None,
            emitted=None,
            attempt=None,
        )
        meta = ProviderMetadata(
            provider_name=provider.provider_name,
            model_name=model,
            extra={"error": MISSING_API_KEY_ERROR},
        )
        return ChatResponse(text=None, parts=None, raw=None, meta=meta)

    client = provider._create_client()
    system_message, user_content = extract_system_and_user(request.messages)
    params, is_structured = build_params(model, request, system_message, user_content)

    normalized_log_event(
        provider._logger,
        "chat.start",
        ctx,
        phase="start",
        has_tools=bool(request.tools),
        has_schema=bool(request.json_schema),
        max_tokens=request.max_tokens,
        temperature=request.temperature,
        tokens=None,
        emitted=None,
        attempt=None,
        error_code=None,
    )
    t0 = time.perf_counter()
    local_retry_config = build_retry_config(provider.provider_name, provider._logger, ctx)

    timeout_cfg = get_timeout_config()
    try:
        with operation_timeout(timeout_cfg.start_timeout_seconds):
            resp = retry(local_retry_config)(
                lambda: invoke_messages_create(client, params, model, provider.provider_name)
            )()
        latency_ms = (time.perf_counter() - t0) * 1000.0
        normalized_log_event(
            provider._logger,
            "chat.end",
            ctx,
            phase="finalize",
            latency_ms=latency_ms,
            tokens=None,
            emitted=None,
            attempt=None,
            error_code=None,
        )
    except TimeoutError as e:
        provider._counters.record_timeout()
        normalized_log_event(
            provider._logger,
            "chat.error",
            ctx,
            phase="finalize",
            error=str(e),
            error_code=ErrorCode.TIMEOUT.value,
            tokens=None,
            emitted=None,
            attempt=None,
        )
        meta = ProviderMetadata(
            provider_name=provider.provider_name,
            model_name=model,
            latency_ms=None,
            extra={"error": str(e), "code": ErrorCode.TIMEOUT.value, "phase": "start_timeout"},
        )
        return ChatResponse(text=None, parts=None, raw=None, meta=meta)
    except ProviderError as e:  # pragma: no cover
        provider._counters.record_failure(e.code.value)
        normalized_log_event(
            provider._logger,
            "chat.error",
            ctx,
            phase="finalize",
            error=str(e),
            error_code=e.code.value,
            tokens=None,
            emitted=None,
            attempt=None,
        )
        meta = ProviderMetadata(
            provider_name=provider.provider_name,
            model_name=model,
            latency_ms=None,
            extra={"error": e.message, "code": e.code.value},
        )
        return ChatResponse(text=None, parts=None, raw=None, meta=meta)
    except Exception as e:  # pragma: no cover
        code = classify_exception(e)
        provider._counters.record_failure(code.value)
        normalized_log_event(
            provider._logger,
            "chat.error",
            ctx,
            phase="finalize",
            error=str(e),
            error_code=code.value,
            tokens=None,
            emitted=None,
            attempt=None,
        )
        meta = ProviderMetadata(
            provider_name=provider.provider_name,
            model_name=model,
            latency_ms=None,
            extra={"error": str(e), "code": code.value},
        )
        return ChatResponse(text=None, parts=None, raw=None, meta=meta)

    text_joined = extract_text(resp)
    try:
        usage_mapping = extract_anthropic_token_usage(resp)
    except Exception:  # pragma: no cover
        usage_mapping = PLACEHOLDER_USAGE.copy()
    usage_mapping = {
        "prompt": usage_mapping.get("prompt"),
        "completion": usage_mapping.get("completion"),
        "total": usage_mapping.get("total"),
    }
    try:
        if is_structured:
            record_observation(provider.provider_name, model, "json_output", True)
    except Exception:
        ...

    meta = ProviderMetadata(
        provider_name=provider.provider_name,
        model_name=model,
        latency_ms=latency_ms,
        token_param_used="max_tokens",  # nosec B106 - static config field; not a credential
        extra={
            "is_structured": is_structured,
            "token_usage": usage_mapping,
        },
    )
    try:
        provider._counters.record_success(int(latency_ms))
    except Exception as counter_exc:  # pragma: no cover
        normalized_log_event(
            provider._logger,
            "metrics.error",
            ctx,
            phase="finalize",
            error=str(counter_exc),
            error_code=None,
            tokens=None,
            emitted=None,
            attempt=None,
        )
    parts = [ContentPart(type="text", text=text_joined)] if text_joined else None
    return ChatResponse(text=text_joined or None, parts=parts, raw=None, meta=meta)
