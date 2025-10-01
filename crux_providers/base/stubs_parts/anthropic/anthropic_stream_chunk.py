"""Anthropic streaming chunk protocol."""

from __future__ import annotations

from typing import Optional, Protocol

from .anthropic_stream_text_delta import AnthropicStreamTextDelta


class AnthropicStreamChunk(Protocol):
    """Protocol for Anthropic streaming chunks emitted during streaming.

    The SDK may produce either direct text on the event (``.text``) or a
    nested ``.delta`` object with a ``text`` attribute. This protocol models
    only the members our translators read.

    Attributes:
        text: Optional direct text segment.
        delta: Optional nested object exposing a ``text`` attribute.
    """

    text: Optional[str]
    delta: Optional[AnthropicStreamTextDelta]
