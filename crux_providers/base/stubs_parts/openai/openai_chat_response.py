"""OpenAI chat response protocol (non-stream)."""

from __future__ import annotations

from typing import Protocol, Sequence

from .openai_nonstream_choice import OpenAINonStreamChoice


class OpenAIChatResponse(Protocol):
    """Protocol for OpenAI chat completions response (non-stream)."""

    choices: Sequence[OpenAINonStreamChoice]
