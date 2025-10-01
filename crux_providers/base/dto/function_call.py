"""DTO describing a function-style structured output.

This DTO captures the minimal information needed to represent a function call
that a model wants to execute: the function name and a JSON-like arguments
mapping.
"""

from __future__ import annotations

from typing import Any, Dict

from pydantic import BaseModel, Field


class FunctionCallDTO(BaseModel):
    """Represents a function-style structured output from a model.

    Parameters
    ----------
    name:
        The function/tool name suggested by the model.
    arguments:
        JSON-like arguments payload. Defaults to an empty mapping.

    Notes
    -----
    - This DTO is intentionally small and provider-agnostic.
    - Side effects: None. Pure data container.
    - Exceptions: Validation errors can be raised by Pydantic if types mismatch.
    """

    name: str
    arguments: Dict[str, Any] = Field(default_factory=dict)


__all__ = ["FunctionCallDTO"]
