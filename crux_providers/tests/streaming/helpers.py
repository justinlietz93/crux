"""Helper classes & assertions for streaming contract tests.

Defines a FakeStreamingAdapter harness that mimics BaseStreamingAdapter behavior
by yielding artificial ChatStreamEvent objects following configured scenarios.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import List, Optional, Iterator, Callable

from ...base.streaming import ChatStreamEvent

@dataclass
class ScenarioConfig:
    deltas: List[str]
    error_after_index: Optional[int] = None  # emit error after this delta index
    pre_start_error: bool = False
    cancel_after_index: Optional[int] = None  # simulate cancellation after index


def run_scenario(cfg: ScenarioConfig, cancel: Callable[[], bool]) -> Iterator[ChatStreamEvent]:
    """Generate a deterministic stream according to scenario config.

    This is a lightweight harness not invoking real provider logic; unit tests
    focus on lifecycle semantics rather than network I/O.
    """
    if cfg.pre_start_error:
        yield ChatStreamEvent(provider="fake", model="test", delta=None, finish=True, error="pre_start")
        return
    for idx, chunk in enumerate(cfg.deltas):
        if cancel():
            yield ChatStreamEvent(provider="fake", model="test", delta=None, finish=True, error="cancelled")
            return
        yield ChatStreamEvent(provider="fake", model="test", delta=chunk, finish=False)
        if cfg.error_after_index is not None and idx == cfg.error_after_index:
            yield ChatStreamEvent(provider="fake", model="test", delta=None, finish=True, error="boom")
            return
        if cfg.cancel_after_index is not None and idx == cfg.cancel_after_index:
            yield ChatStreamEvent(provider="fake", model="test", delta=None, finish=True, error="cancelled")
            return
    # Normal finalize
    yield ChatStreamEvent(provider="fake", model="test", delta=None, finish=True)


def collect(events: Iterator[ChatStreamEvent]):
    return list(events)
