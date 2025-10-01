"""Streaming cancellation metrics tests.

Validates finalize log + terminal event semantics when cooperative
`CancellationToken` is triggered either (a) before the first delta or (b)
after at least one delta has been emitted.

Assertions:
* error_code == "cancelled" in finalize log (both scenarios)
* Pre-first-delta cancellation: emitted == False, emitted_count == 0, time_to_first_token_ms is None
* Post-first-delta cancellation: emitted == True, emitted_count > 0, time_to_first_token_ms populated and <= total_duration_ms
* Exactly one terminal event; terminal event.error starts with "cancelled:"
"""
from __future__ import annotations

import json
from typing import Iterator

from crux_providers.base.streaming import BaseStreamingAdapter
from crux_providers.base.logging import LogContext, get_logger
from crux_providers.base.cancellation import CancellationToken


class _ControlledStream:
    """Simple iterable that triggers cancellation at configurable index.

    Attributes:
        parts: Sequence of string chunks to yield.
        cancel_index: Index at which to trigger token cancellation BEFORE yielding
            that chunk (so if cancel_index == 0 no chunk is yielded). If set to
            None no automatic cancellation is performed.
        token: CancellationToken used for cooperative cancellation.
        reason: Cancellation reason to propagate.
    """

    def __init__(self, parts, token: CancellationToken, cancel_index: int | None, reason: str):
        self._parts = list(parts)
        self._token = token
        self._cancel_index = cancel_index
        self._reason = reason

    def __iter__(self) -> Iterator[str]:  # pragma: no cover - trivial iteration
        for idx, p in enumerate(self._parts):
            if self._cancel_index is not None and idx == self._cancel_index:
                # Trigger cancellation before yielding this chunk
                self._token.cancel(self._reason)
            yield p


def _retry_factory(_: str):  # pragma: no cover - fixed single attempt
    from crux_providers.base.resilience.retry import RetryConfig
    return RetryConfig(max_attempts=1, delay_base=0.0)


def _translator(chunk):  # pragma: no cover - passthrough translator
    return chunk


def _run(cancel_index, logger_name: str, log_capture):
    token = CancellationToken()
    reason = "user aborted"
    stream = _ControlledStream(["A", "B", "C"], token, cancel_index, reason)
    ctx = LogContext(provider="fake_provider", model="fake-model")
    logger = get_logger(logger_name, json_mode=True)
    adapter = BaseStreamingAdapter(
        ctx=ctx,
        provider_name="fake_provider",
        model="fake-model",
        starter=lambda: stream,
        translator=_translator,
        retry_config_factory=_retry_factory,
        logger=logger,
        cancellation_token=token,
    )
    events = list(adapter.run())
    finalize = _extract_finalize(log_capture)
    terminal = [e for e in events if e.finish]
    if len(terminal) != 1:
        raise AssertionError(f"expected exactly one terminal event, got {len(terminal)}")
    term = terminal[0]
    return finalize, term


def _maybe_parse_json(line: str):
    line = line.strip()
    if not (line.startswith("{") and line.endswith("}")):
        return None
    if '"phase"' not in line:
        return None
    try:
        return json.loads(line)
    except Exception:  # pragma: no cover - defensive
        return None


def _extract_finalize(records):
    finalize = None
    for rec in records:
        msg = getattr(rec, 'getMessage', lambda: rec)()
        obj = _maybe_parse_json(msg)
        if obj and obj.get("phase") == "finalize":
            finalize = obj
    if not finalize:
        raise AssertionError("finalize log not found")
    return finalize


def test_cancellation_pre_first_delta(log_capture):
    print("TEST: cancellation before first delta")
    finalize, term = _run(cancel_index=0, logger_name="providers.test.cancel.before", log_capture=log_capture)
    if term.error is None or not term.error.startswith("cancelled:"):
        raise AssertionError(f"expected cancelled error prefix got {term.error}")
    if finalize.get("error_code") != "cancelled":
        raise AssertionError(f"expected error_code cancelled got {finalize.get('error_code')}")
    if finalize.get("emitted") not in (False, None):
        raise AssertionError(f"expected emitted False got {finalize.get('emitted')}")
    if finalize.get("emitted_count") not in (0, None):
        raise AssertionError(f"expected emitted_count 0 got {finalize.get('emitted_count')}")
    if finalize.get("time_to_first_token_ms") is not None:
        raise AssertionError("time_to_first_token_ms should be None when no deltas emitted")
    total = finalize.get("total_duration_ms")
    if total is None or total <= 0:
        raise AssertionError(f"invalid total_duration_ms {total}")


def test_cancellation_post_first_delta(log_capture):
    print("TEST: cancellation after first delta")
    finalize, term = _run(cancel_index=1, logger_name="providers.test.cancel.after", log_capture=log_capture)
    if term.error is None or not term.error.startswith("cancelled:"):
        raise AssertionError(f"expected cancelled error prefix got {term.error}")
    if finalize.get("error_code") != "cancelled":
        raise AssertionError(f"expected error_code cancelled got {finalize.get('error_code')}")
    if finalize.get("emitted") is not True:
        raise AssertionError("expected emitted True after at least one delta")
    count = finalize.get("emitted_count")
    if count is None or count < 1:
        raise AssertionError(f"expected emitted_count >=1 got {count}")
    ttf = finalize.get("time_to_first_token_ms")
    total = finalize.get("total_duration_ms")
    if ttf is None or ttf <= 0:
        raise AssertionError(f"invalid time_to_first_token_ms {ttf}")
    if total is None or total <= 0:
        raise AssertionError(f"invalid total_duration_ms {total}")
    if ttf > total:
        raise AssertionError(f"time_to_first_token_ms {ttf} greater than total_duration_ms {total}")
