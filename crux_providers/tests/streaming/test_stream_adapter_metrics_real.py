"""Real adapter metrics tests using BaseStreamingAdapter with fake clock.

Validates that time_to_first_token_ms, total_duration_ms, and emitted count
are populated as the adapter iterates through translated chunks under
controlled perf_counter progression.
"""
from __future__ import annotations

from typing import Optional
import logging

from crux_providers.base.streaming import BaseStreamingAdapter
from crux_providers.base.logging import LogContext
from crux_providers.base.resilience.retry import RetryConfig
from crux_providers.base.cancellation import CancellationToken


# Helper builders

def _retry_factory(_: str) -> RetryConfig:
    # Updated to current RetryConfig signature (max_attempts, delay_base, retryable_codes, attempt_logger)
    return RetryConfig(max_attempts=1, delay_base=1.0)


def _build_adapter(chunks: list[str], clock_advance, *, cancel_token: Optional[CancellationToken] = None):
    emitted_iter = iter(chunks)
    def starter():
        return emitted_iter
    def translator(chunk):
        clock_advance(15)  # advance 15ms per chunk
        return chunk
    logger = logging.getLogger("test.adapter.metrics")
    return BaseStreamingAdapter(
        ctx=LogContext(provider="fake", model="m1"),
        provider_name="fake",
        model="m1",
        starter=starter,  # noqa: PLW0108 - direct function reference intentional
        translator=translator,
        retry_config_factory=_retry_factory,
        logger=logger,
        cancellation_token=cancel_token,
    )


def test_metrics_multi_delta(fake_clock):
    print("TEST: real adapter metrics - multi-delta success")
    adapter = _build_adapter(["a", "b", "c"], fake_clock.advance)
    events = list(adapter.run())
    if not events[-1].finish:
        raise AssertionError("terminal event expected")
    metrics = adapter.metrics
    if metrics.emitted != 3:
        raise AssertionError(f"expected emitted=3 got {metrics.emitted}")
    if metrics.time_to_first_token_ms is None or metrics.time_to_first_token_ms <= 0:
        raise AssertionError("time_to_first_token_ms should be positive")
    if metrics.total_duration_ms is None:
        raise AssertionError("total_duration_ms must be set")
    if metrics.total_duration_ms < metrics.time_to_first_token_ms:
        raise AssertionError("total_duration_ms must be >= time_to_first_token_ms")


def test_metrics_empty_stream(fake_clock):
    print("TEST: real adapter metrics - empty stream")
    adapter = _build_adapter([], fake_clock.advance)
    events = list(adapter.run())
    if not (len(events) == 1 and events[0].finish):
        raise AssertionError("expected single terminal event for empty stream")
    metrics = adapter.metrics
    if metrics.emitted != 0:
        raise AssertionError("emitted should be 0")
    if metrics.time_to_first_token_ms not in (None, 0):
        raise AssertionError("time_to_first_token_ms must be None/0 when no deltas")
    if metrics.total_duration_ms is None or metrics.total_duration_ms < 0:
        raise AssertionError("total_duration_ms must be non-negative")


def test_metrics_midstream_error(fake_clock):
    print("TEST: real adapter metrics - mid-stream error path")
    class BoomIter:
        def __iter__(self):
            yield "first"
            fake_clock.advance(20)
            raise RuntimeError("iterator boom")
    def starter():
        return BoomIter()
    def translator(chunk):
        fake_clock.advance(20)
        return chunk
    logger = logging.getLogger("test.adapter.metrics")
    adapter = BaseStreamingAdapter(
        ctx=LogContext(provider="fake", model="m1"),
        provider_name="fake",
        model="m1",
        starter=starter,  # noqa: PLW0108 - direct function reference intentional
        translator=translator,
        retry_config_factory=_retry_factory,
        logger=logger,
    )
    events = list(adapter.run())
    if not (events[-1].finish and events[-1].error):
        raise AssertionError("terminal error event expected")
    metrics = adapter.metrics
    if metrics.emitted != 1:
        raise AssertionError(f"expected emitted=1 got {metrics.emitted}")
    if metrics.time_to_first_token_ms is None or metrics.time_to_first_token_ms <= 0:
        raise AssertionError("time_to_first_token_ms should be set on first delta")
    if metrics.total_duration_ms is None or metrics.total_duration_ms < metrics.time_to_first_token_ms:
        raise AssertionError("total_duration_ms must be >= time_to_first_token_ms on error path")


def test_metrics_cancellation(fake_clock):
    print("TEST: real adapter metrics - cancellation path")
    token = CancellationToken()
    chunks = ["x", "y", "z"]
    emitted_iter = iter(chunks)
    def starter():
        return emitted_iter
    def translator(chunk):
        fake_clock.advance(10)
        if chunk == "y":
            # Cancel BEFORE emitting the second delta so only first delta counts
            token.cancel("user request")
            return None
        return chunk
    logger = logging.getLogger("test.adapter.metrics")
    adapter = BaseStreamingAdapter(
        ctx=LogContext(provider="fake", model="m1"),
        provider_name="fake",
        model="m1",
        starter=starter,  # noqa: PLW0108 - direct function reference intentional
        translator=translator,
        retry_config_factory=_retry_factory,
        logger=logger,
        cancellation_token=token,
    )
    events = list(adapter.run())
    terminal = events[-1]
    if not (terminal.finish and terminal.error and "cancelled" in terminal.error.lower()):
        raise AssertionError("expected cancelled terminal event")
    metrics = adapter.metrics
    if metrics.emitted != 1:
        raise AssertionError(f"expected emitted=1 after cancellation before second delta, got {metrics.emitted}")
    if metrics.total_duration_ms is None or metrics.time_to_first_token_ms is None:
        raise AssertionError("metrics should record timing on cancellation")
    if metrics.total_duration_ms < metrics.time_to_first_token_ms:
        raise AssertionError("total_duration_ms must be >= time_to_first_token_ms on cancellation")
