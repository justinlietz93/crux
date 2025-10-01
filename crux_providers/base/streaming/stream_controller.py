"""StreamController abstraction separated from adapter module.

Provides a lightweight cancellable iterator façade around
`BaseStreamingAdapter`. Splitting this out keeps the adapter module
focused strictly on the streaming orchestration loop. This improves
maintainability and allows controller-specific unit tests without
importing the entire adapter implementation.
"""
from __future__ import annotations

from contextlib import suppress
from typing import Iterator, Protocol, runtime_checkable

from ..cancellation import CancellationToken
from .streaming import ChatStreamEvent


class StreamController:
    """High-level cancellable iterator wrapping `BaseStreamingAdapter`.

    Responsibilities:
      * Iterate over `ChatStreamEvent` objects.
      * Expose `cancel(reason)` for cooperative cancellation.
      * Track terminal event for post-hoc inspection.
    """

    def __init__(
        self,
        adapter,  # intentionally untyped to avoid circular import of BaseStreamingAdapter
        token: CancellationToken | None = None,
    ) -> None:
        self._adapter = adapter
        self._token = token or CancellationToken()
        # Inject token into adapter if not already present (backward compat)
        try:
            # Prefer typed check via Protocol to avoid getattr patterns
            @runtime_checkable
            class _HasCancellationToken(Protocol):
                _cancellation_token: CancellationToken | None

            if isinstance(adapter, _HasCancellationToken) and adapter._cancellation_token is None:  # type: ignore[misc,attr-defined]
                # Safe direct access: runtime-checkable Protocol ensures attribute presence
                adapter._cancellation_token = self._token  # type: ignore[attr-defined]
        except Exception:
            # Last-resort best-effort: do not fail controller construction
            with suppress(Exception):
                adapter._cancellation_token = self._token  # type: ignore[attr-defined]
        self._finished = False
        self._terminal_event: ChatStreamEvent | None = None

    def __iter__(self) -> Iterator[ChatStreamEvent]:  # pragma: no cover - delegation
        for evt in self._adapter.run():
            if evt.finish:
                self._finished = True
                self._terminal_event = evt
            yield evt

    # API -----------------------------------------------------------------
    def cancel(self, reason: str | None = None) -> None:
        """Request cooperative cancellation of the underlying stream.

        Safe to invoke multiple times or after completion.
        """
        with suppress(Exception):
            self._token.cancel(reason)

    @property
    def finished(self) -> bool:  # noqa: D401 - short property
        """Whether the stream has emitted its terminal event."""
        return self._finished

    @property
    def terminal_event(self) -> ChatStreamEvent | None:  # noqa: D401 - short property
        """Return the captured terminal event if iteration has completed."""
        return self._terminal_event

    @property
    def error(self) -> str | None:  # noqa: D401 - short property
        """Return error string from terminal event (if any)."""
        return self._terminal_event.error if self._terminal_event else None


__all__ = ["StreamController"]
