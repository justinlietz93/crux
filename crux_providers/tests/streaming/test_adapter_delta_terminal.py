"""Streaming adapter minimal contract tests (delta + terminal).

Ensures that the `BaseStreamingAdapter` emits at least one non-empty delta
event and exactly one terminal event with no error in the normal path.
"""
from __future__ import annotations

from typing import Iterable, List, Optional

from crux_providers.base.streaming import BaseStreamingAdapter
from crux_providers.base.logging import LogContext


class DummyLogger:
    """Minimal logger capturing events for inspection.

    We only need an object exposing `.info` / `.warning` / `.error` so the adapter's
    `log_event` helper can invoke it. Messages are stored for optional future
    assertions without polluting stdout in test runs.
    """

    def __init__(self) -> None:
        self.records: List[tuple[str, str]] = []

    def info(self, msg: str, *_, **__):  # type: ignore[override]
        self.records.append(("info", msg))

    def warning(self, msg: str, *_, **__):  # type: ignore[override]
        self.records.append(("warning", msg))

    def error(self, msg: str, *_, **__):  # type: ignore[override]
        self.records.append(("error", msg))


def _dummy_starter() -> Iterable[str]:
    """Return an iterable of artificial 'chunks'."""
    return ["Hel", "lo", " world"]


def _dummy_translator(chunk: str) -> Optional[str]:
    """Translator returning the chunk unchanged (simulates provider delta)."""
    return chunk


def _retry_cfg_factory(_phase: str):  # pragma: no cover - simple stub
    from crux_providers.base.resilience.retry import RetryConfig

    return RetryConfig(max_attempts=1)


def test_streaming_emits_non_empty_delta():
    """Adapter should emit >0 delta events and one terminal event for normal flow.

    Validates that at least one event has a non-empty ``delta`` attribute and that
    the final event sets ``finish=True`` with no error.
    """
    logger = DummyLogger()
    adapter = BaseStreamingAdapter(
        ctx=LogContext(provider="dummy", model="m1"),
        provider_name="dummy",
        model="m1",
        starter=_dummy_starter,
        translator=_dummy_translator,
        retry_config_factory=_retry_cfg_factory,
        logger=logger,
    )
    events = list(adapter.run())

    # Partition events
    deltas = [e for e in events if e.delta]
    terminals = [e for e in events if e.finish]

    if not deltas:
        raise AssertionError("Expected at least one non-empty delta event")
    if len(terminals) != 1:
        raise AssertionError("Expected exactly one terminal event")
    term = terminals[0]
    if term.error is not None:
        raise AssertionError(f"Unexpected terminal error: {term.error}")
    # Basic metric sanity (emitted count matches)
    if adapter.metrics.emitted != len(deltas):
        raise AssertionError("Emitted metric mismatch")
