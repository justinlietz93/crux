"""Streaming contract tests: scenarios A-C.

Covers:
A. Happy Path Multi-Delta
B. Empty Completion
C. Mid-Stream Error

Each test prints a descriptive line per repository guidance.
"""
from __future__ import annotations
from crux_providers.tests.streaming.helpers import ScenarioConfig, run_scenario, collect


def _cancel_never():  # pragma: no cover - trivial helper
    """Cancellation predicate that always returns False.

    Used to simulate an uninterrupted streaming session within these
    contract tests. Marked no cover because its behavior is trivial and
    exercised implicitly by every test.
    """
    return False


def _cancel_never_factory():  # compatibility if extended later
    """Factory returning the always-false cancellation predicate.

    Exists for forward compatibility should scenarios later require a
    factory signature (e.g., per-test dynamic token creation). Currently
    just returns `_cancel_never`.
    """
    return _cancel_never


def test_multi_delta_happy_path(log_capture):
    """Scenario A: multi-delta successful stream.

    Verifies:
    - Three content delta events are emitted in-order followed by exactly
      one terminal finalize event.
    - Only the last event has `finish` True and it carries no error.
    Failure modes raise explicit AssertionError with contextual counts to
    ease debugging when contract changes.
    """
    print("TEST: multi-delta happy path ensures final event and proper ordering")
    cfg = ScenarioConfig(deltas=["a", "b", "c"])
    events = collect(run_scenario(cfg, _cancel_never))
    if len(events) != 4:  # 3 deltas + 1 final
        raise AssertionError(f"expected 4 events, got {len(events)}")
    if any(e.finish for e in events[:-1]):
        raise AssertionError("non-final events must have finish False")
    last = events[-1]
    if (not last.finish) or (last.error is not None):
        raise AssertionError("final event must have finish True and no error")


def test_empty_completion(log_capture):
    """Scenario B: empty completion emits single terminal event.

    Verifies an immediate finalize event with finish=True and no error
    when the provider returns no deltas. Ensures adapter produces a
    consistent terminal event even for zero-length outputs.
    """
    print("TEST: empty completion yields single terminal event")
    cfg = ScenarioConfig(deltas=[])
    events = collect(run_scenario(cfg, _cancel_never))
    if len(events) != 1:
        raise AssertionError(f"expected single terminal event, got {len(events)}")
    term = events[0]
    if (not term.finish) or (term.error is not None):
        raise AssertionError("terminal event must have finish True and no error")


def test_mid_stream_error(log_capture):
    """Scenario C: mid-stream error after first delta.

    Configuration sets `error_after_index=0`, so the iterator raises on
    attempt to fetch the second delta. Verifies we receive exactly two
    events: one normal delta followed by a terminal event carrying the
    expected error string. Ensures adapter abort pathway surfaces the
    original error message in the finalize event.
    """
    print("TEST: mid-stream error emits error terminal after first delta")
    cfg = ScenarioConfig(deltas=["x", "y"], error_after_index=0)
    events = collect(run_scenario(cfg, _cancel_never))
    if len(events) != 2:
        raise AssertionError(f"expected 2 events (delta + error), got {len(events)}")
    if events[0].finish is True:
        raise AssertionError("first event should be a delta (finish False)")
    final = events[1]
    if (not final.finish) or final.error != "boom":
        raise AssertionError("second event must be terminal with error 'boom'")
