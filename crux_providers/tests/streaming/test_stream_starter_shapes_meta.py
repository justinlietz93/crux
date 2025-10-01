"""Starter shape meta propagation tests.

Validates that each supported starter return shape propagates request_id and
response_id into the adapter LogContext (and therefore into finalize logs /
terminal event metadata) without duplication or loss.

Covered Shapes
--------------
1. Direct stream iterable.
2. Tuple: (stream, meta_dict).
3. Mapping: {"stream": stream, "request_id": ..., "response_id": ...}.

Contract Assertions
-------------------
* All shapes yield identical deltas/content.
* Meta IDs (request_id, response_id) are set exactly once on context.
* Final terminal event emitted and not an error.
* time_to_first_token_ms and total_duration_ms populated when deltas exist.

Design Rationale
----------------
Ensures we do not regress meta propagation logic (e.g., forgetting to set
request_id when absent or overwriting existing values incorrectly) while
extending or refactoring starter coercion.
"""
from __future__ import annotations

from typing import List

import json
from crux_providers.base.streaming import BaseStreamingAdapter
from crux_providers.base.logging import LogContext, get_logger


class _TinyStream:
    """Deterministic tiny stream producing three fragments.

    The generator-like object here is intentionally simple so tests remain
    stable across environments; it implements the iterator protocol.
    """

    def __init__(self, parts: List[str]):
        self._parts = parts

    def __iter__(self):  # pragma: no cover - trivial
        yield from self._parts


def _translator(chunk: str):  # pragma: no cover - simple passthrough
    return chunk


def _retry_factory(_: str):  # pragma: no cover - deterministic fast retry config
    from crux_providers.base.resilience.retry import RetryConfig
    return RetryConfig(max_attempts=1, delay_base=0.0)


def _make_stream():
    return _TinyStream(["A", "B", "C"])


def _starter_direct():  # shape 1
    return _make_stream()


def _starter_tuple():  # shape 2
    return _make_stream(), {"request_id": "req-tuple", "response_id": "resp-tuple"}


def _starter_mapping():  # shape 3
    return {"stream": _make_stream(), "request_id": "req-map", "response_id": "resp-map"}


_STARTERS = [
    ("direct", _starter_direct, None, None),
    ("tuple", _starter_tuple, "req-tuple", "resp-tuple"),
    ("mapping", _starter_mapping, "req-map", "resp-map"),
]


def _collect_events(starter_name: str, starter_callable, log_capture):
    ctx = LogContext(provider="fake_provider", model="fake-model")
    logger = get_logger(f"providers.test.starter_shapes.{starter_name}", json_mode=True)
    adapter = BaseStreamingAdapter(
        ctx=ctx,
        provider_name="fake_provider",
        model="fake-model",
        starter=starter_callable,
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


def _assert_events_shape(name: str, events):
    if not events:
        raise AssertionError(f"{name}: expected at least 1 event")
    if len(events) != 4:
        raise AssertionError(f"{name}: expected 4 events (3 deltas + 1 terminal), got {len(events)}")
    return events[:-1], events[-1]


def _assert_deltas(name: str, deltas):
    collected_text = ''.join(d.delta for d in deltas if d.delta)
    if collected_text != "ABC":
        raise AssertionError(f"{name}: unexpected delta aggregation {collected_text}")


def _assert_terminal(name: str, terminal):
    if not terminal.finish:
        raise AssertionError(f"{name}: terminal event missing finish flag")
    if terminal.error:
        raise AssertionError(f"{name}: unexpected error {terminal.error}")


def _assert_meta(name: str, ctx: LogContext, expected_req, expected_resp):
    if expected_req and ctx.request_id != expected_req:
        raise AssertionError(f"{name}: expected request_id {expected_req}, got {ctx.request_id}")
    if expected_resp and ctx.response_id != expected_resp:
        raise AssertionError(f"{name}: expected response_id {expected_resp}, got {ctx.response_id}")
    if expected_req is None and ctx.request_id is not None:
        raise AssertionError(f"{name}: did not expect request_id, found {ctx.request_id}")
    if expected_resp is None and ctx.response_id is not None:
        raise AssertionError(f"{name}: did not expect response_id, found {ctx.response_id}")


def _assert_metrics(name: str, finalize_payload):
    if finalize_payload.get("emitted_count") != 3:
        raise AssertionError(f"{name}: expected emitted_count 3, got {finalize_payload.get('emitted_count')}")
    if finalize_payload.get("emitted") is not True:
        raise AssertionError(f"{name}: expected emitted True, got {finalize_payload.get('emitted')}")
    ttf = finalize_payload.get("time_to_first_token_ms")
    total = finalize_payload.get("total_duration_ms")
    if ttf is None or total is None:
        raise AssertionError(f"{name}: expected timing metrics present, got {finalize_payload}")
    if ttf <= 0 or total <= 0 or ttf > total:
        raise AssertionError(f"{name}: invalid timing relationship ttf={ttf} total={total}")


def _validate_shape(name: str, ctx: LogContext, events, finalize_payload, expected_req, expected_resp):
    deltas, terminal = _assert_events_shape(name, events)
    _assert_deltas(name, deltas)
    _assert_terminal(name, terminal)
    _assert_meta(name, ctx, expected_req, expected_resp)
    _assert_metrics(name, finalize_payload)


def test_starter_shapes_meta_propagation(log_capture):
    print("TEST: starter shape variants propagate request/response ids correctly")
    for name, starter_fn, expected_req, expected_resp in _STARTERS:
        ctx, events, finalize = _collect_events(name, starter_fn, log_capture)
        _validate_shape(name, ctx, events, finalize, expected_req, expected_resp)
