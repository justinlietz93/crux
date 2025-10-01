"""SupportsStreaming Protocol (single-class module).

Capability marker for providers that can stream incremental deltas.
"""

from __future__ import annotations

from typing import Iterator, Protocol, runtime_checkable

from ..models import ChatRequest
from ..streaming import ChatStreamEvent


@runtime_checkable
class SupportsStreaming(Protocol):
    """Capability marker for providers that can stream incremental deltas.

    Implementations should yield zero or more delta events (``finish=False``)
    then exactly one terminal event (``finish=True``). On error, emit a single
    terminal event with ``error`` populated.
    """

    def supports_streaming(self) -> bool:  # pragma: no cover - trivial
        """Return True if the provider supports streaming chat responses."""
        return True

    def stream_chat(self, request: ChatRequest) -> Iterator[ChatStreamEvent]:  # pragma: no cover - interface
        """Stream chat responses as incremental delta events."""
        ...
