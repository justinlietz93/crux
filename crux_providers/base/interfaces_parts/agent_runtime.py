"""IAgentRuntime Protocol (single-class module).

Interface for multi-step agent orchestration, enabling tool-augmented
conversations with planning, execution, and reflection capabilities.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

from ..models import ChatRequest, ChatResponse, Message
from ..dto.tool_result import ToolResultDTO


@runtime_checkable
class IAgentRuntime(Protocol):
    """Interface for agent orchestration and multi-step execution.

    Implementations should:
    - Orchestrate multi-turn conversations with tool execution
    - Maintain conversation history and context
    - Execute tools requested by the LLM
    - Handle error recovery and retries
    - Track execution metrics and state

    Agent execution flow:
    1. Client provides goal/task and available tools
    2. Runtime engages LLM to plan and execute steps
    3. Runtime executes tool calls automatically
    4. Runtime feeds results back to LLM for next steps
    5. Runtime returns final result when complete
    """

    def execute(
        self,
        goal: str,
        tools: List[Dict[str, Any]] | None = None,
        max_iterations: int = 10,
        context: Optional[List[Message]] = None,
    ) -> ChatResponse:
        """Execute an agent task with optional tool access.

        Args:
            goal: The task or question for the agent to accomplish.
            tools: Optional list of tool specifications available to agent.
            max_iterations: Maximum number of agent reasoning steps.
            context: Optional prior conversation context.

        Returns:
            ChatResponse: Final response after completing the task.

        Raises:
            RuntimeError: If agent exceeds max iterations without completion.
            ProviderError: On provider-specific errors.
        """
        ...

    def execute_streaming(
        self,
        goal: str,
        tools: List[Dict[str, Any]] | None = None,
        max_iterations: int = 10,
        context: Optional[List[Message]] = None,
    ):
        """Execute agent task with streaming progress updates.

        Yields intermediate steps, tool calls, and final result.

        Args:
            goal: The task or question for the agent to accomplish.
            tools: Optional list of tool specifications available to agent.
            max_iterations: Maximum number of agent reasoning steps.
            context: Optional prior conversation context.

        Yields:
            Dict[str, Any]: Progress events including:
                - type: "thinking" | "tool_call" | "tool_result" | "response"
                - content: Event-specific content
                - metadata: Additional context

        Raises:
            RuntimeError: If agent exceeds max iterations without completion.
            ProviderError: On provider-specific errors.
        """
        ...

    def get_conversation_history(self) -> List[Message]:
        """Get the current conversation history.

        Returns:
            List[Message]: All messages in current conversation context.
        """
        ...

    def clear_history(self) -> None:
        """Clear the conversation history and reset agent state."""
        ...

    def register_tool(self, name: str, handler: Any) -> None:
        """Register a tool handler for the agent to use.

        Args:
            name: Unique tool name.
            handler: Callable tool implementation.

        Raises:
            ValueError: If tool name already registered.
        """
        ...

    def unregister_tool(self, name: str) -> None:
        """Remove a tool from the registry.

        Args:
            name: Tool name to unregister.

        Raises:
            KeyError: If tool not found.
        """
        ...


__all__ = ["IAgentRuntime"]
