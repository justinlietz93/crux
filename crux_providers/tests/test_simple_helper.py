from __future__ import annotations

import pytest

from crux_providers.base.interfaces import HasDefaultModel, LLMProvider
from crux_providers.base.models import ChatRequest, ChatResponse, ContentPart, Message, ProviderMetadata
from crux_providers.base.utils.simple import simple


class _ProviderWithDefault(LLMProvider, HasDefaultModel):  # type: ignore[misc]
    """Fake provider implementing a default model and chat for testing."""

    def __init__(self):
        self._calls = []

    @property
    def provider_name(self) -> str:  # pragma: no cover - trivial
        """Return a stable provider name for tests."""
        return "fake"

    def default_model(self) -> str:  # type: ignore[override]
        """Return a default model identifier for tests."""
        return "fake-default"

    def chat(self, request: ChatRequest) -> ChatResponse:
        """Record the request and return a simple response."""
        self._calls.append(request)
        return ChatResponse(
            text="ok",
            parts=[ContentPart(type="text", text="ok")],
            raw=None,
            meta=ProviderMetadata(provider_name="fake", model_name=request.model),
        )


class _ProviderNoDefault(LLMProvider):  # type: ignore[misc]
    """Fake provider lacking a default model for negative-path testing."""

    @property
    def provider_name(self) -> str:  # pragma: no cover - trivial
        """Return a stable provider name for tests."""
        return "nodef"

    def chat(self, request: ChatRequest) -> ChatResponse:
        """Return a simple response using the provided model."""
        return ChatResponse(
            text="ok",
            parts=[ContentPart(type="text", text="ok")],
            raw=None,
            meta=ProviderMetadata(provider_name="nodef", model_name=request.model),
        )


def test_simple_uses_provider_default_model():
    """It should use the provider's default model when none is specified."""
    p = _ProviderWithDefault()
    resp = simple(p, "hello")
    if resp.text != "ok":  # nosec - explicit check for Bandit
        raise AssertionError("unexpected response text")
    # Ensure default model was used and message is set
    if p._calls[0].model != "fake-default":  # nosec - explicit check
        raise AssertionError("default model not used")
    if p._calls[0].messages != [Message(role="user", content="hello")]:  # nosec - explicit check
        raise AssertionError("user message mismatch")


def test_simple_requires_model_if_no_default():
    """It should raise ValueError if the provider has no default model and none is provided."""
    p = _ProviderNoDefault()
    with pytest.raises(ValueError):
        simple(p, "hello")


def test_simple_allows_explicit_model_override():
    """It should allow explicitly overriding the default model via argument."""
    p = _ProviderWithDefault()
    resp = simple(p, "hello", model="override")
    if resp.meta.model_name != "override":  # nosec - explicit check
        raise AssertionError("explicit model override not honored")
