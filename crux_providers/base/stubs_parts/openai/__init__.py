"""OpenAI-specific Protocol exports (grouped namespace).

This subpackage groups OpenAI-shaped Protocols and now contains the physical
modules. Public imports remain stable via ``stubs_parts`` and
``stubs_parts.openai``.
"""

from __future__ import annotations

from .openai_choice import OpenAIChoice
from .openai_choice_delta import OpenAIChoiceDelta
from .openai_stream_chunk import OpenAIStreamChunk
from .openai_message import OpenAIMessage
from .openai_nonstream_choice import OpenAINonStreamChoice
from .openai_chat_response import OpenAIChatResponse
from .openai_tool_function import OpenAIToolFunction
from .openai_tool_call import OpenAIToolCall
from .openai_usage import OpenAIUsage, HasOpenAIUsage

__all__ = [
    "OpenAIChoice",
    "OpenAIChoiceDelta",
    "OpenAIStreamChunk",
    "OpenAIMessage",
    "OpenAINonStreamChoice",
    "OpenAIChatResponse",
    "OpenAIToolFunction",
    "OpenAIToolCall",
    "OpenAIUsage",
    "HasOpenAIUsage",
]
