"""Unit tests for input_size_guard utilities.

Covers default-on guard semantics, per-string enforcement, request measurement,
multipart content handling, spillover condensation helper, and integration via
``build_chat_request``.
"""
from __future__ import annotations

import os
import importlib
import contextlib

import pytest

from crux_providers.base.models import Message, ContentPart, ChatRequest
from crux_providers.service import helpers as svc_helpers


def _reset_env():
    for k in ["PROVIDERS_MAX_INPUT_ENABLED", "PROVIDERS_MAX_INPUT_CHARS"]:
        os.environ.pop(k, None)


def test_enforce_max_input_disabled_noop():
    _reset_env()
    from crux_providers.utils import input_size_guard as g
    importlib.reload(g)
    # Default-on guard but with no max configured (0) → no-op
    assert g.is_guard_enabled() is True  # nosec B101 - test assertion
    assert g.get_max_input_chars() == 0  # nosec B101 - test assertion
    g.enforce_max_input("x" * 10)  # should not raise


def test_enforce_max_input_enabled_raises():
    _reset_env()
    os.environ["PROVIDERS_MAX_INPUT_ENABLED"] = "1"
    os.environ["PROVIDERS_MAX_INPUT_CHARS"] = "5"
    from crux_providers.utils import input_size_guard as g
    importlib.reload(g)
    with pytest.raises(ValueError):
        g.enforce_max_input("x" * 6)


def test_measure_request_chars_with_multipart():
    _reset_env()
    from crux_providers.utils import input_size_guard as g
    m = Message(
        role="user",
        content=[
            ContentPart(type="text", text="hello"),
            ContentPart(type="image", data={"url": "http://..."}),
            ContentPart(type="text", text="world"),
        ],
    )
    req = ChatRequest(model="m", messages=[m])
    assert g.measure_request_chars(req) == len("helloworld")  # nosec B101 - pytest assertion in tests


def test_build_chat_request_condenses_when_enabled(monkeypatch):
    _reset_env()
    os.environ["PROVIDERS_MAX_INPUT_ENABLED"] = "true"
    os.environ["PROVIDERS_MAX_INPUT_CHARS"] = "4"
    body = type("Body", (), {})()
    body.model = "m"
    body.messages = [type("M", (), {"role": "user", "content": "hello"})()]
    body.max_tokens = None
    body.temperature = None
    body.response_format = None
    body.json_schema = None
    body.tools = None
    body.extra = {}
    req = svc_helpers.build_chat_request(body)
    # Expect user content to be condensed to <= 4 characters
    assert isinstance(req, ChatRequest)  # nosec B101 - test assertion
    user_text = "".join(m.text_or_joined() for m in req.messages if m.role == "user")
    assert len(user_text) <= 4  # nosec B101 - test assertion


def test_build_chat_request_noop_when_disabled():
    _reset_env()
    # Explicitly disable via env to ensure no exception regardless of size
    os.environ["PROVIDERS_MAX_INPUT_ENABLED"] = "0"
    body = type("Body", (), {})()
    body.model = "m"
    body.messages = [type("M", (), {"role": "user", "content": "hello"})()]
    body.max_tokens = None
    body.temperature = None
    body.response_format = None
    body.json_schema = None
    body.tools = None
    body.extra = {}
    req = svc_helpers.build_chat_request(body)
    assert isinstance(req, ChatRequest)  # nosec B101 - pytest assertion in tests
