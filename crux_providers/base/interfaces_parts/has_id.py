"""
Protocol for structural typing of objects that expose an ``id`` attribute.

This interface avoids brittle dynamic attribute access (e.g., ``getattr``)
when working with heterogeneous SDK objects by enabling safe runtime
"duck-typing" checks via ``isinstance(obj, HasId)``.

External dependencies: None.

Timeout & retries: Not applicable. Contains only a type contract.

Fallback semantics: Callers should provide sensible defaults when objects do
not implement this Protocol (e.g., use a ``name`` field or stringify the
object), depending on context.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class HasId(Protocol):
    """Structural contract for objects that expose an ``id`` attribute."""

    id: str
