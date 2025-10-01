"""Cooperative cancellation token implementation.

Exposes the ``CancellationToken`` class used across providers to enable early
termination of long-running or streaming operations via cooperative polling.
"""

from __future__ import annotations

from threading import Lock
from typing import List

from .state import State
from .cancelled_error import CancelledError


class CancellationToken:
    """A cooperative cancellation token with optional cascading semantics.

    Thread-safe for basic ``cancel`` + ``raise_if_cancelled`` usage. Child tokens
    inherit cancellation when the parent is cancelled.
    """

    def __init__(self, *, parent: "CancellationToken | None" = None) -> None:
        self._state = State()
        self._lock = Lock()
        self._children: List[CancellationToken] = []
        if parent is not None:
            parent.link_child(self)

    @property
    def cancelled(self) -> bool:  # noqa: D401 - short form
        """Whether cancellation has been requested."""
        return self._state.cancelled

    @property
    def reason(self) -> str | None:  # noqa: D401 - short form
        """Reason string supplied at cancel time (if any)."""
        return self._state.reason

    def cancel(self, reason: str | None = None) -> None:
        """Request cooperative cancellation and cascade to children."""
        with self._lock:
            if self._state.cancelled:
                return
            self._state.cancelled = True
            self._state.reason = reason
            children = list(self._children)
        for child in children:
            child.cancel(reason)

    def link_child(self, token: "CancellationToken") -> "CancellationToken":
        """Link a child token so parent cancellation cascades (returns child)."""
        with self._lock:
            self._children.append(token)
            should_cancel = self._state.cancelled
            reason = self._state.reason
        if should_cancel:
            token.cancel(reason)
        return token

    def raise_if_cancelled(self) -> None:
        """Raise ``CancelledError`` if token is cancelled."""
        if self._state.cancelled:
            raise CancelledError(self._state.reason or "operation cancelled")

    def child(self) -> "CancellationToken":
        """Create and link a child token (shortcut)."""
        return CancellationToken(parent=self)

    def __repr__(self) -> str:  # pragma: no cover - introspection aid
        return (
            f"CancellationToken(cancelled={self._state.cancelled}, "
            f"reason={self._state.reason!r}, children={len(self._children)})"
        )


__all__ = ["CancellationToken"]
