"""OpenAI choice delta protocol.

This module defines the minimal structural protocol for the delta object
contained within an OpenAI streaming choice. It is intentionally narrow and
only includes the members accessed by our translation logic.

External dependencies: None (typing-only Protocol).
Fallback/Timeouts: Not applicable.
"""

from __future__ import annotations

from typing import Optional, Protocol, Sequence
from .openai_tool_call import OpenAIToolCall


class OpenAIChoiceDelta(Protocol):
    """Protocol for the delta object inside an OpenAI streaming choice.

    Attributes:
        content: Optional segment of generated text for this delta.
        tool_calls: Optional sequence of tool call entries when present.
    """

    content: Optional[str]
    tool_calls: Optional[Sequence[OpenAIToolCall]]
