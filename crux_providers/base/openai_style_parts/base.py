"""BaseOpenAIStyleProvider implementation split from the monolithic module.

Purpose:
- Provide a reusable base class for providers implementing an OpenAI-compatible
  Chat Completions interface while adhering to governance constraints.

External dependencies:
- Relies on provider SDKs supplied by concrete subclasses. This module does not
  perform network I/O directly; it orchestrates calls into the SDK.

Fallback semantics:
- Missing SDK or API key yields lightweight error metadata in non-stream mode;
  streaming emits a terminal error event.

Timeout strategy:
- Wraps only the start/first-byte phase in ``operation_timeout`` using
  ``get_timeout_config()``. Mid-stream cancellation is not enforced.
"""

from __future__ import annotations

import asyncio
from typing import Iterator, Optional
from contextlib import suppress

from ..constants import MISSING_API_KEY_ERROR, STRUCTURED_STREAMING_UNSUPPORTED
from ..errors import ErrorCode, ProviderError, classify_exception
from ..interfaces import HasDefaultModel, LLMProvider, SupportsJSONOutput, SupportsStreaming
from ..logging import LogContext, get_logger, normalized_log_event
from ..models import ChatRequest, ChatResponse, ProviderMetadata
from ..resilience.retry import RetryConfig, retry
from ..streaming import BaseStreamingAdapter, ChatStreamEvent, streaming_supported
from ..middleware.registry import get_middleware_chain
from ..timeouts import get_timeout_config, operation_timeout
from .style_helpers import (
    extract_openai_text,
    prepare_response_format,
    extract_messages_and_format,
    build_chat_params,
    build_stream_params,
    invoke_create,
)
from .structured import translate_openai_structured_chunk
from ..utils.messages import extract_system_and_user
from ...config import get_provider_config
from ..capabilities import record_observation
from .client_protocol import _ChatCompletionsClient
from .provider_init import _ProviderInit
from .nonstream_helpers import (
    run_nonstream_with_timeout_and_retry,
    nonstream_error_response,
    build_nonstream_success_response,
)


