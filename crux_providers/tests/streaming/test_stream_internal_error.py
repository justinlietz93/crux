"""Streaming adapter INTERNAL error path test.

Purpose
-------
Validate that when the starter returns a mapping missing the required
"stream" key, the adapter classifies the failure with the `internal`
error code and emits a single terminal event carrying the code prefix.

Contract Assertions
-------------------
* Exactly one event is produced.
* Event is terminal (`finish` True).
* `error` string starts with "internal:" (normalized code prefix).
* No deltas are emitted (metrics.emitted == 0 implicit via single event).

Rationale
---------
Provides explicit coverage for INTERNAL guard paths ensuring future
regressions (e.g., relaxing coercion validation) are detected.
"""
from __future__ import annotations

from crux_providers.base.streaming import BaseStreamingAdapter
from crux_providers.base.logging import LogContext, get_logger


def _starter_invalid_mapping():  # pragma: no cover - executed via test
    """Return an invalid mapping missing the 'stream' key to trigger INTERNAL.

    The adapter's `_coerce_stream_start_result` expects a mapping with a
    'stream' key when given a mapping. Absence should raise `ProviderError`
    with code INTERNAL which is then converted to a terminal event.
    """
    return {"request_id": "req-123"}  # missing 'stream'


def _translator(_: object):  # pragma: no cover - no deltas expected
    return None


def _retry_factory(_: str):  # pragma: no cover - simple deterministic retry cfg
    from crux_providers.base.resilience.retry import RetryConfig
    return RetryConfig(max_attempts=1, delay_base=0.0)


def test_internal_error_missing_stream_key(log_capture):
    """Starter mapping missing 'stream' yields single INTERNAL terminal event."""
    print("TEST: internal error guard path (missing 'stream' key) emits INTERNAL terminal event")
    adapter = BaseStreamingAdapter(
        ctx=LogContext(provider="fake_provider", model="fake-model"),
        provider_name="fake_provider",
        model="fake-model",
        starter=_starter_invalid_mapping,
        translator=_translator,
        retry_config_factory=_retry_factory,
        logger=get_logger("providers.test.internal", json_mode=True),
        cancellation_token=None,
    )
    events = list(adapter.run())
    if len(events) != 1:
        raise AssertionError(f"expected 1 terminal event, got {len(events)}")
    evt = events[0]
    if not evt.finish:
        raise AssertionError("event must be terminal (finish True)")
    if not evt.error or not evt.error.startswith("internal:"):
        raise AssertionError(f"expected error to start with 'internal:', got {evt.error!r}")
