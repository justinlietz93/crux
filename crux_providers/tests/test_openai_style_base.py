"""Unit tests for BaseOpenAIStyleProvider using a fake client.

Covers:
- Happy path non-streaming chat returning text.
- Start-phase timeout handling.
"""

from __future__ import annotations

import types

from ..base.models import ChatRequest, Message
from ..base.openai_style_parts import BaseOpenAIStyleProvider, _ProviderInit
from ..base.timeouts import get_timeout_config


class _FakeChunk:  # noqa: D401 - simple container for parity
    class _Delta:
        def __init__(self, content: str) -> None:
            self.content = content

    class _Choice:
        def __init__(self, text: str) -> None:
            self.delta = _FakeChunk._Delta(text)

    def __init__(self, text: str) -> None:
        self.choices = [self._Choice(text)]


class _FakeResponse:
    class _Message:
        def __init__(self, content: str) -> None:
            self.content = content

    class _Choice:
        def __init__(self, content: str) -> None:
            self.message = _FakeResponse._Message(content)

    def __init__(self, content: str) -> None:
        self.choices = [self._Choice(content)]


class _FakeClient:
    def __init__(self, content: str, delay: float = 0.0) -> None:
        self._content = content
        self._delay = delay
        self.chat = types.SimpleNamespace(
            completions=types.SimpleNamespace(create=self._create)
        )

    def _create(self, **params):  # noqa: D401 - SDK parity
        import time as _t

        if self._delay:
            _t.sleep(self._delay)
        return _FakeResponse(self._content)


class _FakeProvider(BaseOpenAIStyleProvider):
    @property
    def provider_name(self) -> str:
        return "fake-openai-style"

    def __init__(self, content: str, delay: float = 0.0) -> None:
        sdk = object()  # sentinel meaning "installed"
        super().__init__(
            _ProviderInit(
                api_key="k",
                base_url="http://x",
                default_model="m",
                logger_name="providers.fake",
                sdk_sentinel=sdk,
                structured_streaming_supported=False,
            )
        )
        self._content = content
        self._delay = delay

    def _make_client(self):  # noqa: D401 - returns fake SDK client
        return _FakeClient(self._content, self._delay)


def test_base_openai_style_chat_happy_path():
    p = _FakeProvider(content="hello")
    req = ChatRequest(model="m", messages=[Message(role="user", content="hi")])
    resp = p.chat(req)
    assert resp.text == "hello"  # nosec B101 test assertion
    assert resp.meta.provider_name == p.provider_name  # nosec B101 test assertion


def test_base_openai_style_chat_start_timeout(monkeypatch):
    # Make start timeout very small to force timeout with delayed client
    monkeypatch.setenv("PROVIDERS_START_TIMEOUT_SECONDS", "0.01")
    p = _FakeProvider(content="slow", delay=0.1)
    req = ChatRequest(model="m", messages=[Message(role="user", content="hi")])
    out = p.chat(req)
    assert out.text is None  # nosec B101 test assertion
    assert out.meta.extra and out.meta.extra.get("code") == "timeout"  # nosec B101 test assertion
