"""SupportsToolUse Protocol (single-class module).

Capability marker for providers that can execute tools/functions.
This interface enables providers to support tool calling patterns where
the LLM can request function execution and receive results.
"""

from __future__ import annotations

from typing import Iterator, List, Protocol, runtime_checkable

from ..models import ChatRequest, ChatResponse
from ..streaming import ChatStreamEvent
from ..dto.tool_result import ToolResultDTO


@runtime_checkable
class SupportsToolUse(Protocol):
    """Capability marker for providers that support tool/function calling.

    Implementations should:
    - Accept tool specifications in ChatRequest.tools
    - Return tool calls in response content parts
    - Support both streaming and non-streaming tool execution
    - Handle tool results in conversation context

    Tool calling flow:
    1. Client sends ChatRequest with tools array
    2. Provider returns ChatResponse with tool_call content parts
    3. Client executes tools and sends results back
    4. Provider continues conversation with tool results
    """

    def supports_tool_use(self) -> bool:  # pragma: no cover - trivial
        """Return True if the provider supports tool/function calling."""
        return True

    def chat_with_tools(
        self,
        request: ChatRequest,
        available_tools: List[ToolResultDTO] | None = None,
    ) -> ChatResponse:
        """Execute a chat request with tool calling support.

        Args:
            request: ChatRequest containing messages and tool specifications.
            available_tools: Optional list of tool results from previous calls.

        Returns:
            ChatResponse: Response may contain tool_call content parts.

        Raises:
            ProviderError: On provider-specific errors.
        """
        ...

    def stream_chat_with_tools(
        self,
        request: ChatRequest,
        available_tools: List[ToolResultDTO] | None = None,
    ) -> Iterator[ChatStreamEvent]:
        """Stream chat responses with tool calling support.

        Args:
            request: ChatRequest containing messages and tool specifications.
            available_tools: Optional list of tool results from previous calls.

        Yields:
            ChatStreamEvent: Delta events including tool call deltas,
                           followed by terminal event.

        Raises:
            ProviderError: On provider-specific errors.
        """
        ...


__all__ = ["SupportsToolUse"]
