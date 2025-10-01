from __future__ import annotations

from dataclasses import dataclass

from .tracing_noop_span import _NoOpSpan


@dataclass
class _NoOpTracer:
    name: str = "providers"

    def start_span(self, name: str):  # pragma: no cover - trivial
        return _NoOpSpan(name)


__all__ = ["_NoOpTracer"]
