"""OpenRouter provider adapter (OpenAI-style over HTTP).

Summary:
- Non-stream chat via `httpx` with centralized timeouts and retry
- Streaming via `BaseStreamingAdapter` (standard metrics + finalize logging)
- Capability gating with `streaming_supported()`; structured streaming disallowed

Timeouts & Retries:
- Use `get_timeout_config()` and `operation_timeout` for start phases
- Use `retry()` wrappers for HTTP calls and streaming start

Errors & Observability:
- Normalize exceptions with `classify_exception`
- Emit structured start/finalize events; streaming captures `time_to_first_token_ms`,
  `total_duration_ms`, `emitted_count`

This module orchestrates I/O only; business logic lives in shared base layers.
"""

from __future__ import annotations

import json
from typing import Any, Dict, Optional

from ..base.constants import MISSING_API_KEY_ERROR, STRUCTURED_STREAMING_UNSUPPORTED
from ..base.timeouts import get_timeout_config, operation_timeout
from ..base.http import get_httpx_client
from ..base.errors import ErrorCode, ProviderError, classify_exception
from ..base.interfaces import HasDefaultModel, LLMProvider, SupportsJSONOutput
from ..base.logging import LogContext, get_logger, log_event, normalized_log_event
from ..base.models import ChatRequest, ChatResponse, ProviderMetadata
from ..base.resilience.retry import retry
from ..base.streaming import ChatStreamEvent
from ..base.streaming import BaseStreamingAdapter
from ..config import get_provider_config
from ..base.streaming import streaming_supported
from ..config.defaults import OPENROUTER_DEFAULT_MODEL, OPENROUTER_DEFAULT_BASE_URL

# Mixin helpers split out to keep this file under 500 LOC and reduce duplication
from .helpers import OpenRouterCommonMixin
from .chat_helpers import OpenRouterChatMixin
from .stream_helpers import (
    OpenRouterStreamingMixin,
    translate_text_from_line,
    translate_structured_from_line,
)


