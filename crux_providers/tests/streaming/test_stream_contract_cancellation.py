"""Streaming contract tests: scenarios D-F.

D. Pre-start error
E. Cancellation before first delta
F. Cancellation after some deltas

Each test prints a descriptive line for clarity per repository guidance.
"""
from __future__ import annotations

from crux_providers.tests.streaming.helpers import ScenarioConfig, run_scenario, collect


def test_pre_start_error():
    print("TEST: pre-start error produces single terminal error event and no deltas")
    cfg = ScenarioConfig(deltas=["ignored"], pre_start_error=True)
    events = collect(run_scenario(cfg, lambda: False))
    if len(events) != 1:
        raise AssertionError(f"expected 1 event, got {len(events)}")
    ev = events[0]
    if not ev.finish or ev.error != "pre_start":
        raise AssertionError("terminal event must carry pre_start error")


def test_cancellation_before_first_delta():
    print("TEST: cancellation before first delta yields single cancelled terminal event")
    # cancel() returns True on first invocation
    def cancel():
        return True
    cfg = ScenarioConfig(deltas=["a", "b"])
    events = collect(run_scenario(cfg, cancel))
    if len(events) != 1:
        raise AssertionError(f"expected 1 event (cancel terminal), got {len(events)}")
    ev = events[0]
    if not ev.finish or ev.error != "cancelled":
        raise AssertionError("expected cancelled terminal event before any delta")


def test_cancellation_after_some_deltas():
    print("TEST: cancellation after first delta yields delta + cancelled terminal event")
    calls = {"n": 0}
    def cancel():
        calls["n"] += 1
        # Return True starting with second loop iteration (after 1 delta emitted)
        return calls["n"] >= 2
    cfg = ScenarioConfig(deltas=["chunk1", "chunk2", "chunk3"])
    events = collect(run_scenario(cfg, cancel))
    if len(events) != 2:
        raise AssertionError(f"expected 2 events (delta + cancelled), got {len(events)}")
    first, second = events
    if first.finish:
        raise AssertionError("first event should be delta (finish False)")
    if (not second.finish) or second.error != "cancelled":
        raise AssertionError("second event must be cancelled terminal")
