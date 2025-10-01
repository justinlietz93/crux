"""AnthropicProvider adapter.

This module implements the Anthropic provider integration using
``anthropic>=0.34`` Messages API (``client.messages.create``) for non-streaming
requests and ``client.messages.stream`` for streaming.

Key behaviors / architecture notes:
* Start-phase timeouts use ``operation_timeout`` – no hard-coded numeric literals.
* Retries are centralized through ``RetryConfig`` with structured attempt logging.
* Streaming leverages a helper generator and normalized logging schema.
* Token Accounting (Issue #59): The Anthropic SDK version presently used in
    this code path does not return explicit token usage statistics. To maintain
    a stable downstream contract (parity with OpenAI provider scaffolding), a
    placeholder ``token_usage`` mapping is injected into ``ProviderMetadata.extra``
    with keys ``prompt``, ``completion`` and ``total`` all set to ``None``.
    Future enhancement: Replace placeholder with real values once exposed by
    the SDK / response object. (See issue #59 for roadmap.)
"""

from __future__ import annotations

from typing import Optional

try:
    import anthropic  # type: ignore
except Exception:  # pragma: no cover
    anthropic = None  # type: ignore

# Local imports (restored to proper module scope)
from ..base.interfaces import (
    HasDefaultModel,
    LLMProvider,
    ModelListingProvider,
    SupportsJSONOutput,
)
from ..base.logging import get_logger
from ..base.metrics import ProviderInvocationCounters
from ..base.models import ChatRequest, ChatResponse
from ..base.repositories.model_registry.repository import ModelRegistryRepository
from ..base.streaming import streaming_supported
from ..config import get_provider_config
from ..config.defaults import ANTHROPIC_DEFAULT_MODEL
from .chat_helpers import chat_impl as _chat_impl
from .helpers import stream_chat_impl as _stream_chat_impl


def _default_model() -> str:
    """Return the centralized default Anthropic model name.

    Uses the constant from `providers.config.defaults` to avoid scattered
    literals and keep a single source of truth for defaults.

    Returns:
        str: Default model identifier for Anthropic.
    """
    return ANTHROPIC_DEFAULT_MODEL


class AnthropicProvider(
    LLMProvider, SupportsJSONOutput, ModelListingProvider, HasDefaultModel
):
    """Adapter for the Anthropic LLM provider supporting chat and streaming.

    Responsibilities:
    * Build and dispatch chat requests (messages.create)
    * Provide streaming interface with normalized logging events
    * Surface model listings via a registry abstraction
    * Perform structured retry + start-phase timeout handling

    Token Accounting (Issue #59):
    A placeholder ``token_usage`` object is attached to ``ProviderMetadata.extra``
    for chat completions to preserve a consistent metrics / logging surface.
    The mapping shape is ``{"prompt": None, "completion": None, "total": None}``.
    Once Anthropic's SDK (or an upgraded response schema) exposes token usage
    fields, this placeholder will be replaced with real counts.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        registry: Optional[ModelRegistryRepository] = None,
    ) -> None:
        cfg = get_provider_config("anthropic")
        key = (
            api_key or cfg.get("api_key") or getattr(anthropic, "api_key", None) or None
        )
        self._api_key = key
        self._model = model or cfg.get("model") or _default_model()
        self._registry = registry or ModelRegistryRepository()
        self._logger = get_logger("providers.anthropic")
        # Invocation counters (Issue #61) - provider-level lifecycle metrics
        self._counters = ProviderInvocationCounters(provider="anthropic")

    @property
    def provider_name(self) -> str:
        """Returns the name of the provider.

        This property identifies the provider as 'anthropic'.

        Returns:
            str: The provider name.
        """
        return "anthropic"

    def default_model(self) -> Optional[str]:
        """Returns the default model name for this provider instance.

        This method provides the model name currently set for the provider.

        Returns:
            Optional[str]: The default model name.
        """
        return self._model

    def supports_json_output(self) -> bool:
        """Indicates whether the provider supports JSON output.

        This method returns True to signal support for JSON-style structured output.

        Returns:
            bool: True if JSON output is supported.
        """
        return True

    def list_models(self, refresh: bool = False):
        """Lists available models for the Anthropic provider.

        This method retrieves the list of models, optionally refreshing the cache.

        Args:
            refresh (bool): Whether to refresh the model list from the source.

        Returns:
            list: A list of available model names.
        """
        return self._registry.list_models("anthropic", refresh=refresh)

    def chat(self, request: ChatRequest) -> ChatResponse:
        """Delegate non-streaming chat to helpers implementation."""
        return _chat_impl(self, request)

    # ---- Streaming ----
    def supports_streaming(self) -> bool:  # runtime-checkable capability
        """Return True if Anthropic SDK installed and API key present."""
        return streaming_supported(
            anthropic,
            require_api_key=True,
            api_key_getter=lambda: (self._api_key or ""),  # type: ignore[attr-defined]
        )

    def stream_chat(self, request: ChatRequest):
        """Delegate streaming to helpers implementation to keep file lean."""
        yield from _stream_chat_impl(self, request)

    # ---- Internal helpers ----
    # _extract_messages removed in favor of shared helper extract_system_and_user

    # ---- Internal refactored helpers ----

    # -------------------- Invocation Counters Introspection --------------------
    def counters_snapshot(self, reset: bool = False):
        """Return snapshot of invocation counters for Anthropic provider.

        Args:
            reset: Whether to reset internal state after snapshot.
        """
        return self._counters.snapshot(reset=reset)

    def _create_client(self):
        """Instantiate the Anthropic SDK client.

        Summary:
            Returns an ``anthropic.Anthropic`` instance configured with the
            provider's API key when available.

        Returns:
            anthropic.Anthropic: A client ready to issue requests against the
            Anthropic Messages API.

        Raises:
            AttributeError: If the ``anthropic`` module is not available. In normal
                flows we guard earlier via ``supports_streaming`` and checks in
                ``chat``; callers should validate availability when necessary.

        Side Effects:
            None.
        """
        return (
            anthropic.Anthropic(api_key=self._api_key)
            if self._api_key
            else anthropic.Anthropic()
        )

    # The following invocation helpers have been moved to anthropic.helpers
    # and are now consumed via closures above:
    # - invoke_messages_create -> _invoke_messages_create_helper
    # - start_stream_context -> _start_stream_context_helper

    # Removed bespoke streaming loop helpers in favor of BaseStreamingAdapter.
