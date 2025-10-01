"""OpenAI provider adapter built on BaseOpenAIStyleProvider.

This module refactors the OpenAI adapter to reuse the shared
``BaseOpenAIStyleProvider`` that centralizes:
- start-phase timeout via ``operation_timeout(get_timeout_config())``
- structured logging with normalized schema
- centralized retry with attempt logging
- streaming via ``BaseStreamingAdapter``

Public surface remains stable: ``OpenAIProvider`` implements
``LLMProvider`` (chat/stream) and ``SupportsJSONOutput``; model listing
is provided via ``ModelRegistryRepository``.

Timeout & Fallback semantics match the base class. No hard-coded numeric
timeouts are introduced. See base module docstring for details.
"""

from __future__ import annotations

from typing import Optional

from ..base.interfaces import HasDefaultModel, LLMProvider, ModelListingProvider, SupportsJSONOutput
from ..base.interfaces_parts import HasCode, HasValue
from ..base.logging import get_logger, normalized_log_event
from ..base.repositories.model_registry.repository import ModelRegistryRepository
from ..base.resilience.retry import RetryConfig
from ..config import get_provider_config
from ..base.openai_style_parts.base import BaseOpenAIStyleProvider
from ..base.openai_style_parts.provider_init import _ProviderInit

try:
    from openai import OpenAI as _OpenAIClient  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    _OpenAIClient = None  # type: ignore

__all__ = ["OpenAIProvider"]


class OpenAIProvider(BaseOpenAIStyleProvider, LLMProvider, SupportsJSONOutput, ModelListingProvider, HasDefaultModel):
    """OpenAI adapter using the shared OpenAI-style base provider.

    Keeps OpenAI defaults and exposes model listing. Streaming and chat
    orchestration are inherited from the base class.
    """

    def __init__(
        self,
        default_model: Optional[str] = None,
        registry: Optional[ModelRegistryRepository] = None,
    ) -> None:
        """
        Initialize an OpenAIProvider instance with optional default model and registry.

        Sets up the provider with configuration, model registry, and a structured logger.

        Args:
            default_model: Optional default model name to use for requests.
            registry: Optional ModelRegistryRepository instance to use.
        """
        cfg = get_provider_config("openai")
        self._registry = registry or ModelRegistryRepository()
        init = _ProviderInit(
            api_key=cfg.get("api_key") or (cfg.get("api", {}).get("openai", {}).get("api_key") if isinstance(cfg.get("api"), dict) else None),
            base_url=cfg.get("base_url") or (cfg.get("api", {}).get("openai", {}).get("base_url") if isinstance(cfg.get("api"), dict) else None),
            default_model=default_model or cfg.get("model") or "gpt-4o-mini",
            logger_name="providers.openai",
            sdk_sentinel=_OpenAIClient,
            structured_streaming_supported=False,
        )
        super().__init__(init)
        self._logger = get_logger("providers.openai")

    @property
    def provider_name(self) -> str:
        """Return the canonical provider name."""
        return "openai"

    def default_model(self) -> Optional[str]:
        """Return the default model configured for OpenAI."""
        return super().default_model()

    def supports_json_output(self) -> bool:
        """JSON output is supported for OpenAI chat completions."""
        return super().supports_json_output()

    # NOTE: If/when responses API support is needed again, reintroduce a gate here.

    # supports_streaming & stream_chat are inherited from BaseOpenAIStyleProvider

    def list_models(self, refresh: bool = False):
        """Return available models for the OpenAI provider via registry."""
        return self._registry.list_models("openai", refresh=refresh)

    # chat implementation is inherited from BaseOpenAIStyleProvider

    # Resolution helpers now handled in base class; no override needed here.

    # API key presence checks and gating are performed by the base.

    # Missing-key response shaping handled by base class.

    # API config and message shaping now occurs in the base class.

    # Chat invocation logic is inherited from the base class.

    # Retry-wrapped call is implemented in the base class.

    # Error handling is unified in the base.

    # Unexpected error shaping is handled by the base.

    # Response metadata construction is implemented by the base.

    # Response normalization is handled by the base.

    # -------------------- Invocation Counters Introspection --------------------
    # Invocation counters were specific to the previous mixin; omitted here.

    # stream_chat and streaming helpers are inherited from BaseOpenAIStyleProvider

    # -------------------- Internal helpers --------------------

    def _build_retry_config(self, ctx, phase: Optional[str] = None) -> RetryConfig:  # type: ignore[override]
        """Use the shared retry configuration pattern.

        Delegates to the same semantics as other providers by reading
        `retry` from `get_provider_config("openai")`.
        """
        retry_cfg_raw = {}
        try:
            retry_cfg_raw = get_provider_config(self.provider_name).get("retry", {}) or {}
        except Exception:  # pragma: no cover - defensive
            retry_cfg_raw = {}
        max_attempts = int(retry_cfg_raw.get("max_attempts", 3))
        delay_base = float(retry_cfg_raw.get("delay_base", 2.0))

        def _attempt_logger(*, attempt: int, max_attempts: int, delay, error):  # type: ignore[override]
            normalized_log_event(
                self._logger,
                "retry.attempt",
                ctx,
                phase=(phase or "retry"),
                attempt=attempt,
                error_code=((error.code.value if isinstance(error, HasCode) and isinstance(error.code, HasValue) else None) if error else None),
                emitted=None,
                tokens=None,
                max_attempts=max_attempts,
                delay=delay,
                will_retry=bool(error and delay is not None),
            )

        return RetryConfig(max_attempts=max_attempts, delay_base=delay_base, attempt_logger=_attempt_logger)

    # SDK client factory -------------------------------------------------
    def _make_client(self):  # noqa: D401 - construct OpenAI SDK client
        if _OpenAIClient is None:  # pragma: no cover - depends on optional install
            raise RuntimeError("openai SDK not installed; install extras [openai]")
        cfg = get_provider_config("openai")
        api_key = cfg.get("api_key") or (cfg.get("api", {}).get("openai", {}).get("api_key") if isinstance(cfg.get("api"), dict) else None)
        base_url = cfg.get("base_url") or (cfg.get("api", {}).get("openai", {}).get("base_url") if isinstance(cfg.get("api"), dict) else None)
        try:
            return _OpenAIClient(api_key=api_key, base_url=base_url)  # type: ignore[arg-type]
        except TypeError:
            return _OpenAIClient()  # type: ignore[call-arg]