class OpenRouterProvider(
    OpenRouterCommonMixin,
    OpenRouterChatMixin,
    OpenRouterStreamingMixin,
    LLMProvider,
    SupportsJSONOutput,
    HasDefaultModel,
):
    """OpenRouter LLM provider implementation.

    This provider issues chat completions and streaming completions to the
    OpenRouter API using an OpenAI-compatible endpoint. Streaming is mediated
    through the shared `BaseStreamingAdapter` for consistent behavior across
    providers.

    Parameters:
        api_key: Explicit API key override; if not provided, resolved from
            provider config.
        model: Default model name; if not provided, resolved from provider
            config (defaults to ``"openrouter/auto"``).
        base_url: API base URL; if not provided, resolved from provider config
            (defaults to ``"https://openrouter.ai/api/v1"``).
        registry: Optional external registry or DI container handle; unused in
            this adapter but accepted for interface compatibility.

    Side effects:
        - Reads provider-level configuration via ``get_provider_config("openrouter")``.
        - Initializes a structured provider logger.
    """
    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        registry: Any | None = None,
    ) -> None:
        cfg = get_provider_config("openrouter")
        self._api_key = api_key or cfg.get("api_key")
        self._model = model or cfg.get("model", OPENROUTER_DEFAULT_MODEL)
        self._base_url = base_url or cfg.get("base_url", OPENROUTER_DEFAULT_BASE_URL)
        self._system_message = cfg.get("system_message")
        self._logger = get_logger("providers.openrouter")

    @property
    def provider_name(self) -> str:
        """Return the canonical provider slug used across the codebase.

        This identifier is used in logs, metrics, and configuration lookups and
        must remain stable to avoid breaking persisted metadata.

        Returns:
            The string literal "openrouter".
        """
        return "openrouter"

    def default_model(self) -> Optional[str]:
        """Return the default model for this provider instance.

        Returns:
            The default model name configured for the provider.
        """
        return self._model

    def supports_json_output(self) -> bool:
        """Report whether JSON-structured output is supported.

        Returns:
            ``True`` as OpenRouter supports ``response_format`` for
            ``json_object`` and ``json_schema`` in non-streaming mode.
        """
        return True

    def chat(self, request: ChatRequest) -> ChatResponse:
        """Perform a non-streaming chat completion.

        Parameters:
            request: The chat request containing messages, optional tools,
                response schema, and generation parameters.

        Returns:
            A ``ChatResponse`` with text and parts on success. On failure,
            returns a ``ChatResponse`` with ``meta.extra`` including structured
            error information and logs a normalized event.

        Failure modes:
            - Missing API key results in an error response via ``_err_no_key``.
            - Transport and HTTP errors are classified and wrapped into a
              ``ProviderError``; generic exceptions are also normalized.

        Side effects:
            - Performs outbound HTTP I/O to the OpenRouter API using ``httpx``.
            - Emits structured start/end log events.

        Timeout/Retry:
            - The blocking start phase is guarded by ``operation_timeout`` using
              ``get_timeout_config()``.
            - The HTTP call is executed through a retry wrapper (``retry()``)
              applied to the callable returned by ``_make_chat_call``.
        """
        model = request.model or self._model
        ctx = LogContext(provider=self.provider_name, model=model)
        if not self._api_key:
            return self._err_no_key(model)

        # Build request payload & headers
        is_structured = request.response_format == "json_object"
        payload, headers = self._prepare_chat_http(model, request, is_structured)

        # Execute HTTP call with retry + timing
        self._log_chat_start(ctx, request)
        try:
            timeout_cfg = get_timeout_config()
            with operation_timeout(timeout_cfg.start_timeout_seconds):
                text, latency_ms = self._execute_chat(payload, headers, model, ctx)
        except ProviderError as e:  # pragma: no cover
            return self._provider_error_response(e, model, ctx)
        except Exception as e:  # pragma: no cover
            return self._generic_error_response(e, model, ctx)

        # Build response metadata & structured parsing
        return self._build_chat_response(model, text, is_structured, ctx, latency_ms)

    # ---- Streaming ----
    def supports_streaming(self) -> bool:
        """Return True if OpenRouter streaming is supported at runtime.

        Delegates to the centralized ``streaming_supported`` helper so
        capability detection policy (SDK presence + API key requirement) stays
        consistent across all providers. OpenRouter requires only that an API
        key is configured; the HTTP client resides in stdlib/``httpx``, so we
        pass a sentinel object for the SDK presence check.

        Returns:
            ``True`` if runtime capabilities are sufficient for streaming, else
            ``False``.
        """
        return streaming_supported(object(), require_api_key=True, api_key_getter=lambda: self._api_key)

    def stream_chat(self, request: ChatRequest):
        """Stream chat completions using the unified ``BaseStreamingAdapter``.

        This replaces the bespoke streaming loop with the standardized adapter
        to ensure consistent retry-on-start behavior, metrics capture
        (``emitted_count``, ``time_to_first_token_ms``, ``total_duration_ms``),
        and structured finalize logging. Capability gating and structured-
        streaming guards are preserved prior to adapter invocation.

        Parameters:
            request: The chat request including messages and generation params.

        Yields:
            ``ChatStreamEvent`` instances for each translated delta and a
            single terminal event.

        Failure modes:
            - Missing API key or disallowed structured streaming short-circuit
              with a terminal error event via ``_stream_fail``.
            - Start/connect errors are handled by the adapter with retry policy
              and normalized error classification.

        Side effects:
            - Performs outbound HTTP streaming I/O via ``httpx.Client.stream``.
            - Emits structured log events for start and finalize stages.

        Timeout/Retry:
            - Connection start is protected by ``BaseStreamingAdapter`` with
              centralized timeout config.
            - The underlying start callable is wrapped by a retry decorator
              (``retry()``) configured in ``_make_stream_call``.
        """
        model = request.model or self._model
        ctx = LogContext(provider=self.provider_name, model=model)
        self._log_stream_start(ctx, request)
        if not self._api_key:
            yield from self._stream_fail(ctx, model, MISSING_API_KEY_ERROR)
            return
        if self._structured_streaming_disallowed(request):
            yield from self._stream_fail(ctx, model, STRUCTURED_STREAMING_UNSUPPORTED)
            return

        response_format, _ = self._stream_response_format(request)
        messages = self._build_messages(request)
        payload = self._build_payload(model, messages, request, response_format, stream=True)
        headers = self._build_headers()

        def _starter():
            # Returns context manager from httpx.Client.stream via retry wrapper
            return self._make_stream_call(payload, headers, model)()

        def _translator(resp_line) -> Optional[str]:
            # Delegate to helper to keep this module under LOC and centralize logic
            text = translate_text_from_line(resp_line)
            if text is None:
                # Preserve previous decode-error logging behavior on malformed JSON
                try:
                    _ = json.loads(resp_line if isinstance(resp_line, (str, bytes)) else str(resp_line))
                except Exception:
                    log_event(self._logger, "stream.decode_error", ctx, code="DECODE")
            return text

        # Build adapter yielding events from httpx stream iterator lines
        def _start_lines():
            """Start the HTTP stream and yield raw lines (adapter starter)."""
            # _starter() returns the context manager from httpx.Client.stream
            # We must pass the context manager itself, not the function,
            # otherwise "with start_cm as resp" will receive a function and
            # raise: "'function' object does not support the context manager protocol".
            return self._iter_httpx_lines(_starter())
        adapter = BaseStreamingAdapter(
            ctx=ctx,
            provider_name=self.provider_name,
            model=model,
            starter=_start_lines,
            translator=_translator,
            structured_translator=translate_structured_from_line,
            retry_config_factory=self._default_retry_config,
            logger=self._logger,
        )
        yield from adapter.run()

    def _iter_httpx_lines(self, start_cm):
        """Yield raw lines from an ``httpx`` streaming response.

        Parameters:
            start_cm: The context manager returned by ``httpx.Client.stream``.

        Yields:
            Raw ``bytes`` lines as produced by ``Response.iter_lines()``.

        Notes:
            Calls ``raise_for_status()`` prior to iteration and ensures the
            context manager is cleanly exited.
        """
        with start_cm as resp:
            resp.raise_for_status()
            yield from resp.iter_lines()

    # Note: default retry config is provided by OpenRouterStreamingMixin

    # ---- Internal helpers ----
    # Common payload/header builders provided by OpenRouterCommonMixin

    # --- Internal chat helpers (extracted) ---
    # Chat orchestration helpers provided by OpenRouterChatMixin

    # _execute_chat provided by OpenRouterChatMixin

    # _build_chat_response provided by OpenRouterChatMixin

    def _log_chat_start(self, ctx: LogContext, request: ChatRequest) -> None:
        """Emit a normalized structured log event for chat start."""
        normalized_log_event(
            self._logger,
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

    # _make_chat_call provided by OpenRouterChatMixin

    # _maybe_parse_structured provided by OpenRouterChatMixin

    def _provider_error_response(self, e: ProviderError, model: str, ctx: LogContext) -> ChatResponse:
        """Build a normalized error response from a ``ProviderError``.

        Parameters:
            e: The provider error raised by HTTP or transport layers.
            model: Target model name for metadata.
            ctx: Log context for event emission.

        Returns:
            A ``ChatResponse`` populated with provider metadata and error
            details in ``meta.extra``.
        """
        normalized_log_event(
            self._logger,
            "chat.error",
            ctx,
            phase="finalize",
            attempt=None,
            emitted=False,
            tokens=None,
            error=str(e),
            error_code=e.code.value,
        )
        meta = ProviderMetadata(provider_name=self.provider_name, model_name=model, latency_ms=None, extra={"error": e.message, "code": e.code.value})
        return ChatResponse(text=None, parts=None, raw=None, meta=meta)

    def _generic_error_response(self, e: Exception, model: str, ctx: LogContext) -> ChatResponse:
        """Build a normalized error response from an untyped exception.

        Parameters:
            e: The raw exception encountered.
            model: Target model name for metadata.
            ctx: Log context for event emission.

        Returns:
            A ``ChatResponse`` populated with provider metadata and error
            details in ``meta.extra``.
        """
        code = classify_exception(e)
        normalized_log_event(
            self._logger,
            "chat.error",
            ctx,
            phase="finalize",
            attempt=None,
            emitted=False,
            tokens=None,
            error=str(e),
            error_code=code.value,
        )
        meta = ProviderMetadata(provider_name=self.provider_name, model_name=model, latency_ms=None, extra={"error": str(e), "code": code.value})
        return ChatResponse(text=None, parts=None, raw=None, meta=meta)

    def _log_stream_start(self, ctx: LogContext, request: ChatRequest) -> None:
        """Emit a normalized structured log event for stream start."""
        normalized_log_event(
            self._logger,
            "stream.start",
            ctx,
            phase="start",
            attempt=None,
            emitted=None,
            tokens=None,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
        )

    def _structured_streaming_disallowed(self, request: ChatRequest) -> bool:
        """Return True when structured streaming is disallowed for request."""
        return bool(request.response_format == "json_object" or request.json_schema or request.tools)

    def _stream_response_format(self, request: ChatRequest):
        """Derive ``response_format`` for streaming path using shared helper.

        Delegates to ``prepare_response_format`` from the OpenAI-style helpers
        to ensure a single translation logic for JSON outputs (``json_object``
        and ``json_schema``). Note that structured streaming is disallowed by
        this provider; callers must still gate via
        ``_structured_streaming_disallowed`` before invoking the adapter.

        Returns:
            Tuple of ``(response_format_dict_or_none, is_structured: bool)``.
        """
        from ..base.openai_style_parts.style_helpers import prepare_response_format

        response_format, is_structured = prepare_response_format(request)
        return response_format, is_structured

    def _make_stream_call(self, payload: Dict[str, Any], headers: Dict[str, str], model: str):
        """Return a callable opening a streaming request with unified timeout.

        Uses configured start timeout with a multiplier to tolerate longer model
        warm-up while still bounding connection establishment and header
        latency. The returned callable is wrapped with a centralized retry
        decorator (``@retry()``).

        Parameters:
            payload: JSON payload for the request.
            headers: HTTP headers including authorization.
            model: Target model name for error context.

        Returns:
            A zero-argument callable that returns the context manager from
            ``httpx.Client.stream``.

        Failure handling:
            - Catches transport exceptions, classifies them, and raises a
              ``ProviderError`` that indicates whether a retry is appropriate.
        """
    # Returns nested callable for retry wrapper.
        @retry()
        def _start_stream():
            try:
                client = get_httpx_client(self._base_url, purpose="openrouter.stream")
                return client.stream(
                    "POST",
                    "/chat/completions",
                    json=payload,
                    headers=headers,
                )
            except Exception as e:
                code = classify_exception(e)
                raise ProviderError(
                    code=code,
                    message=str(e),
                    provider=self.provider_name,
                    model=model,
                    retryable=code in (ErrorCode.TRANSIENT, ErrorCode.RATE_LIMIT, ErrorCode.TIMEOUT),
                    raw=e,
                ) from e
        return _start_stream

    # Note: legacy bespoke stream delta iterator removed; unified adapter path

    def _stream_fail(self, ctx: LogContext, model: str, error: str):
        """Emit a start-phase stream error and yield a terminal event.

        Parameters:
            ctx: Log context.
            model: Target model name for event metadata.
            error: Human-readable error message to surface.

        Yields:
            A single terminal ``ChatStreamEvent`` conveying the error.
        """
        normalized_log_event(
            self._logger,
            "stream.error",
            ctx,
            phase="start",
            attempt=None,
            emitted=False,
            tokens=None,
            error=error,
            error_code="START_FAIL",
        )
        yield ChatStreamEvent(provider=self.provider_name, model=model, delta=None, finish=True, error=error)

    def _err_no_key(self, model: str) -> ChatResponse:
        """Return an error ``ChatResponse`` for missing API key.

        Parameters:
            model: Target model name for metadata.

        Returns:
            A ``ChatResponse`` with ``meta.extra`` populated with a missing-key
            error message.
        """
        meta = ProviderMetadata(provider_name=self.provider_name, model_name=model, extra={"error": MISSING_API_KEY_ERROR})
        return ChatResponse(text=None, parts=None, raw=None, meta=meta)
