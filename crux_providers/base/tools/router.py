"""Simple in-process tool invocation router stub.

This module defines a minimal router that maps tool names to callables and
invokes them safely, returning a standard ``ToolResultDTO``. It is intentionally
simple and does not handle async or external processes.
"""

from __future__ import annotations

from typing import Any, Callable, Dict

from ..dto.tool_result import ToolResultDTO


ToolHandler = Callable[[dict], Any]


class SimpleToolRouter:
    """A minimal registry-based tool router.

    Contract:
        - Register handlers by name using ``register(name, handler)``.
        - Invoke via ``invoke(name, params)`` and receive ``ToolResultDTO``.
        - Handlers receive a single ``dict`` of params and return any value.
    """

    def __init__(self) -> None:
        self._handlers: Dict[str, ToolHandler] = {}

    def register(self, name: str, handler: ToolHandler) -> None:
        """Register a tool handler under ``name``.

        Args:
            name: Unique tool name.
            handler: Callable that accepts a dict of params and returns a value.
        """

        self._handlers[name] = handler

    def invoke(self, name: str, params: dict | None = None) -> ToolResultDTO:
        """Invoke a registered tool handler and wrap the result.

        Args:
            name: Tool name to invoke.
            params: Optional dict of parameters passed to the handler.

        Returns:
            ToolResultDTO: Standardized result envelope.
        """

        params = params or {}
        handler = self._handlers.get(name)
        if handler is None:
            return ToolResultDTO(name=name, ok=False, code="NOT_FOUND", error=f"tool '{name}' not registered")
        try:
            result = handler(params)
            # Normalize result to str or dict when possible
            content = result if isinstance(result, (str, dict)) else str(result)
            return ToolResultDTO(name=name, ok=True, content=content)
        except Exception as e:  # pragma: no cover (covered via unit test)
            return ToolResultDTO(name=name, ok=False, code="EXCEPTION", error=str(e))


__all__ = ["SimpleToolRouter", "ToolHandler"]
