"""LLMProvider Protocol (single-class module).

Defines the minimal chat interface contract for provider adapters.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..models import ChatRequest, ChatResponse


@runtime_checkable
class LLMProvider(Protocol):
    """Minimal interface for Large Language Model providers.

    Implementations should map ``ChatRequest`` fields to their SDK parameters,
    normalize responses to ``ChatResponse``, and never leak SDK objects upstream.
    """

    @property
    def provider_name(self) -> str:
        """Canonical provider identifier, e.g., ``"openai"`` or ``"anthropic"``."""
        ...

    def chat(self, request: ChatRequest) -> ChatResponse:
        """Execute a single chat completion request.

        Failure handling: Do not raise for common provider errors; encode details
        in ``ChatResponse.meta.extra`` and return best-effort text/parts. Reserve
        exceptions for programmer errors.
        """
        ...
