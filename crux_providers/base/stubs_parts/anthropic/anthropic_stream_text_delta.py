"""Anthropic stream text delta protocol."""

from __future__ import annotations

from typing import Optional, Protocol


class AnthropicStreamTextDelta(Protocol):
    """Protocol for a text delta nested inside Anthropic streaming events.

    Attributes:
        text: Optional piece of text for this delta.
    """

    text: Optional[str]