class BaseOpenAIStyleProvider(LLMProvider, SupportsJSONOutput, HasDefaultModel, SupportsStreaming):
    """Reusable base class for OpenAI-compatible providers.

    Subclasses must implement:
    - ``provider_name``: canonical provider identifier.
    - ``_make_client()``: create and return an SDK client implementing
      :class:`_ChatCompletionsClient` semantics.

    They may also override ``supports_streaming`` if SDK gating differs.
    """

    def __init__(self, init: _ProviderInit) -> None:
        """Initialize a provider with shared configuration.

        Parameters:
            init: Dataclass containing api key, base_url, default model, logger name, and SDK sentinel.
        """
        self._api_key = init.api_key
        self._base_url = init.base_url
        self._model = init.default_model
        self._logger = get_logger(init.logger_name)
        self._sdk_sentinel = init.sdk_sentinel
        self._structured_streaming_supported = init.structured_streaming_supported

    # ----- Abstract surface -----
    @property
    def provider_name(self) -> str:  # pragma: no cover - abstract
        """Return the canonical provider name (e.g., ``deepseek``)."""
        raise NotImplementedError

    def _make_client(self) -> _ChatCompletionsClient:  # pragma: no cover - abstract
        """Create and return the underlying SDK client.

        Implementations should pass ``api_key`` and ``base_url`` where applicable.
        """
        raise NotImplementedError

    # ----- Capability & basic info -----
    def default_model(self) -> Optional[str]:
        """Return the default model name configured for this provider."""
        return self._model

    def supports_json_output(self) -> bool:
        """Indicate that OpenAI-style providers support JSON output formats."""
        return True

    def supports_streaming(self) -> bool:
        """Return True when the SDK is present and an API key is available."""
        return streaming_supported(
            self._sdk_sentinel,
            require_api_key=True,
            api_key_getter=lambda: self._api_key,
        )

    # ----- Chat -----
    def chat(self, request: ChatRequest) -> ChatResponse:
        """Perform a non-streaming chat completion using the provider SDK.

        This method delegates precondition checks and the actual invocation to
        smaller helpers to minimize complexity while preserving behavior.
        """
        model = request.model or self._model
        ctx = LogContext(provider=self.provider_name, model=model)
        # Allow middleware to mutate the request before logging/validation
        with suppress(Exception):
            request = get_middleware_chain().run_before_chat(ctx, request)

        self._log_chat_start(ctx, request)

        pre = self._check_nonstream_prereqs(model)
        if pre is not None:
            return pre

        resp = self._invoke_nonstream_chat(model=model, request=request, ctx=ctx)
        with suppress(Exception):
            resp = get_middleware_chain().run_after_chat(ctx, resp)
        return resp

    # ----- Streaming -----

    def stream_chat(self, request: ChatRequest) -> Iterator[ChatStreamEvent]:
        """Stream chat responses as incremental delta events.

        Preconditions and starter creation are delegated to helpers to reduce
        complexity while maintaining behavior and logging.
        """
        model = request.model or self._model
        ctx = LogContext(provider=self.provider_name, model=model)
        # Allow middleware to mutate request prior to gating/logging
        with suppress(Exception):
            request = get_middleware_chain().run_before_stream(ctx, request)

        failed = self._check_stream_prereqs(request)
        if failed is not None:
            yield failed
            return

        self._log_stream_start(ctx, request)

        messages = self._build_stream_messages(request)
        response_format, _ = prepare_response_format(request)
        starter = self._build_stream_starter(model=model, request=request, messages=messages, response_format=response_format, ctx=ctx)
        # Attach OpenAI-style structured translator to surface function-call partials
        adapter = BaseStreamingAdapter(
            ctx=ctx,
            provider_name=self.provider_name,
            model=model,
            starter=starter,
            translator=self._translate_openai_delta,
            structured_translator=translate_openai_structured_chunk,
            retry_config_factory=lambda phase: self._build_retry_config(ctx, phase=phase),
            logger=self._logger,
        )
        emitted_any = False
        for ev in adapter.run():
            if ev is not None and ev.delta and not emitted_any:
                emitted_any = True
                try:
                    record_observation(self.provider_name, model, "streaming", True)
                except Exception:
                    ...
            yield ev

    # ----- helpers -----

    def _build_retry_config(self, ctx: LogContext, phase: Optional[str] = None) -> RetryConfig:
        retry_cfg_raw = {}
        try:
            retry_cfg_raw = get_provider_config(self.provider_name).get("retry", {}) or {}
        except Exception:  # pragma: no cover - defensive
            retry_cfg_raw = {}
        max_attempts = int(retry_cfg_raw.get("max_attempts", 3))
        delay_base = float(retry_cfg_raw.get("delay_base", 2.0))

        def _attempt_logger(*, attempt: int, max_attempts: int, delay, error: ProviderError | None):  # type: ignore[override]
            normalized_log_event(
                self._logger,
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

        # Avoid retrying TIMEOUTs during start phase. Transient + rate-limit remain retryable.
        retryable_codes = (
            (ErrorCode.TRANSIENT, ErrorCode.RATE_LIMIT)
            if (phase == "start")
            else (ErrorCode.TRANSIENT, ErrorCode.RATE_LIMIT, ErrorCode.TIMEOUT)
        )
        return RetryConfig(max_attempts=max_attempts, delay_base=delay_base, retryable_codes=retryable_codes, attempt_logger=_attempt_logger)

    # Small helper shared by chat/stream to translate response formatting
    def _prepare_response_format(self, request: ChatRequest) -> tuple[dict | None, bool]:
        """Compatibility wrapper: delegates to ``prepare_response_format``.

        Kept for backward-compatibility with tests that may patch this method.
        """
        return prepare_response_format(request)

    # ----- extracted helpers (chat) -----

    def _log_chat_start(self, ctx: LogContext, request: ChatRequest) -> None:
        """Emit a normalized start log for non-streaming chat.

        Parameters:
            ctx: Context carrying provider and model metadata for logging.
            request: Chat request parameters used for contextual fields.
        """
        normalized_log_event(
            self._logger,
            "chat.start",
            ctx,
            phase="start",
            attempt=None,
            emitted=None,
            tokens=None,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
            has_schema=bool(request.json_schema),
            has_tools=bool(request.tools),
        )

    def _check_nonstream_prereqs(self, model: str) -> ChatResponse | None:
        """Validate SDK presence and API key before non-stream invocation.

        Returns a ``ChatResponse`` with error details when a prerequisite fails;
        otherwise returns ``None`` to proceed.
        """
        if self._sdk_sentinel is None:
            meta = ProviderMetadata(
                provider_name=self.provider_name,
                model_name=model,
                extra={"error": "openai SDK not installed"},
            )
            return ChatResponse(text=None, parts=None, raw=None, meta=meta)
        if not self._api_key:
            meta = ProviderMetadata(
                provider_name=self.provider_name,
                model_name=model,
                extra={"error": MISSING_API_KEY_ERROR},
            )
            return ChatResponse(text=None, parts=None, raw=None, meta=meta)
        return None

    def _invoke_nonstream_chat(self, *, model: str, request: ChatRequest, ctx: LogContext) -> ChatResponse:
        """Execute the chat completion call with retries, timeout, and logging.

        Delegates timeout/retry orchestration and response shaping to
        ``nonstream_helpers`` to reduce method length while preserving
        behavior and logging semantics.
        """
        messages, response_format, is_structured = extract_messages_and_format(request)

        def _invoke():
            """Invoke the chat completion using the provider's client.

            This function creates the client, builds the chat parameters, and calls the provider's chat creation method.
            """
            client = self._make_client()
            params = build_chat_params(model, messages, request, response_format)
            return invoke_create(client, params, model, self.provider_name)

        timeout_cfg = get_timeout_config()
        try:
            resp, latency_ms = run_nonstream_with_timeout_and_retry(
                invoke_fn=_invoke,
                ctx=ctx,
                logger=self._logger,
                retry_config_factory=lambda: self._build_retry_config(ctx, phase="start"),
                start_timeout_seconds=timeout_cfg.start_timeout_seconds,
            )
            text = extract_openai_text(resp)
            return build_nonstream_success_response(
                provider_name=self.provider_name,
                model=model,
                text=text,
                is_structured=is_structured,
                latency_ms=latency_ms,
            )
        except Exception as e:  # noqa: BLE001
            return nonstream_error_response(
                provider_name=self.provider_name,
                model=model,
                ctx=ctx,
                logger=self._logger,
                exc=e,
            )

    # ----- extracted helpers (stream) -----

    def _check_stream_prereqs(self, request: ChatRequest) -> ChatStreamEvent | None:
        """Validate streaming prerequisites; return a terminal error event when failing.

        Parameters:
            request: The streaming chat request.

        Returns:
            A terminal ``ChatStreamEvent`` describing the failure, or ``None`` if ok.
        """
        if not self.supports_streaming():
            return ChatStreamEvent(
                provider=self.provider_name,
                model=request.model,
                delta=None,
                finish=True,
                error="openai SDK not installed",
            )

        if not self._structured_streaming_supported and (
            request.response_format == "json_object" or request.json_schema or request.tools
        ):
            try:
                record_observation(self.provider_name, request.model or self._model, "structured_streaming", False)
            except Exception:
                ...
            return ChatStreamEvent(
                provider=self.provider_name,
                model=request.model,
                delta=None,
                finish=True,
                error=STRUCTURED_STREAMING_UNSUPPORTED,
            )
        return None

    def _log_stream_start(self, ctx: LogContext, request: ChatRequest) -> None:
        """Emit a normalized start log for streaming chat.

        Parameters:
            ctx: Context with provider/model metadata.
            request: Chat request providing additional contextual fields.
        """
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

    def _build_stream_messages(self, request: ChatRequest) -> list[dict[str, str]]:
        """Construct a compact OpenAI-style message list from the request."""
        system_message, user_content = extract_system_and_user(request.messages)
        messages: list[dict[str, str]] = []
        if system_message:
            messages.append({"role": "system", "content": system_message})
        if user_content:
            messages.append({"role": "user", "content": user_content})
        return messages

    def _build_stream_starter(
        self,
        *,
        model: str,
        request: ChatRequest,
        messages: list[dict[str, str]],
        response_format: dict | None,
        ctx: LogContext,
    ):
        """Construct a starter callable for ``BaseStreamingAdapter``.

        The starter encapsulates retry classification and start-phase timeout.
        """

        @retry(self._build_retry_config(ctx, phase="start"))
        def _start():
            try:
                client = self._make_client()
                params = build_stream_params(model, messages, request, response_format)
                return client.chat.completions.create(**params)
            except Exception as e:  # noqa: BLE001
                if isinstance(e, (TimeoutError, asyncio.TimeoutError)):
                    raise
                code = classify_exception(e)
                raise ProviderError(
                    code=code,
                    message=str(e),
                    provider=self.provider_name,
                    model=model,
                    retryable=code in (ErrorCode.TRANSIENT, ErrorCode.RATE_LIMIT, ErrorCode.TIMEOUT),
                    raw=e,
                )

        timeout_cfg = get_timeout_config()

        def _starter():
            with operation_timeout(timeout_cfg.start_timeout_seconds):
                return _start()

        return _starter

    @staticmethod
    def _translate_openai_delta(chunk) -> Optional[str]:  # noqa: ANN001
        """Translate a streaming chunk into a text delta if present.

        Returns ``None`` when the chunk doesn't contain content.
        """
        try:
            return chunk.choices[0].delta.content  # type: ignore[attr-defined]
        except Exception:
            return None

__all__ = ["BaseOpenAIStyleProvider"]
