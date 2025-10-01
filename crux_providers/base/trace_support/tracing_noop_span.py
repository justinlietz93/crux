from __future__ import annotations

from typing import Any


class _NoOpSpan:
    def __init__(self, name: str) -> None:
        self.name = name

    def __enter__(self):  # pragma: no cover - trivial
        return self

    def __exit__(self, exc_type, exc, tb):  # pragma: no cover - trivial
        return False

    def set_attribute(self, key: str, value: Any) -> None:  # pragma: no cover - trivial
        pass

    def record_exception(self, exc: BaseException) -> None:  # pragma: no cover - trivial
        pass


__all__ = ["_NoOpSpan"]
