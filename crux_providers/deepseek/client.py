"""DeepseekProvider adapter using OpenAI-compatible Chat Completions API.

Refactored to use ``BaseOpenAIStyleProvider`` for shared chat/stream logic,
including start-phase timeout, retry, structured logging, and streaming via
``BaseStreamingAdapter``. This removes duplicated orchestration while keeping
Deepseek-specific defaults (base_url, model) and provider name intact.
"""

from __future__ import annotations

from typing import Any, Optional

try:
    from openai import OpenAI  # type: ignore
except Exception:  # pragma: no cover
    OpenAI = None  # type: ignore

from ..base.interfaces import HasDefaultModel
from ..base.logging import get_logger
from ..base.openai_style_parts import BaseOpenAIStyleProvider, _ProviderInit
from ..config.defaults import (
    DEEPSEEK_DEFAULT_BASE_URL,
    DEEPSEEK_DEFAULT_MODEL,
)


class DeepseekProvider(BaseOpenAIStyleProvider, HasDefaultModel):
    """Deepseek provider built on the OpenAI-style base class."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        registry: Any | None = None,
    ) -> None:
        """Initialize the DeepseekProvider with API key, base URL, and model.

        Sets up the provider with Deepseek-specific defaults and logging. Inherits shared logic from the base OpenAI-style provider.

        Args:
            api_key: The API key for authenticating with Deepseek.
            base_url: The base URL for the Deepseek API.
            model: The default model to use for requests.
            registry: Optional model registry for provider integration.
        """
        init = _ProviderInit(
            api_key=api_key,
            base_url=base_url or DEEPSEEK_DEFAULT_BASE_URL,
            default_model=model or DEEPSEEK_DEFAULT_MODEL,
            logger_name="providers.deepseek",
            sdk_sentinel=OpenAI,
            structured_streaming_supported=False,
        )
        super().__init__(init)
        self._logger = get_logger("providers.deepseek")

    @property
    def provider_name(self) -> str:
        """Return the name of the provider.

        This property identifies the provider as 'deepseek'.

        Returns:
            str: The provider name.
        """
        return "deepseek"

    def _make_client(self):
        """Create and return an OpenAI client instance for Deepseek.

        This method initializes the OpenAI client with the configured API key and base URL.

        Returns:
            OpenAI: An instance of the OpenAI client configured for Deepseek.
        """
        return OpenAI(api_key=self._api_key, base_url=self._base_url)  # type: ignore[arg-type]

    # All behavior for chat/stream is inherited from BaseOpenAIStyleProvider.
