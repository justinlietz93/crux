"""OpenAI-style usage protocol types."""

from __future__ import annotations

from typing import Optional, Protocol


class OpenAIUsage(Protocol):
    """Protocol for OpenAI-style usage object.

    Attributes:
        prompt_tokens: Optional count of prompt tokens.
        completion_tokens: Optional count of completion tokens.
        total_tokens: Optional total tokens when provided by the SDK.
    """

    prompt_tokens: Optional[int]
    completion_tokens: Optional[int]
    total_tokens: Optional[int]


class HasOpenAIUsage(Protocol):
    """Protocol for objects exposing an ``usage`` attribute compatible with OpenAI.

    This is used for structural typing on SDK response objects without importing
    the actual SDK types at runtime.
    """

    usage: OpenAIUsage
