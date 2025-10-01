"""Unit tests for the Gemini provider adapter.

These tests stub the google-generativeai SDK to avoid network calls and
exercise key behaviors: default properties, missing-SDK handling, chat
success path, and streaming translation via BaseStreamingAdapter.

All tests are offline and rely on monkeypatching the module-level
``genai`` in `crux_providers.gemini.client`.
"""
from __future__ import annotations

from typing import Any, List

import types
import pytest

from crux_providers.base.models_parts.message import Message
from crux_providers.base.models_parts.chat_request import ChatRequest
from crux_providers.gemini.client import GeminiProvider


class _FakeChunk:
    """Simple fake stream chunk carrying text for translation."""

    def __init__(self, text: str) -> None:
        self.text = text


class _FakeResponse:
    """Simple fake non-stream response with a `.text` attribute."""

    def __init__(self, text: str) -> None:
        self.text = text


class _FakeGenerativeModel:
    """Fake GenerativeModel implementing only what the adapter uses."""

    def __init__(self, *, model_name: str, generation_config: Any | None = None) -> None:
        self._model_name = model_name
        self._cfg = generation_config or {}

    def generate_content(self, content: str, stream: bool = False):
        if stream:
            # Yield two small chunks as the stream body
            return [_FakeChunk("alpha"), _FakeChunk("beta")]
        return _FakeResponse("ok")


def _install_fake_genai(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace `gemini.client.genai` with a minimal fake SDK module.

    The fake exposes `configure` and `GenerativeModel` attributes as used by the adapter.
    """
    fake = types.SimpleNamespace()
    fake.configure = lambda **_: None  # no-op
    # Use direct function to avoid unnecessary-lambda warning
    def _gm(**kw):
        return _FakeGenerativeModel(**kw)
    fake.GenerativeModel = _gm  # type: ignore[assignment]
    monkeypatch.setattr("crux_providers.gemini.client.genai", fake, raising=False)


def _stub_record_observation(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make capability recording a no-op to avoid side effects."""
    monkeypatch.setattr(
        "crux_providers.gemini.client.record_observation", lambda *a, **k: None, raising=False
    )


def test_gemini_provider_defaults_and_props() -> None:
    """Provider exposes correct name, default model, and JSON support."""
    p = GeminiProvider(api_key=None, model=None)
    assert p.provider_name == "gemini"  # nosec B101 - pytest assertion in tests
    # default_model falls back to constant when not provided
    assert isinstance(p.default_model(), str) and p.default_model()  # nosec B101 - pytest assertion in tests
    assert p.supports_json_output() is True  # nosec B101 - pytest assertion in tests


def test_gemini_chat_sdk_missing_returns_meta_error() -> None:
    """When SDK is missing, chat returns a response with meta error info."""
    p = GeminiProvider(api_key="key", model="models/gemini-pro")  # pragma: allowlist secret - test-only fake key
    req = ChatRequest(model=p.default_model(), messages=[Message(role="user", content="hi")])
    # Ensure SDK is considered missing
    from crux_providers.gemini import client as gmod

    gmod.genai = None  # type: ignore
    resp = p.chat(req)
    assert resp.meta is not None  # nosec B101 - pytest assertion in tests
    assert resp.meta.extra.get("error")  # nosec B101 - pytest assertion in tests
    assert resp.text is None  # nosec B101 - pytest assertion in tests


def test_gemini_supports_streaming_false_without_sdk_or_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """supports_streaming is False when SDK or API key is missing."""
    p = GeminiProvider(api_key=None, model="models/gemini-pro")
    # No SDK, no key
    from crux_providers.gemini import client as gmod

    gmod.genai = None  # type: ignore
    assert p.supports_streaming() is False  # nosec B101 - pytest assertion in tests

    # With SDK but still no key
    _install_fake_genai(monkeypatch)
    assert p.supports_streaming() is False  # nosec B101 - pytest assertion in tests


def test_gemini_chat_success_with_fake_sdk(monkeypatch: pytest.MonkeyPatch) -> None:
    """Chat returns text when SDK is available and API key is set."""
    _install_fake_genai(monkeypatch)
    _stub_record_observation(monkeypatch)
    p = GeminiProvider(api_key="key", model="models/gemini-pro")  # pragma: allowlist secret - test-only fake key
    req = ChatRequest(model=p.default_model(), messages=[Message(role="user", content="hello")])
    resp = p.chat(req)
    assert resp.text == "ok"  # nosec B101 - pytest assertion in tests
    assert resp.parts and resp.parts[0].text == "ok"  # nosec B101 - pytest assertion in tests


def test_gemini_stream_chat_emits_deltas_and_finish(monkeypatch: pytest.MonkeyPatch) -> None:
    """Streaming path yields deltas and terminates with a final event."""
    _install_fake_genai(monkeypatch)
    _stub_record_observation(monkeypatch)
    p = GeminiProvider(api_key="key", model="models/gemini-pro")  # pragma: allowlist secret - test-only fake key
    req = ChatRequest(model=p.default_model(), messages=[Message(role="user", content="go")])
    events = list(p.stream_chat(req))
    deltas: List[str] = [e.delta for e in events if getattr(e, "delta", None)]  # type: ignore[attr-defined]
    assert deltas == ["alpha", "beta"]  # nosec B101 - pytest assertion in tests
    assert any(getattr(e, "finish", False) for e in events)  # nosec B101 - pytest assertion in tests
