"""OpenAI non-streaming message protocol."""

from __future__ import annotations

from typing import Optional, Protocol


class OpenAIMessage(Protocol):
    """Protocol for a non-stream OpenAI chat message payload."""

    content: Optional[str]
