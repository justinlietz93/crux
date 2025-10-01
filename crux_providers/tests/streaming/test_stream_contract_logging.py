"""Structured logging contract tests for BaseStreamingAdapter finalization.

Validates that finalize_stream emits normalized logging records with expected
fields for success, error, and cancellation scenarios. These tests focus on the
terminal logging event (phase=="finalize"). Mid-stream logging events are
currently emitted only via finalize helper (start phase logging is provider
specific and outside the adapter scope at this layer). If future enhancements
introduce explicit start-phase standardized logging here, extend test coverage.

Test Scenarios
--------------
1. Success with deltas: Ensure emitted=True, emitted_count>0, metrics fields set.
2. Success with no deltas (empty stream): emitted=False, emitted_count==0, first token latency None.
3. Mid-stream error: emitted may be >0 depending on chunks before failure, error_code extracted.
4. Cancellation before first delta: emitted=False, error_code=="cancelled".
5. Cancellation after some deltas: emitted=True, emitted_count reflects produced deltas, error_code=="cancelled".

Assertion Style
---------------
No bare `assert` statements (Bandit B101). Use conditional checks and raise
`AssertionError` with a descriptive message on failure.
"""
from __future__ import annotations

import json
import logging
from typing import Iterable, List, Optional

import pytest

from crux_providers.base.streaming import (
    BaseStreamingAdapter,
)
from crux_providers.base.logging import LogContext
from crux_providers.base.resilience.retry import RetryConfig
from crux_providers.base.cancellation import CancellationToken


# ----------------- Helpers -----------------

def _dummy_retry_config(_: str) -> RetryConfig:  # noqa: D401 - small factory
    return RetryConfig(max_attempts=1, delay_base=1.0)


def _collect(adapter: BaseStreamingAdapter) -> List:
    events = []
    for evt in adapter.run():
        events.append(evt)
    return events


def _last_log_payload(records):
    finalized = []
    for r in records:
        try:
            payload = json.loads(r.getMessage())
        except Exception:
            continue
        if payload.get("phase") == "finalize":
            finalized.append(payload)
    return finalized[-1] if finalized else None


@pytest.fixture()
def adapter_logger():
    logger = logging.getLogger("test.adapter")
    logger.setLevel(logging.INFO)
    return logger


# ----------------- Tests -----------------


def test_logging_success_with_deltas(fake_clock, log_capture, adapter_logger):
    # Prepare a stream that yields three chunks.
    def starter() -> Iterable[str]:
        return ["a", "b", "c"]

    def translator(chunk: str) -> Optional[str]:  # identity
        return chunk

    adapter = BaseStreamingAdapter(
        ctx=LogContext(provider="unit", model="success-deltas"),
        provider_name="unit",
        model="success-deltas",
        starter=starter,
        translator=translator,
        retry_config_factory=_dummy_retry_config,
        logger=adapter_logger,
    )
    events = _collect(adapter)
    if len(events) != 4:
        raise AssertionError(f"Expected 4 events (3 deltas + terminal), got {len(events)}")
    record = _last_log_payload(log_capture)
    if record is None:
        raise AssertionError("No finalize log record captured (logger level might be too high)")
    # Field assertions (record is a dict payload)
    if record.get("emitted") is not True:
        raise AssertionError("expected emitted True for deltas present")
    if record.get("emitted_count") != 3:
        raise AssertionError("expected emitted_count 3")
    # Accept 0.0 (no clock advance) or positive value
    ttf = record.get("time_to_first_token_ms")
    if ttf is None:
        raise AssertionError("missing time_to_first_token_ms")
    total = record.get("total_duration_ms")
    if total is None:
        raise AssertionError("missing total_duration_ms")
    if record.get("error_code") is not None:
        raise AssertionError("error_code should be None on success")


def test_logging_success_empty_stream(fake_clock, log_capture, adapter_logger):
    def starter() -> Iterable[str]:
        return []

    def translator(chunk: str) -> Optional[str]:
        return chunk

    adapter = BaseStreamingAdapter(
        ctx=LogContext(provider="unit", model="success-empty"),
        provider_name="unit",
        model="success-empty",
        starter=starter,
        translator=translator,
        retry_config_factory=_dummy_retry_config,
        logger=adapter_logger,
    )
    events = _collect(adapter)
    if len(events) != 1:
        raise AssertionError(f"Expected only terminal event, got {len(events)}")
    record = _last_log_payload(log_capture)
    if record is None:
        raise AssertionError("No finalize log record captured for empty stream (logger level?)")
    if record.get("emitted") is not False:
        raise AssertionError("expected emitted False for empty stream")
    if record.get("emitted_count") != 0:
        raise AssertionError("expected emitted_count 0 for empty stream")
    if record.get("time_to_first_token_ms") is not None:
        raise AssertionError("time_to_first_token_ms must remain None for empty stream")
    if record.get("error_code") is not None:
        raise AssertionError("error_code should be None on empty success")


