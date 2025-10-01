"""OpenAI streaming choice protocol.

Defines the minimal structural protocol for an OpenAI streaming choice entry.
"""

from __future__ import annotations

from typing import Protocol

from .openai_choice_delta import OpenAIChoiceDelta


class OpenAIChoice(Protocol):
    """Protocol for an OpenAI streaming choice entry."""

    delta: OpenAIChoiceDelta
