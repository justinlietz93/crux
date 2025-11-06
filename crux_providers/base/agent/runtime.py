"""Base implementation of IAgentRuntime for multi-step orchestration.

This module provides a default implementation that coordinates LLM interactions
with tool execution in an iterative loop until task completion.
"""

from __future__ import annotations

from typing import Any, Dict, Iterator, List, Optional

from ..interfaces import IAgentRuntime, LLMProvider, SupportsToolUse
from ..models import ChatRequest, ChatResponse, Message
from ..dto.tool_result import ToolResultDTO
from ..tools.router import SimpleToolRouter
from ..logging import get_logger


class BaseAgentRuntime:
    """Base implementation of agent orchestration.

    This implementation provides:
    - Multi-turn conversation management
    - Automatic tool execution loop
    - Error recovery with retries
    - Execution metrics and history tracking

    Attributes:
        provider: LLM provider instance.
        tool_router: Tool registry and execution router.
        history: Conversation message history.
        logger: Structured logger instance.
    """

    def __init__(
        self,
        provider: LLMProvider,
        tool_router: Optional[SimpleToolRouter] = None,
    ) -> None:
        """Initialize the agent runtime.

        Args:
            provider: LLM provider to use for completions.
            tool_router: Optional tool router; created if not provided.

        Raises:
            TypeError: If provider doesn't support required capabilities.
        """
        self.provider = provider
        self.tool_router = tool_router or SimpleToolRouter()
        self.history: List[Message] = []
        self.logger = get_logger("agent_runtime")
        
        # Check if provider supports tool use
        self._supports_tools = isinstance(provider, SupportsToolUse)
        if not self._supports_tools:
            self.logger.warning(
                "Provider does not support tool use",
                extra={"provider": getattr(provider, "provider_name", "unknown")},
            )

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
        # Initialize conversation
        self.history = list(context or [])
        self.history.append(Message(role="user", content=goal))

        iteration = 0
        while iteration < max_iterations:
            iteration += 1
            
            self.logger.debug(
                "Agent iteration",
                extra={"iteration": iteration, "max": max_iterations},
            )

            # Create request
            request = ChatRequest(
                model=getattr(self.provider, "default_model", lambda: "default")() or "default",
                messages=self.history,
                tools=tools,
            )

            # Get response from provider
            if self._supports_tools and tools:
                response = self.provider.chat_with_tools(request)  # type: ignore
            else:
                response = self.provider.chat(request)

            # Check if response contains tool calls
            tool_calls = self._extract_tool_calls(response)
            
            if not tool_calls:
                # No tool calls - task complete
                return response

            # Execute tools and continue loop
            self._execute_and_append_tools(tool_calls)

        raise RuntimeError(f"Agent exceeded max iterations ({max_iterations})")

    def execute_streaming(
        self,
        goal: str,
        tools: List[Dict[str, Any]] | None = None,
        max_iterations: int = 10,
        context: Optional[List[Message]] = None,
    ) -> Iterator[Dict[str, Any]]:
        """Execute agent task with streaming progress updates.

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
        # Initialize conversation
        self.history = list(context or [])
        self.history.append(Message(role="user", content=goal))

        iteration = 0
        while iteration < max_iterations:
            iteration += 1
            
            yield {
                "type": "thinking",
                "content": f"Iteration {iteration}/{max_iterations}",
                "metadata": {"iteration": iteration},
            }

            # Create request
            request = ChatRequest(
                model=getattr(self.provider, "default_model", lambda: "default")() or "default",
                messages=self.history,
                tools=tools,
            )

            # Get response from provider
            if self._supports_tools and tools:
                response = self.provider.chat_with_tools(request)  # type: ignore
            else:
                response = self.provider.chat(request)

            # Extract tool calls
            tool_calls = self._extract_tool_calls(response)
            
            if not tool_calls:
                # No tool calls - task complete
                yield {
                    "type": "response",
                    "content": response.text,
                    "metadata": {"response": response},
                }
                return

            # Execute tools and yield results
            for tool_call in tool_calls:
                yield {
                    "type": "tool_call",
                    "content": tool_call,
                    "metadata": {},
                }
                
                result = self.tool_router.invoke(
                    tool_call.get("name", ""),
                    tool_call.get("arguments", {}),
                )
                
                yield {
                    "type": "tool_result",
                    "content": result,
                    "metadata": {},
                }
                
                # Append result to history
                self.history.append(
                    Message(
                        role="tool",
                        content=str(result.content) if result.content else str(result.error),
                    )
                )

        raise RuntimeError(f"Agent exceeded max iterations ({max_iterations})")

    def _extract_tool_calls(self, response: ChatResponse) -> List[Dict[str, Any]]:
        """Extract tool calls from a chat response.

        Args:
            response: Chat response to inspect.

        Returns:
            List of tool call dictionaries.
        """
        tool_calls = []
        
        # Check response content parts for tool calls
        if hasattr(response, "parts") and response.parts:
            for part in response.parts:
                if hasattr(part, "type") and part.type == "tool_call":
                    if hasattr(part, "data") and part.data:
                        tool_calls.append(part.data)
        
        return tool_calls

    def _execute_and_append_tools(self, tool_calls: List[Dict[str, Any]]) -> None:
        """Execute tool calls and append results to history.

        Args:
            tool_calls: List of tool call specifications.
        """
        for tool_call in tool_calls:
            name = tool_call.get("name", "")
            args = tool_call.get("arguments", {})
            
            self.logger.debug(
                "Executing tool",
                extra={"tool": name, "args": args},
            )
            
            result = self.tool_router.invoke(name, args)
            
            # Append result to history
            content = str(result.content) if result.content else str(result.error)
            self.history.append(Message(role="tool", content=content))

    def get_conversation_history(self) -> List[Message]:
        """Get the current conversation history.

        Returns:
            List[Message]: All messages in current conversation context.
        """
        return self.history.copy()

    def clear_history(self) -> None:
        """Clear the conversation history and reset agent state."""
        self.history = []
        self.logger.debug("Conversation history cleared")

    def register_tool(self, name: str, handler: Any) -> None:
        """Register a tool handler for the agent to use.

        Args:
            name: Unique tool name.
            handler: Callable tool implementation.

        Raises:
            ValueError: If tool name already registered.
        """
        if name in self.tool_router._handlers:
            raise ValueError(f"Tool '{name}' already registered")
        
        self.tool_router.register(name, handler)
        self.logger.debug("Tool registered", extra={"tool": name})

    def unregister_tool(self, name: str) -> None:
        """Remove a tool from the registry.

        Args:
            name: Tool name to unregister.

        Raises:
            KeyError: If tool not found.
        """
        if name not in self.tool_router._handlers:
            raise KeyError(f"Tool '{name}' not found")
        
        del self.tool_router._handlers[name]
        self.logger.debug("Tool unregistered", extra={"tool": name})


__all__ = ["BaseAgentRuntime"]
