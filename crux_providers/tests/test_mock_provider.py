"""Unit tests covering the deterministic mock provider fixtures and routing."""

from __future__ import annotations

from typing import List

import pytest

from crux_providers.base.factory import ProviderFactory
from crux_providers.mock import MockProvider
from crux_providers.base.models import ChatRequest, Message
from crux_providers.base.streaming import accumulate_events


def _build_request(prompt: str) -> ChatRequest:
    """Helper to construct a minimal ChatRequest for tests."""

    return ChatRequest(model=None, messages=[Message(role="user", content=prompt)])


@pytest.mark.usefixtures("enable_mock_providers")
class TestMockProvider:
    """Verify chat and streaming behaviour for the mock provider."""

    def test_chat_returns_fixture_payload(self) -> None:
        """Chat responses should match the fixture text and metadata annotations."""

        provider = MockProvider()
        request = _build_request("hello")
        response = provider.chat(request)
        assert response.text == "Hello from the mock provider!"
        assert response.meta.provider_name == "mock"
        assert response.meta.extra["fixture_name"] == "default"
        assert response.meta.extra["prompt_key"] == "hello"

    def test_stream_chat_emits_events_and_metadata(self) -> None:
        """Streaming should yield deltas and expose metadata on the terminal event."""

        provider = MockProvider()
        request = _build_request("hello")
        events = list(provider.stream_chat(request))
        assert events, "expected at least one streaming event"
        deltas: List[str] = [evt.delta for evt in events if evt.delta]
        assert "".join(deltas) == "Hello from the mock provider!"
        terminal = events[-1]
        assert terminal.finish is True
        assert terminal.error is None
        assert isinstance(terminal.raw, dict)
        assert terminal.raw["metadata"]["extra"]["prompt_key"] == "hello"


class TestFactoryMockRouting:
    """Ensure ProviderFactory routes providers to mock implementations when toggled."""

    def test_factory_returns_mock_for_real_provider_when_enabled(self, enable_mock_providers) -> None:
        """When the toggle is active, requesting openai should return a MockProvider."""

        adapter = ProviderFactory.create("openai")
        assert isinstance(adapter, MockProvider)
        assert adapter.provider_name == "openai"

    def test_factory_respects_explicit_mock_provider(self) -> None:
        """Explicit mock provider creation works without enabling the toggle."""

        adapter = ProviderFactory.create("mock")
        assert isinstance(adapter, MockProvider)
        assert adapter.provider_name == "mock"

    def test_accumulate_events_recovers_chat_response(self, enable_mock_providers) -> None:
        """Aggregated streaming events should produce ChatResponse text matching fixtures."""

        adapter = ProviderFactory.create("openrouter")
        request = _build_request("hello")
        events = list(adapter.stream_chat(request))
        response = accumulate_events(events)
        assert response.text == "Hello from the mock provider!"
        assert response.meta.provider_name == "openrouter"
        assert getattr(adapter, "_last_metadata").extra["mock_provider"] is True  # type: ignore[attr-defined]
