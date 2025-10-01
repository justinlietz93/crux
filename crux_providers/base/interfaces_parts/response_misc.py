"""
Miscellaneous response Protocols for structural typing.

This module defines tiny runtime-checkable Protocols for common attributes
observed in provider SDK exceptions and responses. Using these Protocols lets
callers avoid dynamic getattr/hasattr access patterns while keeping code
decoupled from concrete SDK types.

External dependencies: None.

Timeout & retries: Not applicable.

"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class HasCode(Protocol):
    """Structural contract for objects exposing a ``code`` attribute."""

    @property
    def code(self) -> Any:  # pragma: no cover - structural
        """Machine-readable error or status code."""


@runtime_checkable
class HasValue(Protocol):
    """Structural contract for objects exposing a ``value`` attribute."""

    @property
    def value(self) -> Any:  # pragma: no cover - structural
        """Underlying value payload (often of an enum)."""


@runtime_checkable
class HasText(Protocol):
    """Structural contract for objects exposing a textual ``text`` attribute."""

    @property
    def text(self) -> str:  # pragma: no cover - structural
        """Response text."""
