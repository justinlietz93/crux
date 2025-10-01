"""Streaming metrics integrity tests.

Validates core invariants for metrics captured by BaseStreamingAdapter:
* emitted == (emitted_count > 0)
* time_to_first_token_ms is null iff emitted_count == 0
* time_to_first_token_ms <= total_duration_ms
* total_duration_ms > 0
* Exactly one terminal event produced
"""
from __future__ import annotations

import json
from crux_providers.base.streaming import BaseStreamingAdapter
from crux_providers.base.logging import LogContext, get_logger


class _SeqStream:
    def __init__(self, parts):
        self._parts = parts

    def __iter__(self):  # pragma: no cover - trivial
        for p in self._parts:
            yield p


def _retry_factory(_: str):  # pragma: no cover
    from crux_providers.base.resilience.retry import RetryConfig
    return RetryConfig(max_attempts=1, delay_base=0.0)


def _translator(chunk):  # pragma: no cover - passthrough
    return chunk


def _starter_deltas():
    return _SeqStream(["X", "Y", "Z"])  # 3 chunks


def _starter_empty():
    # Provide an iterator that yields nothing
    return _SeqStream([])


def _run(starter, logger_name: str, log_capture):
    ctx = LogContext(provider="fake_provider", model="fake-model")
    logger = get_logger(logger_name, json_mode=True)
    adapter = BaseStreamingAdapter(
        ctx=ctx,
        provider_name="fake_provider",
        model="fake-model",
        starter=starter,
        translator=_translator,
        retry_config_factory=_retry_factory,
        logger=logger,
    )
    events = list(adapter.run())
    return ctx, events, _extract_finalize(log_capture)


def _maybe_parse_json(line: str):
    line = line.strip()
    if not (line.startswith('{') and line.endswith('}')):
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
        if obj and obj.get('phase') == 'finalize':
            finalize = obj
    if not finalize:
        raise AssertionError("finalize log not found")
    return finalize


def _extract_terminal(events):
    terminal = [e for e in events if e.finish]
    if len(terminal) != 1:
        raise AssertionError(f"expected exactly 1 terminal event, got {len(terminal)}")
    return terminal[0]


def test_metrics_with_deltas(log_capture):
    print("TEST: metrics invariants when deltas emitted")
    _ctx, events, finalize = _run(_starter_deltas, "providers.test.metrics.deltas", log_capture)
    term = _extract_terminal(events)
    if finalize.get("emitted_count") != 3:
        raise AssertionError(f"expected emitted_count 3 got {finalize.get('emitted_count')}")
    if finalize.get("emitted") is not True:
        raise AssertionError("expected emitted True")
    ttf = finalize.get("time_to_first_token_ms")
    total = finalize.get("total_duration_ms")
    if ttf is None or ttf <= 0:
        raise AssertionError(f"invalid time_to_first_token_ms {ttf}")
    if total is None or total <= 0:
        raise AssertionError(f"invalid total_duration_ms {total}")
    if ttf > total:
        raise AssertionError(f"time_to_first_token_ms {ttf} greater than total_duration_ms {total}")
    if term.error:
        raise AssertionError(f"unexpected error {term.error}")


def test_metrics_no_deltas(log_capture):
    print("TEST: metrics invariants when no deltas emitted")
    _ctx, events, finalize = _run(_starter_empty, "providers.test.metrics.empty", log_capture)
    term = _extract_terminal(events)
    if finalize.get("emitted_count") not in (0, None):
        raise AssertionError(f"expected emitted_count 0 got {finalize.get('emitted_count')}")
    if finalize.get("emitted") not in (False, None):
        raise AssertionError(f"expected emitted False got {finalize.get('emitted')}")
    if finalize.get("time_to_first_token_ms") is not None:
        raise AssertionError("expected time_to_first_token_ms None when no deltas")
    total = finalize.get("total_duration_ms")
    if total is None or total <= 0:
        raise AssertionError(f"invalid total_duration_ms {total}")
    if term.error:
        raise AssertionError(f"unexpected error {term.error}")
