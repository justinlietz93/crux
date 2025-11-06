"""IAgentRuntime Protocol (single-class module).

Interface for agent orchestration and multi-step execution.
"""

from __future__ import annotations

from typing import Any, Dict, Iterator, List, Optional, Protocol, runtime_checkable

from ..models import ChatRequest, ChatResponse
from ..dto.tool_result import ToolResultDTO


@runtime_checkable
class IAgentRuntime(Protocol):
    """Interface for agent runtime orchestration.

    Implementations handle:
    - Multi-step reasoning and execution
    - Tool invocation loops
    - Decision making and planning
    - Error recovery and retry logic
    """

    def execute_agent_loop(
        self,
        request: ChatRequest,
        max_iterations: int = 10,
        tools: Optional[List[dict]] = None,
    ) -> ChatResponse:  # pragma: no cover - interface
        """Execute an agent loop with tool calling until completion.
        
        Parameters
        ----------
        request:
            Initial chat request.
        max_iterations:
            Maximum number of iterations to prevent infinite loops.
        tools:
            Available tools for the agent to use.
            
        Returns
        -------
        ChatResponse
            Final response after agent completes task.
            
        Raises
        ------
        MaxIterationsError:
            When max iterations reached without completion.
        """
        ...

    def stream_agent_loop(
        self,
        request: ChatRequest,
        max_iterations: int = 10,
        tools: Optional[List[dict]] = None,
    ) -> Iterator[Dict[str, Any]]:  # pragma: no cover - interface
        """Stream agent execution events (thoughts, actions, results).
        
        Parameters
        ----------
        request:
            Initial chat request.
        max_iterations:
            Maximum iterations.
        tools:
            Available tools.
            
        Yields
        ------
        Dict[str, Any]
            Agent events: {'type': 'thought'|'action'|'observation'|'complete', ...}
        """
        ...

    def register_tool_executor(
        self,
        tool_name: str,
        executor: Any,
    ) -> None:  # pragma: no cover - interface
        """Register a tool executor for the agent.
        
        Parameters
        ----------
        tool_name:
            Unique tool identifier.
        executor:
            Callable that executes the tool (signature: dict -> Any).
        """
        ...

    def plan_steps(
        self,
        request: ChatRequest,
        available_tools: List[dict],
    ) -> List[Dict[str, Any]]:  # pragma: no cover - interface
        """Plan execution steps before running agent loop.
        
        Parameters
        ----------
        request:
            Initial request.
        available_tools:
            Tools available for planning.
            
        Returns
        -------
        List[Dict[str, Any]]
            Planned steps with estimated costs/resources.
        """
        ...
