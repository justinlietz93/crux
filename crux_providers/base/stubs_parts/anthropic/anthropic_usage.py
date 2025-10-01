"""Anthropic-style usage protocol types."""

from __future__ import annotations

from typing import Optional, Protocol


class AnthropicUsage(Protocol):
    """Protocol for Anthropic-style usage object.

    Attributes:
        input_tokens: Optional count of input (prompt) tokens.
        output_tokens: Optional count of generated (completion) tokens.
        total_tokens: Optional total tokens when provided by the SDK.
    """

    input_tokens: Optional[int]
    output_tokens: Optional[int]
    total_tokens: Optional[int]


class HasAnthropicUsage(Protocol):
    """Protocol for objects exposing an ``usage`` attribute compatible with Anthropic."""

    usage: AnthropicUsage
