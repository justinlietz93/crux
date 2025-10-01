"""Ollama provider adapter.

Purpose:
        Implements chat and streaming generation against the local Ollama HTTP API
        (default `http://localhost:11434`). Follows the unified streaming
        architecture via `BaseStreamingAdapter` with standardized timeouts,
        retries, logging, and metrics.

External dependencies:
        - HTTP client only (`httpx`). No SDK or API key is required since Ollama
            is a local daemon.

Timeout strategy:
        - All blocking start phases are guarded by `operation_timeout` using
            durations from `get_timeout_config()`.
        - No hard-coded numeric timeouts are introduced; HTTP calls are invoked
            with `timeout=None` and rely on the explicit start-phase guard.

Retries and error handling:
        - Centralized retry policy via `RetryConfig` sourced from provider config
            (`get_provider_config`).
        - Exceptions are classified with `classify_exception` and wrapped in
            `ProviderError` with normalized error codes.
        - Structured logging uses `normalized_log_event` with required context.

Fallback semantics:
        - For non-streaming `chat`, errors are surfaced in the `ChatResponse.meta`;
            no hidden fallback is applied.
        - For streaming, unsupported structured streaming requests are rejected
            explicitly with a single terminal event containing
            `STRUCTURED_STREAMING_UNSUPPORTED`.

Metrics:
        - Streaming emits finalize metrics with `time_to_first_token_ms`,
            `total_duration_ms`, and `emitted_count`.
"""

from __future__ import annotations

from typing import Any, Optional

from ..base.streaming import streaming_supported
from ..base.interfaces import HasDefaultModel, LLMProvider, SupportsJSONOutput
from ..base.logging import get_logger
from ..base.models import ChatRequest, ChatResponse
from .helpers import (
    chat_impl as _chat_impl,
    stream_chat_impl as _stream_chat_impl,
)
from ..config import get_provider_config
from ..config.defaults import OLLAMA_DEFAULT_HOST, OLLAMA_DEFAULT_MODEL


def _coerce_non_empty_str(candidate: Any, fallback: str) -> str:
    """Return a sanitized string value derived from ``candidate``.

    Parameters
    ----------
    candidate:
        Arbitrary override sourced from configuration layers (defaults,
        environment variables, or explicit overrides).
    fallback:
        Provider default used when the candidate is missing or empty.

    Returns
    -------
    str
        Non-empty string derived from ``candidate``; falls back to ``fallback``
        when sanitization yields an empty result.
    """

    if isinstance(candidate, str):
        stripped = candidate.strip()
        return stripped or fallback
    if candidate is None:
        return fallback
    coerced = str(candidate).strip()
    return coerced or fallback


class OllamaProvider(LLMProvider, SupportsJSONOutput, HasDefaultModel):
    def __init__(
        self,
        host: Optional[str] = None,
        model: Optional[str] = None,
        registry: Any | None = None,
    ):
        """Initialize the Ollama provider with configuration overrides.

        Parameters
        ----------
        host:
            Explicit base URL for the Ollama daemon. When omitted, the provider
            resolves the value from the layered configuration stack (defaults,
            optional config file, environment variables such as ``OLLAMA_HOST``)
            and finally falls back to ``http://localhost:11434``.
        model:
            Default model name for chat requests lacking an explicit model. The
            same layered configuration resolution applies, honoring
            ``OLLAMA_MODEL`` or config-file overrides before the baked-in
            default of ``gpt-oss:20b``.
        registry:
            Optional dependency injection registry placeholder. Present for
            interface parity; not used directly today.

        Side Effects
        ------------
        Initializes a structured logger for provider operations.
        """
        cfg = get_provider_config(
            "ollama",
            overrides={"host": host, "model": model},
        )
        resolved_host = _coerce_non_empty_str(cfg.get("host"), OLLAMA_DEFAULT_HOST)
        resolved_model = _coerce_non_empty_str(cfg.get("model"), OLLAMA_DEFAULT_MODEL)

        self._host = resolved_host
        self._model = resolved_model
        self._logger = get_logger("providers.ollama")

    @property
    def provider_name(self) -> str:
        """Return the stable provider identifier string."""
        return "ollama"

    def default_model(self) -> Optional[str]:
        """Return the default model configured for this provider, if any."""
        return self._model

    def supports_json_output(self) -> bool:
        """Indicate support for JSON output via Ollama's `format: json`.

        Returns:
            True, since the provider can request JSON-formatted responses.
        """
        return True

    def chat(self, request: ChatRequest) -> ChatResponse:
        """Synchronous, single-response chat invocation against Ollama.

        Parameters:
            request: `ChatRequest` containing messages and generation params.

        Returns:
            `ChatResponse` with text, parts, and metadata. On error, `text` is
            None and error details are attached to `meta.extra`.

        Notes:
            - The blocking start phase is protected by `operation_timeout`.
            - Retries are handled inside `_invoke_non_stream` using provider
              `RetryConfig`.
        """
        return _chat_impl(self, request)

    # Delegated: _chat_core removed in favor of helpers.chat_impl

    # ---- Internal helpers (chat) ----
    # Delegated: prompt building via helpers.prepare_prompt

    # Delegated: payload construction via helpers.build_payload

    # Delegated: HTTP invocation via helpers.invoke_non_stream

    # Delegated: metadata assembly via helpers.build_meta

    # Delegated: error response building via helpers.error_chat_response

    # ---- Streaming ----
    def supports_streaming(self) -> bool:
        """Indicate streaming capability for Ollama.

        Ollama uses a local HTTP daemon; no Python SDK or API key is required.
        Delegates to ``streaming_supported`` with ``sdk_obj=None`` and
        ``require_api_key=False`` so the helper's keyless local allowance applies.
        """
        return streaming_supported(
            None,
            require_api_key=False,
            api_key_getter=lambda: None,
            allow_sdk_absent_if_no_key_required=True,
        )

    def stream_chat(self, request: ChatRequest):
        """Stream chat responses using the unified `BaseStreamingAdapter`.

        Parameters:
            request: `ChatRequest` to stream.

        Yields:
            `ChatStreamEvent` instances. A final event will have `finish=True`.

        Behavior and guarantees:
            - Start-phase (HTTP handshake) is guarded by `operation_timeout`.
            - Retries are driven by `_build_retry_config` from provider config.
            - Structured streaming (tools, JSON schema, JSON-object) is rejected
              with a single terminal event carrying
              `STRUCTURED_STREAMING_UNSUPPORTED`.
            - Finalize logs include streaming metrics (TTFT, total duration,
              emitted count).
        """
        yield from _stream_chat_impl(self, request)

    # Delegated: retry config via helpers.build_retry_config

    # Delegated: helpers.should_reject_stream

    # Delegated: stream payload via helpers.build_stream_payload

    # Removed bespoke streaming helpers in favor of BaseStreamingAdapter
