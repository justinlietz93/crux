"""Anthropic message response protocol."""

from __future__ import annotations

from typing import Protocol, Sequence

from .anthropic_content_part import AnthropicContentPart


class AnthropicResponse(Protocol):
    """Protocol for an Anthropic message response object.

    Attributes:
        content: A list of content parts returned by the SDK.
    """

    content: Sequence[AnthropicContentPart]
