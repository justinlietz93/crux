"""OpenAI chat streaming chunk protocol."""

from __future__ import annotations

from typing import Protocol, Sequence

from .openai_choice import OpenAIChoice


class OpenAIStreamChunk(Protocol):
    """Protocol representing an OpenAI chat streaming chunk payload.

    Attributes:
        choices: A non-empty sequence of choices; only the first is used.
    """

    choices: Sequence[OpenAIChoice]
