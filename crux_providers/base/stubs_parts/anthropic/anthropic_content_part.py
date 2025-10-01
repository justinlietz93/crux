"""Anthropic content part protocol."""

from __future__ import annotations

from typing import Optional, Protocol


class AnthropicContentPart(Protocol):
    """Protocol for a Claude message content part.

    Only ``type`` and ``text`` are accessed by our code paths.
    """

    type: str
    text: Optional[str]
