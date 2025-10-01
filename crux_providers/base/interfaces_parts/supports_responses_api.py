"""SupportsResponsesAPI Protocol (single-class module).

Capability marker for providers that expose a 'responses' API variant.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class SupportsResponsesAPI(Protocol):
    """Capability for providers with a separate Responses API path."""

    def uses_responses_api(self, model: str) -> bool:
        """Return True if the model should use the Responses API path."""
        ...
