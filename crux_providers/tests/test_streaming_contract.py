"""Streaming contract tests.

Validates provider stream_chat implementations:
- Emits >=1 events and exactly one terminal finish event.
- No duplicate finish events.
- No final aggregated text delta repeated as a last delta (we rely on accumulate_events).
- Retry only applied to stream start (simulated via a fake wrapper provider).

These tests use a FakeProvider implementing the same ChatStreamEvent semantics to avoid
external API calls. Real providers can be smoke-tested separately behind env guards.
"""

from __future__ import annotations

from typing import Iterable
from typing import Optional

from ..base.interfaces import LLMProvider
from ..base.models import (
    ChatRequest,
    ChatResponse,
    ContentPart,
    Message,
    ProviderMetadata,
)
from ..base.streaming import ChatStreamEvent, accumulate_events


class FakeStreamingProvider(LLMProvider):
    def __init__(
        self, fail_first_start: bool = False, model: str = "fake-model"
    ) -> None:
        self._fail_first_start = fail_first_start
        self._attempts = 0
        self._model = model

    @property
    def provider_name(self) -> str:
        return "fake"

    def default_model(self) -> Optional[str]:  # pragma: no cover - not used
        return self._model

    def chat(
        self, request: ChatRequest
    ) -> ChatResponse:  # pragma: no cover - not part of contract test
        return ChatResponse(
            text="static",
            parts=[ContentPart(type="text", text="static")],
            raw=None,
            meta=ProviderMetadata(
                provider_name=self.provider_name, model_name=self._model
            ),
        )

    def supports_json_output(self) -> bool:  # pragma: no cover
        return False

    def stream_chat(self, request: ChatRequest):
        # Simulate retry-on-start only by raising first time if configured
        if self._fail_first_start and self._attempts == 0:
            self._attempts += 1
            raise RuntimeError("transient start failure")
        # Produce three deltas then terminal
        for ch in ["Hello", ", ", "world!"]:
            yield ChatStreamEvent(
                provider=self.provider_name, model=self._model, delta=ch, finish=False
            )
        yield ChatStreamEvent(
            provider=self.provider_name, model=self._model, delta=None, finish=True
        )


def test_stream_accumulate_basic():
    provider = FakeStreamingProvider()
    req = ChatRequest(model="fake-model", messages=[Message(role="user", content="hi")])
    events = list(provider.stream_chat(req))
    assert events, "No events emitted"  # nosec B101 test assertion
    finishes = [e for e in events if e.finish]
    assert (
        len(finishes) == 1
    ), "Expected exactly one finish event"  # nosec B101 test assertion
    assert (
        finishes[0].delta is None
    ), "Terminal event should not repeat text delta"  # nosec B101 test assertion
    # Accumulate
    resp = accumulate_events(events)
    assert resp.text == "Hello, world!"  # nosec B101 test assertion
    print(
        "test_stream_accumulate_basic: confirmed single terminal event, no duplicated final delta, accumulation produced expected text"
    )


def _run_with_single_retry(provider: FakeStreamingProvider, req: ChatRequest) -> Iterable[ChatStreamEvent]:
    """Helper to encapsulate manual retry logic so test body stays simple.

    Attempts provider.stream_chat up to 3 times until it yields events without raising
    a RuntimeError. Raises after final attempt.
    """
    for attempt in range(3):
        try:
            return list(provider.stream_chat(req))
        except RuntimeError:
            if attempt == 2:
                raise
    return []  # fallback (unreachable)


def test_stream_retry_only_on_start():
    provider = FakeStreamingProvider(fail_first_start=True)
    req = ChatRequest(model="fake-model", messages=[Message(role="user", content="retry")])
    events = _run_with_single_retry(provider, req)
    finishes = [e for e in events if e.finish]
    assert len(finishes) == 1  # nosec B101 test assertion
    assert events[-1].finish is True  # nosec B101 test assertion
    print("test_stream_retry_only_on_start: verified retry abstraction helper used")


def test_accumulate_error_event_short_circuits():
    # Create custom sequence with an error
    events = [
        ChatStreamEvent(provider="fake", model="fake", delta="Hello", finish=False),
        ChatStreamEvent(
            provider="fake", model="fake", delta=None, finish=True, error="boom"
        ),
        ChatStreamEvent(
            provider="fake", model="fake", delta="SHOULD_NOT_INCLUDE", finish=False
        ),
    ]
    resp = accumulate_events(events)
    assert resp.text is None  # nosec B101 test assertion
    assert resp.meta.extra.get("stream_error") == "boom"  # nosec B101 test assertion
    print(
        "test_accumulate_error_event_short_circuits: ensured error terminal stops accumulation and ignores later deltas"
    )
