"""Internal state holder for cancellation tokens.

Dataclass used by ``CancellationToken`` to track cancellation status and
optional reason. Module scoped to keep the token class focused and to comply
with one-class-per-file policy for public types.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class State:
    """Internal state for cooperative cancellation tokens."""

    cancelled: bool = False
    reason: Optional[str] = None


__all__ = ["State"]
