"""Unit tests for `crux_providers.base.openai_style_helpers`.

Focus on pure helpers to raise coverage safely.
"""

from __future__ import annotations

import pytest

from crux_providers.base.models import ChatRequest, Message
from crux_providers.base.openai_style_parts.style_helpers import (
    extract_openai_text,
    prepare_response_format,
    extract_messages_and_format,
    build_chat_params,
    invoke_create,
)


class _Resp:
    class _Choice:
        class _Message:
            def __init__(self, content: str) -> None:
                self.content = content

        def __init__(self, content: str) -> None:
            self.message = _Resp._Choice._Message(content)

    def __init__(self, content: str) -> None:
        self.choices = [self._Choice(content)]


def test_extract_openai_text_ok():
    assert extract_openai_text(_Resp("hi")) == "hi"  # nosec B101 - test assertion


def test_extract_openai_text_missing():
    class _Bad:
        pass

    assert extract_openai_text(_Bad()) == ""  # nosec B101 - test assertion


def test_prepare_response_format_variants():
    req = ChatRequest(model="gpt-x", messages=[Message(role="user", content="x")], response_format="json_object")
    rf, structured = prepare_response_format(req)
    assert rf == {"type": "json_object"} and structured is True  # nosec B101

    req2 = ChatRequest(model="gpt-x", messages=[Message(role="user", content="x")], json_schema={"a": 1})
    rf2, structured2 = prepare_response_format(req2)
    assert rf2 == {"type": "json_schema", "json_schema": {"a": 1}} and structured2 is True  # nosec B101

    req3 = ChatRequest(model="gpt-x", messages=[Message(role="user", content="x")])
    rf3, structured3 = prepare_response_format(req3)
    assert rf3 is None and structured3 is False  # nosec B101


def test_extract_messages_and_format():
    req = ChatRequest(
        model="gpt-x",
        messages=[Message(role="system", content="s"), Message(role="user", content="u")],
        response_format="json_object",
    )
    messages, rf, is_struct = extract_messages_and_format(req)
    assert messages == [{"role": "system", "content": "s"}, {"role": "user", "content": "u"}]  # nosec B101
    assert rf == {"type": "json_object"} and is_struct is True  # nosec B101

    req2 = ChatRequest(model="gpt-x", messages=[Message(role="user", content="u")], json_schema={"foo": "bar"})
    m2, rf2, is_struct2 = extract_messages_and_format(req2)
    assert m2 == [{"role": "user", "content": "u"}]  # nosec B101
    assert rf2 == {"type": "json_schema", "json_schema": {"foo": "bar"}} and is_struct2 is False  # nosec B101


def test_build_chat_params_minimal_and_options():
    req = ChatRequest(model="gpt-x", messages=[Message(role="user", content="u")], max_tokens=10, temperature=0.2, tools=[{"type": "function"}])
    params = build_chat_params("gpt-x", [{"role": "user", "content": "u"}], req, {"type": "json_object"})
    assert params["model"] == "gpt-x" and params["messages"]  # nosec B101
    assert params["max_tokens"] == 10 and params["temperature"] == 0.2  # nosec B101
    assert params["response_format"] == {"type": "json_object"} and params["tools"] == [{"type": "function"}]  # nosec B101


class _DummyClient:
    class _Chat:
        class _Completions:
            def create(self, **kwargs):  # pragma: no cover - success path covered implicitly
                return {"ok": True, "kwargs": kwargs}

        def __init__(self) -> None:
            self.completions = _DummyClient._Chat._Completions()

    def __init__(self) -> None:
        self.chat = _DummyClient._Chat()


class _FailingClient:
    class _Chat:
        class _Completions:
            def create(self, **kwargs):
                raise RuntimeError("boom")

        def __init__(self) -> None:
            self.completions = _FailingClient._Chat._Completions()

    def __init__(self) -> None:
        self.chat = _FailingClient._Chat()


def test_invoke_create_success():
    client = _DummyClient()
    out = invoke_create(client, {"model": "gpt-x", "messages": []}, model="gpt-x", provider_name="openai")
    assert out["ok"] is True  # nosec B101


def test_invoke_create_failure_wrapped():
    client = _FailingClient()
    with pytest.raises(Exception) as excinfo:
        invoke_create(client, {"model": "gpt-x", "messages": []}, model="gpt-x", provider_name="openai")
    # Import here to avoid circulars at test collection time
    from crux_providers.base.errors import ProviderError

    assert isinstance(excinfo.value, ProviderError)  # nosec B101
