"""Standard tool result DTO used by tool invocation routing.

This DTO defines a provider-agnostic, minimal shape for tool results so that
provider adapters and higher layers can rely on a consistent contract.
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Union

from pydantic import BaseModel, Field


class ToolResultDTO(BaseModel):
    """Result envelope for a tool invocation.

    Attributes:
        name: The tool name that was invoked.
        ok: True when the tool executed successfully, False otherwise.
        content: Optional result payload (text or JSON-like dict).
        code: Optional error code string when ``ok`` is False.
        error: Optional human-readable error string when ``ok`` is False.
        metadata: Free-form metadata for tracing/auditing.
    """

    name: str
    ok: bool
    content: Optional[Union[str, Dict[str, Any]]] = None
    code: Optional[str] = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


__all__ = ["ToolResultDTO"]
