"""
Protocols for structural typing of model-like objects exposing common fields.

This module defines lightweight Protocols used to avoid brittle getattr/hasattr
patterns when interacting with third-party SDK objects. By leveraging
``@runtime_checkable`` Protocols, we can safely use ``isinstance`` checks
against objects that structurally conform to the expected attributes without
import-time coupling to those SDK types.

External dependencies: None.

Timeout & retries: Not applicable. This module contains only type contracts.

Fallback semantics: When an object does not satisfy a Protocol, callers should
provide reasonable fallbacks (e.g., stringifying the object or defaulting to
``None`` for optional attributes).
"""

from __future__ import annotations

from typing import Optional, Protocol, runtime_checkable


@runtime_checkable
class HasName(Protocol):
    """Structural contract for objects that expose a ``name`` attribute.

    This Protocol enables safe ``isinstance(obj, HasName)`` checks to access
    ``obj.name`` without resorting to dynamic attribute access.
    """

    name: str


@runtime_checkable
class HasTokenLimits(Protocol):
    """Structural contract for objects that expose token limit attributes.

    Attributes
    ----------
    input_token_limit: Optional[int]
        Maximum number of input tokens accepted by the model.
    output_token_limit: Optional[int]
        Maximum number of output tokens produced by the model.
    """

    input_token_limit: Optional[int]
    output_token_limit: Optional[int]


@runtime_checkable
class HasNameAndLimits(HasName, HasTokenLimits, Protocol):
    """Composite structural contract for objects with ``name`` and limits.

    This is a convenience Protocol combining :class:`HasName` and
    :class:`HasTokenLimits` for concise checks.
    """

    ...
