"""OpenAI tool call protocol for streaming chunks."""

from __future__ import annotations

from typing import Optional, Protocol, runtime_checkable

from .openai_tool_function import OpenAIToolFunction


@runtime_checkable
class OpenAIToolCall(Protocol):
    """Protocol for a single tool call entry within a streaming delta."""

    function: Optional[OpenAIToolFunction]
