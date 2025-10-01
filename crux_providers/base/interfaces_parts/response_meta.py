"""Response meta interfaces (Protocols).

This module defines lightweight runtime-checkable Protocols that describe
the minimal attributes used by helpers when extracting token/usage metadata
from provider response objects. Using Protocols helps us avoid brittle
``getattr``/``hasattr`` patterns while keeping adapters decoupled.

No external dependencies. Pure typing constructs; safe for runtime checks.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class HasExtra(Protocol):
    """Objects exposing an ``extra`` mapping.

    Contract:
        - Attribute: ``extra`` which should be a dictionary-like mapping.

    Notes:
        The Protocol is intentionally permissive on the value type; callers
        must validate that the returned object is a ``dict``.
    """

    @property
    def extra(self) -> Any:  # pragma: no cover - structural, validated by caller
        """Provider-specific extra metadata (typically a ``dict``)."""


@runtime_checkable
class HasMetaExtra(Protocol):
    """Responses that expose a ``meta`` attribute with optional ``extra``.

    Contract:
        - Attribute: ``meta`` which may be either a ``dict`` with an
          "extra" key or an object implementing :class:`HasExtra`.

    Failure modes:
        - The presence of the attribute is checked structurally at runtime.
          Callers are responsible for validating concrete types.
    """

    @property
    def meta(self) -> Any:  # pragma: no cover - structural, validated by caller
        """Response metadata container (dict or object with ``extra``)."""
