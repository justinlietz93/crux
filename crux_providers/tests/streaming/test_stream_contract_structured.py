"""Structured streaming contract tests.

Validates that when a provider emits chunks that can be translated into structured
outputs (partials and a final function-call), the streaming helpers attach these
to `ChatStreamEvent.structured` without disrupting text delta handling or metrics.
"""

from __future__ import annotations

from typing import Iterable, Optional, Any

from crux_providers.base.streaming.streaming_adapter import BaseStreamingAdapter
from crux_providers.base.dto.structured_output import StructuredOutputDTO
from crux_providers.base.dto.function_call import FunctionCallDTO
from crux_providers.base.logging import LogContext
from crux_providers.base.resilience.retry import RetryConfig


class _FakeLogger:
    """Minimal logger stub for tests with isEnabledFor support."""

    def isEnabledFor(self, level: int) -> bool:  # noqa: N802 - keep mimic case
        return False

    def info(self, msg):  # noqa: D401 - trivial stub for logging
        """No-op info logger for tests."""
        _ = msg  # avoid unused-argument warning


def _retry_factory(_op: str) -> RetryConfig:
    """Return a minimal no-retry config suitable for unit tests.

    Keeps adapter behavior deterministic by avoiding backoff delays.
    """
    return RetryConfig(max_attempts=1, delay_base=1.0)


def test_structured_events_alongside_text():
    """Emit mixed text deltas and structured outputs and validate event fields.

    Contract:
    - First event sets time_to_first_token_ms and increments emitted.
    - Structured partials can appear with or without text.
    - Final function-call structured output is attached; terminal event remains separate.
    """

    # Simulated provider chunks
    chunks = [
        {"text": "User:", "partial": "f("},
        {"text": " Hi", "partial": "f({"},
        {"text": None, "func": {"name": "do", "args": {"x": 1}}},
    ]

    def starter() -> Iterable[dict[str, Any]]:
        return chunks

    def translator(ch: dict[str, Any]) -> Optional[str]:
        return ch.get("text")

    def structured(ch: dict[str, Any]) -> Optional[StructuredOutputDTO]:
        func = ch.get("func")
        if func is not None:
            return StructuredOutputDTO(function_call=FunctionCallDTO(name=func["name"], arguments=func["args"]))
        partial = ch.get("partial")
        if partial is not None:
            return StructuredOutputDTO(partial=partial)
        return None

    adapter = BaseStreamingAdapter(
        ctx=LogContext(provider="fake", model="fake-model", request_id=None, response_id=None),
        provider_name="fake",
        model="fake-model",
        starter=starter,
        translator=translator,
        structured_translator=structured,
        retry_config_factory=_retry_factory,
        logger=_FakeLogger(),
        on_complete=None,
        cancellation_token=None,
    )

    events = list(adapter.run())
    # We expect three mid-stream events then a terminal finalize
    assert len(events) == 4  # nosec B101 - test assertion
    assert events[-1].finish is True  # nosec B101 - terminal event

    mid = events[:-1]
    assert any(e.delta for e in mid)  # nosec B101
    assert any(e.structured and e.structured.partial for e in mid)  # nosec B101
    assert any(e.structured and e.structured.function_call for e in mid)  # nosec B101

    # Metrics sanity
    assert adapter.metrics.emitted == 3  # nosec B101
    assert adapter.metrics.time_to_first_token_ms is not None  # nosec B101
