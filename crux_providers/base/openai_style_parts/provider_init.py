"""Initialization dataclass for OpenAI-style providers.

Encapsulates common constructor parameters used by ``BaseOpenAIStyleProvider``.

Docstring policy: Describes purpose, parameters, and external dependencies. No
I/O occurs here; this is a pure data container.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional


@dataclass(frozen=True)
class _ProviderInit:
    """Initialization bundle for ``BaseOpenAIStyleProvider``.

    Attributes:
        api_key: Credential string used by SDK clients.
        base_url: Provider base URL for the OpenAI-style API.
        default_model: Default model to use when a request doesn't specify one.
        logger_name: Structured logger name (e.g., ``providers.deepseek``).
        sdk_sentinel: Module/class used to detect SDK availability for streaming.
        structured_streaming_supported: Whether JSON/tools streaming is supported.
    """

    api_key: Optional[str]
    base_url: Optional[str]
    default_model: str
    logger_name: str
    sdk_sentinel: Any | None
    structured_streaming_supported: bool = False


__all__ = ["_ProviderInit"]
