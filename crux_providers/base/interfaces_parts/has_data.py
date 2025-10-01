"""Interfaces for objects exposing a ``data`` container.

Defines a minimal Protocol for SDK responses that provide a ``data`` attribute.
This allows helpers to avoid brittle ``getattr`` patterns while remaining fully
decoupled from concrete SDK classes.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class HasData(Protocol):
    """Structural interface for objects with a ``data`` attribute.

    Consumers should still validate the type of the returned ``data`` value.
    """

    @property
    def data(self) -> Any:  # pragma: no cover - structural, checked by callers
        """Container of items returned by an SDK list operation."""
