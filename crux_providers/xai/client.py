"""XAIProvider adapter.

Refactored to leverage ``BaseOpenAIStyleProvider`` for shared orchestration:
start-phase timeout, retry, normalized logging, and streaming via
``BaseStreamingAdapter``. Keeps xAI defaults and provider naming intact.
"""

from __future__ import annotations

from typing import Any, Optional

try:
    from openai import OpenAI
except Exception:  # pragma: no cover
    OpenAI = None  # type: ignore

from ..base.interfaces import HasDefaultModel
from ..base.logging import get_logger
from ..base.openai_style_parts import BaseOpenAIStyleProvider, _ProviderInit
from ..config.defaults import (
    XAI_DEFAULT_BASE_URL,
    XAI_DEFAULT_MODEL,
)


class XAIProvider(BaseOpenAIStyleProvider, HasDefaultModel):
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        registry: Any | None = None,
    ) -> None:
        init = _ProviderInit(
            api_key=api_key,
            base_url=base_url or XAI_DEFAULT_BASE_URL,
            default_model=model or XAI_DEFAULT_MODEL,
            logger_name="providers.xai",
            sdk_sentinel=OpenAI,
            structured_streaming_supported=False,
        )
        super().__init__(init)
        self._logger = get_logger("providers.xai")

    @property
    def provider_name(self) -> str:
        return "xai"

    def _make_client(self):
        return OpenAI(api_key=self._api_key, base_url=self._base_url)  # type: ignore[arg-type]
