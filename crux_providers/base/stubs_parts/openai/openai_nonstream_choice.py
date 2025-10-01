"""OpenAI non-streaming choice protocol."""

from __future__ import annotations

from typing import Protocol

from .openai_message import OpenAIMessage


class OpenAINonStreamChoice(Protocol):
    """Protocol for non-stream OpenAI choice with message."""

    message: OpenAIMessage
