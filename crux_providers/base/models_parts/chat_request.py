"""
ChatRequest DTO for provider-agnostic chat invocations.

Adapters map this normalized request shape to specific SDK calls. The request
contains model selection, messages, sampling parameters, optional response
formatting hints, and an escape-hatch ``extra`` for rare adapter needs.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .message import Message


@dataclass
class ChatRequest:
    """Normalized chat request sent to provider adapters.

    Attributes:
        model: Target model identifier.
        messages: Ordered list of chat `Message` instances.
        max_tokens: Maximum tokens for the completion (adapter maps the param name).
        temperature: Sampling temperature when supported by the provider.
        response_format: Optional response format hint (e.g., ``"json_object"``).
        json_schema: Optional JSON Schema when requesting structured output.
        tools: Optional provider-agnostic tool specifications.
        extra: JSON-serializable escape hatch for adapter-specific controls.

    Methods:
        to_dict: Return a JSON-serializable dictionary of the request.
    """

    model: str
    messages: List[Message]
    max_tokens: Optional[int] = None
    temperature: Optional[float] = None
    response_format: Optional[str] = None
    json_schema: Optional[Dict[str, Any]] = None
    tools: Optional[List[Dict[str, Any]]] = None
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Return a JSON-serializable dictionary representation of the request."""
        return {
            "model": self.model,
            "messages": [
                {
                    "role": m.role,
                    "content": (
                        m.content if isinstance(m.content, str)
                        else [getattr(p, "to_dict")() for p in m.content]
                    ),
                }
                for m in self.messages
            ],
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "response_format": self.response_format,
            "json_schema": self.json_schema,
            "tools": self.tools,
            "extra": self.extra,
        }


__all__ = [
    "ChatRequest",
]
