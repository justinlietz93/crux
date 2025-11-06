"""SupportsToolUse Protocol (single-class module).

Capability marker for providers that support tool/function calling.
"""

from __future__ import annotations

from typing import Iterator, List, Optional, Protocol, runtime_checkable

from ..models import ChatRequest, ChatResponse
from ..dto.tool_result import ToolResultDTO


@runtime_checkable
class SupportsToolUse(Protocol):
    """Capability marker for providers that support tool/function calling.

    Implementations should:
    - Accept tools in ChatRequest
    - Return tool calls in ChatResponse when the model requests them
    - Support tool result injection for follow-up requests
    """

    def supports_tool_use(self) -> bool:  # pragma: no cover - trivial
        """Return True if the provider supports tool/function calling."""
        return True

    def execute_with_tools(
        self,
        request: ChatRequest,
        available_tools: Optional[List[dict]] = None,
    ) -> ChatResponse:  # pragma: no cover - interface
        """Execute chat with tool calling support.
        
        Parameters
        ----------
        request:
            The chat request which may contain tool specifications.
        available_tools:
            Optional list of tool definitions available for the model to call.
            
        Returns
        -------
        ChatResponse
            Response that may contain tool_calls in metadata.
        """
        ...

    def inject_tool_results(
        self,
        request: ChatRequest,
        tool_results: List[ToolResultDTO],
    ) -> ChatRequest:  # pragma: no cover - interface
        """Inject tool execution results back into a request.
        
        Parameters
        ----------
        request:
            Original request that generated tool calls.
        tool_results:
            List of tool execution results to inject.
            
        Returns
        -------
        ChatRequest
            Modified request with tool results injected as messages.
        """
        ...
