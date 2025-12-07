from __future__ import annotations

import json
from typing import Iterator

from fastapi.testclient import TestClient

from crux_providers.base.models import ChatRequest
from crux_providers.base.streaming import ChatStreamEvent
from crux_providers.service import app as app_mod


class _StreamingFake:
    """Simple streaming-capable fake adapter for /api/chat/stream tests."""

    def supports_streaming(self) -> bool:
        return True

    def stream_chat(self, request: ChatRequest) -> Iterator[ChatStreamEvent]:
        model = request.model or "fake-model"
        yield ChatStreamEvent(provider="fake", model=model, delta="Hello", finish=False)
        yield ChatStreamEvent(provider="fake", model=model, delta=None, finish=True)


class _NonStreamingFake:
    """Adapter stub without streaming capability."""

    def chat(self, request: ChatRequest) -> None:
        # Non-streaming code path is not exercised in these tests.
        return None


def _make_client() -> TestClient:
    """Construct a TestClient bound to the shared FastAPI app instance."""
    return TestClient(app_mod.get_app())


def test_post_chat_stream_emits_delta_and_final(monkeypatch) -> None:
    """/api/chat/stream yields at least one delta and a single final event."""
    fake = _StreamingFake()

    # Route all providers to our fake streaming adapter and disable env mutation.
    monkeypatch.setattr(
        "crux_providers.service.app.ProviderFactory.create",
        lambda provider: fake,
        raising=True,
    )
    monkeypatch.setattr(
        "crux_providers.service.app.set_env_for_provider",
        lambda provider, uow=None: None,
        raising=True,
    )

    client = _make_client()
    body = {
        "provider": "fake",
        "model": "fake-model",
        "messages": [{"role": "user", "content": "hi"}],
    }

    response = client.post("/api/chat/stream", json=body)
    assert response.status_code == 200

    lines = [line for line in response.text.splitlines() if line.strip()]
    assert lines, "expected at least one streamed line"

    chunks = [json.loads(line) for line in lines]

    # First event should be a delta with the expected text.
    first = chunks[0]
    assert first.get("type") == "delta"
    assert first.get("delta") == "Hello"

    # Last event should be a terminal final event with finish=True and no error.
    last = chunks[-1]
    assert last.get("type") == "final"
    assert last.get("finish") is True
    assert last.get("error") in (None, "")


def test_post_chat_stream_returns_400_when_provider_not_streaming(monkeypatch) -> None:
    """/api/chat/stream returns HTTP 400 when provider does not support streaming."""
    fake = _NonStreamingFake()

    monkeypatch.setattr(
        "crux_providers.service.app.ProviderFactory.create",
        lambda provider: fake,
        raising=True,
    )
    monkeypatch.setattr(
        "crux_providers.service.app.set_env_for_provider",
        lambda provider, uow=None: None,
        raising=True,
    )

    client = _make_client()
    body = {
        "provider": "fake",
        "model": "fake-model",
        "messages": [{"role": "user", "content": "hi"}],
    }

    response = client.post("/api/chat/stream", json=body)
    assert response.status_code == 400

    payload = response.json()
    detail = payload.get("detail")
    assert isinstance(detail, str)
    assert "does not support streaming" in detail