def test_logging_midstream_error(fake_clock, log_capture, adapter_logger):
    class BoomIter:
        def __iter__(self):
            yield "a"
            raise RuntimeError("boom")

    def starter() -> Iterable[str]:
        return BoomIter()

    def translator(chunk: str) -> Optional[str]:
        return chunk

    adapter = BaseStreamingAdapter(
        ctx=LogContext(provider="unit", model="midstream-error"),
        provider_name="unit",
        model="midstream-error",
        starter=starter,
        translator=translator,
        retry_config_factory=_dummy_retry_config,
        logger=adapter_logger,
    )
    events = _collect(adapter)
    if len(events) != 2:
        raise AssertionError(f"Expected 2 events (1 delta + terminal error), got {len(events)}")
    record = _last_log_payload(log_capture)
    if record is None:
        raise AssertionError("No finalize log record captured for midstream error (logger level?)")
    if record.get("emitted") is not True:
        raise AssertionError("expected emitted True (some deltas before error)")
    if record.get("emitted_count") != 1:
        raise AssertionError("expected emitted_count 1 before error")
    if not record.get("error_code"):
        raise AssertionError("expected error_code extracted for midstream error")


def test_logging_cancellation_before_first_delta(fake_clock, log_capture, adapter_logger):
    token = CancellationToken()

    def starter() -> Iterable[str]:
        # Immediately cancel before iteration begins
        token.cancel("user aborted")
        # Return a plain iterable plus meta dict using the supported (stream, meta) shape
        # to avoid triggering INTERNAL guard paths in _coerce_stream_start_result which
        # would classify as internal instead of exercising cancellation logic.
        return ["a", "b"], {"request_id": "req-cancel-before"}

    def translator(chunk: str) -> Optional[str]:
        return chunk

    adapter = BaseStreamingAdapter(
        ctx=LogContext(provider="unit", model="cancel-before"),
        provider_name="unit",
        model="cancel-before",
        starter=starter,
        translator=translator,
        retry_config_factory=_dummy_retry_config,
        logger=adapter_logger,
        cancellation_token=token,
    )
    events = _collect(adapter)
    if len(events) != 1:
        raise AssertionError(f"Expected only terminal cancellation event, got {len(events)}")
    record = _last_log_payload(log_capture)
    if record is None:
        raise AssertionError("No finalize log record captured for cancellation (logger level?)")
    if record.get("emitted") is not False:
        raise AssertionError("expected emitted False when cancelled before first delta")
    if record.get("emitted_count") != 0:
        raise AssertionError("expected emitted_count 0 when cancelled before first delta")
    if record.get("error_code") != "cancelled":
        raise AssertionError("expected error_code 'cancelled' for cancellation before first delta")


def test_logging_cancellation_after_some_deltas(fake_clock, log_capture, adapter_logger):
    token = CancellationToken()

    class _Iter:
        def __iter__(self):  # noqa: D401 - small generator wrapper
            yield "a"
            token.cancel("stop now")
            yield "b"  # Will trigger cancellation check before processing

    def starter() -> Iterable[str]:
        return _Iter()

    def translator(chunk: str) -> Optional[str]:
        return chunk

    adapter = BaseStreamingAdapter(
        ctx=LogContext(provider="unit", model="cancel-after"),
        provider_name="unit",
        model="cancel-after",
        starter=starter,
        translator=translator,
        retry_config_factory=_dummy_retry_config,
        logger=adapter_logger,
        cancellation_token=token,
    )
    events = _collect(adapter)
    # Expect 2 events: delta for "a", then cancellation terminal event ("b" never emitted)
    if len(events) != 2:
        raise AssertionError(f"Expected 2 events (1 delta + terminal cancellation), got {len(events)}")
    record = _last_log_payload(log_capture)
    if record is None:
        raise AssertionError("No finalize log record captured for cancellation after some deltas (logger level?)")
    if record.get("emitted") is not True:
        raise AssertionError("expected emitted True when at least one delta preceded cancellation")
    if record.get("emitted_count") != 1:
        raise AssertionError("expected emitted_count 1 when cancellation after first delta")
    if record.get("error_code") != "cancelled":
        raise AssertionError("expected error_code 'cancelled' for cancellation after some deltas")
