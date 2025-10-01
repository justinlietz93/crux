"""DTO for partial structured outputs.

Defines a provider-agnostic envelope for assistant structured outputs that can
carry function-call descriptors (see ``FunctionCallDTO``) or partial text. This
is a minimal scaffold to unblock adapter integration and tests.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from pydantic import BaseModel, Field

from .function_call import FunctionCallDTO


class StructuredOutputDTO(BaseModel):
    """Top-level envelope for structured outputs.

    Attributes:
        function_call: Optional function call descriptor when provided by model.
        partial: Optional partial text suitable for incremental assembly.
        metadata: Free-form context for adapters (e.g., provider-specific ids).
    """

    function_call: Optional[FunctionCallDTO] = None
    partial: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


__all__ = ["StructuredOutputDTO"]
