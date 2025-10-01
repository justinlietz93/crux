"""OpenRouter structured streaming integration test.

Validates that the OpenRouter streaming path can surface structured outputs
(function-call style) alongside text deltas when the SSE lines include
OpenAI-compatible ``tool_calls`` fragments. Uses the shared
``BaseStreamingAdapter`` plus provider helpers.
"""

from __future__ import annotations

from typing import Iterable

from crux_providers.base.logging import LogContext
from crux_providers.base.resilience.retry import RetryConfig
from crux_providers.base.streaming.streaming_adapter import BaseStreamingAdapter
from crux_providers.openrouter.stream_helpers import (
    translate_text_from_line,
    translate_structured_from_line,
)


class _FakeLogger:
    def isEnabledFor(self, level: int) -> bool:  # noqa: N802 - mimic method
        return False

    def info(self, msg):
        _ = msg


def _retry_factory(_phase: str) -> RetryConfig:
    return RetryConfig(max_attempts=1, delay_base=1.0)


def test_openrouter_mixed_text_and_structured():
    """Emit text deltas and structured partials/name metadata from SSE lines."""

    # Simulate three SSE data lines followed by adapter terminal finalize
    sse_lines: list[bytes] = [
        b"data: {\"choices\": [{\"delta\": {\"content\": \"Hello\"}}]}",
        b"data: {\"choices\": [{\"delta\": {\"tool_calls\": [{\"function\": {\"name\": \"foo\", \"arguments\": \"{\\\"a\\\": 1\"}}}]}}]}",
        b"data: {\"choices\": [{\"delta\": {\"tool_calls\": [{\"function\": {\"name\": \"foo\"}}]}}]}",
    ]

    def starter() -> Iterable[bytes]:
        return sse_lines

    adapter = BaseStreamingAdapter(
        ctx=LogContext(provider="openrouter", model="or-test-model"),
        provider_name="openrouter",
        model="or-test-model",
        starter=starter,
        translator=translate_text_from_line,
        structured_translator=translate_structured_from_line,
        retry_config_factory=_retry_factory,
        logger=_FakeLogger(),
    )

    events = list(adapter.run())
    # Expect at least 2 mid-stream events + 1 terminal finalize event
    assert len(events) >= 3  # nosec B101
    assert events[-1].finish is True  # nosec B101

    mids = events[:-1]
    # Ensure we saw at least one text delta and at least one structured payload
    assert any(e.delta for e in mids)  # nosec B101
    assert any(e.structured for e in mids)  # nosec B101

    # Metrics sanity
    assert adapter.metrics.emitted == len(mids)  # nosec B101
    assert adapter.metrics.time_to_first_token_ms is not None  # nosec B101
