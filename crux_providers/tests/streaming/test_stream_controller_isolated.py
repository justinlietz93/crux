"""Isolated unit tests for `StreamController` lifecycle semantics.

Covers:
- Normal completion sets `finished` and captures a terminal event.
- Cooperative cancellation before and during iteration.
- Mid-stream error propagates to `terminal_event` and `.error`.
- Empty stream (only terminal event) still marks `finished`.
- `cancel()` idempotency and safety after completion.

These tests use a minimal fake adapter that respects an injected
`_cancellation_token` attribute and yields `ChatStreamEvent` items.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator, List, Optional

from crux_providers.base.cancellation import CancellationToken
from crux_providers.base.streaming import ChatStreamEvent
from crux_providers.base.streaming.stream_controller import StreamController


@dataclass
class _FakeAdapterConfig:
    """Configuration for `_FakeAdapter` streaming behavior.

    Attributes:
        deltas: Ordered list of text chunks to emit before finalize.
        error_after_index: If set, emit an error terminal event after this delta index.
        pre_start_error: If True, emit an error terminal event before any deltas.
        respect_cancel: If True, poll `_cancellation_token` and emit cancelled terminal event.
    """

    deltas: List[str]
    error_after_index: Optional[int] = None
    pre_start_error: bool = False
    respect_cancel: bool = True


class _FakeAdapter:
    """Minimal adapter stub exposing a `run()` generator.

    The `StreamController` will inject `_cancellation_token` onto this instance
    if the attribute is missing; the stub polls it to simulate cooperative
    cancellation.
    """

    def __init__(self, cfg: _FakeAdapterConfig) -> None:
        self._cfg = cfg
        self._cancellation_token: CancellationToken | None = None

    def run(self) -> Iterator[ChatStreamEvent]:
        """Yield `ChatStreamEvent` according to configured scenario."""
        # Brief print so test output explains intent (project standard)
        # Note: Printing once per run keeps noise minimal.
        print("_FakeAdapter.run: starting stream scenario")
        if self._cfg.pre_start_error:
            yield ChatStreamEvent(provider="fake", model="m", delta=None, finish=True, error="pre_start")
            return

        for idx, delta in enumerate(self._cfg.deltas):
            if self._cfg.respect_cancel and self._cancellation_token and self._cancellation_token.cancelled:
                yield ChatStreamEvent(provider="fake", model="m", delta=None, finish=True, error="cancelled")
                return
            yield ChatStreamEvent(provider="fake", model="m", delta=delta, finish=False)
            if self._cfg.error_after_index is not None and idx == self._cfg.error_after_index:
                yield ChatStreamEvent(provider="fake", model="m", delta=None, finish=True, error="boom")
                return

        # Normal finalize
        yield ChatStreamEvent(provider="fake", model="m", delta=None, finish=True)


def test_controller_normal_completion_sets_terminal_event() -> None:
    """Proves that a normal stream marks `finished` and captures terminal event."""
    print("TEST: Normal completion should set finished=True and terminal_event present")
    adapter = _FakeAdapter(_FakeAdapterConfig(deltas=["a", "b"]))
    ctrl = StreamController(adapter)

    collected = list(ctrl)
    if not collected or collected[-1].finish is not True:
        raise AssertionError("expected final event with finish=True")
    if ctrl.finished is not True:
        raise AssertionError("controller.finished should be True after finalize")
    if ctrl.terminal_event is None:
        raise AssertionError("controller.terminal_event should be captured on finalize")
    if ctrl.error is not None:
        raise AssertionError("controller.error should be None on success finalize")


def test_controller_cancellation_before_iteration() -> None:
    """Proves that cancelling before iteration yields cancelled terminal event."""
    print("TEST: Cancellation before iteration should result in cancelled terminal event")
    adapter = _FakeAdapter(_FakeAdapterConfig(deltas=["a", "b"], respect_cancel=True))
    ctrl = StreamController(adapter)
    ctrl.cancel("user aborted")

    events = list(ctrl)
    if not events or events[-1].finish is not True:
        raise AssertionError("expected final event with finish=True on cancellation path")
    if events[-1].error != "cancelled":
        raise AssertionError("expected terminal error 'cancelled'")
    if ctrl.finished is not True:
        raise AssertionError("controller.finished should be True after cancelled finalize")
    if ctrl.error != "cancelled":
        raise AssertionError("controller.error should equal 'cancelled'")


def test_controller_mid_stream_error_propagates() -> None:
    """Proves that a mid-stream error becomes the terminal event/error on controller."""
    print("TEST: Mid-stream error should propagate to controller.error")
    adapter = _FakeAdapter(_FakeAdapterConfig(deltas=["a", "b", "c"], error_after_index=1))
    ctrl = StreamController(adapter)

    events = list(ctrl)
    if not any(e.error for e in events):
        raise AssertionError("expected at least one error event in stream")
    if ctrl.finished is not True:
        raise AssertionError("controller.finished should be True after error finalize")
    if ctrl.error != "boom":
        raise AssertionError("controller.error should equal 'boom'")
    if not ctrl.terminal_event or ctrl.terminal_event.error != "boom":
        raise AssertionError("terminal_event.error should equal 'boom'")


def test_controller_empty_stream_only_terminal() -> None:
    """Proves that an empty stream (no deltas) still sets `finished` on finalize."""
    print("TEST: Empty stream (only terminal) should still set finished=True")
    adapter = _FakeAdapter(_FakeAdapterConfig(deltas=[]))
    ctrl = StreamController(adapter)
    events = list(ctrl)
    if any(e.delta for e in events):
        raise AssertionError("no deltas expected when cfg.deltas is empty")
    if not events or events[-1].finish is not True:
        raise AssertionError("expected a terminal finalize event")
    if ctrl.finished is not True:
        raise AssertionError("controller.finished should be True after finalize")
    if ctrl.error is not None:
        raise AssertionError("controller.error should be None on success finalize")


def test_cancel_idempotent_and_safe_post_completion() -> None:
    """Proves that calling `cancel()` multiple times, including post-finish, is safe."""
    print("TEST: cancel() should be idempotent and safe after completion")
    adapter = _FakeAdapter(_FakeAdapterConfig(deltas=["x"]))
    ctrl = StreamController(adapter)
    _ = list(ctrl)  # exhaust to completion
    # Multiple cancel calls should not raise
    ctrl.cancel("reason1")
    ctrl.cancel("reason2")
    if ctrl.finished is not True:
        raise AssertionError("controller.finished should remain True post completion")
    # Ensure terminal event remains success (no error introduced by cancel)
    if ctrl.error is not None:
        raise AssertionError("controller.error should remain None after post-finish cancel")
