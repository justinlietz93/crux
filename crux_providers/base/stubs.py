"""Typed protocol stubs for third-party SDK response shapes.

This module preserves the public import surface while delegating the concrete
protocol definitions to one-class-per-file modules under ``stubs_parts/``.
Keeping each protocol in its own file enforces governance rules (#66/#67) and
reduces drift risk as upstream SDKs evolve.
"""

from .stubs_parts.openai import (
    OpenAIChoiceDelta,
    OpenAIChoice,
    OpenAIStreamChunk,
    OpenAIMessage,
    OpenAINonStreamChoice,
    OpenAIChatResponse,
    OpenAIUsage,
    HasOpenAIUsage,
)
from .stubs_parts.anthropic import (
    AnthropicContentPart,
    AnthropicResponse,
    AnthropicStreamTextDelta,
    AnthropicStreamChunk,
    AnthropicStreamContext,
    AnthropicUsage,
    HasAnthropicUsage,
)

__all__ = [
    "OpenAIChoiceDelta",
    "OpenAIChoice",
    "OpenAIStreamChunk",
    "OpenAIMessage",
    "OpenAINonStreamChoice",
    "OpenAIChatResponse",
    "AnthropicContentPart",
    "AnthropicResponse",
    "AnthropicStreamTextDelta",
    "AnthropicStreamChunk",
    "AnthropicStreamContext",
    "OpenAIUsage",
    "HasOpenAIUsage",
    "AnthropicUsage",
    "HasAnthropicUsage",
]
