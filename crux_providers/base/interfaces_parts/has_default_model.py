"""HasDefaultModel Protocol (single-class module).

Optional convenience mixin for providers with a default model.
"""

from __future__ import annotations

from typing import Optional, Protocol, runtime_checkable


@runtime_checkable
class HasDefaultModel(Protocol):
    """Interface for providers that have a default model."""

    def default_model(self) -> Optional[str]:  # pragma: no cover - trivial
        """Return the default model identifier for the provider, if available."""
        return None
