"""Tests for centralized streaming capability helper and OpenAI structured guard.

Focus:
- streaming_supported() boolean matrix
- OpenAIProvider.stream_chat rejects structured streaming inputs (json_object/json_schema/tools)

Design:
- No conditionals or loops inside assertion blocks (clarity & static analysis friendliness).
- SDK presence is forced via a stub to avoid conditional patching logic.

# Security Note:
# Using plain `assert` is intentional & idiomatic in pytest. Suppress Bandit B101 for this test file.
# nosec B101
"""
from __future__ import annotations

from typing import Optional
import pytest

from crux_providers.base.streaming import streaming_supported
from crux_providers.openai.client import OpenAIProvider
from crux_providers.base.models import ChatRequest, Message


class _FakeSDK:  # simple stand-in for openai.OpenAI class
    ...


def _fake_key_getter(val: Optional[str]):
    return lambda: val


@pytest.mark.parametrize(
    "sdk_obj,require_api_key,key,expected",
    [
        (None, True, None, False),  # missing sdk + key required
    (None, False, None, True),  # sdk may be absent when key not required (local provider case)
        (_FakeSDK, True, None, False),  # sdk present but key required & missing
        (_FakeSDK, True, "", False),  # empty key
        (_FakeSDK, True, "   ", False),  # whitespace key
        (_FakeSDK, True, "sk-abc", True),  # valid key
        (_FakeSDK, False, None, True),  # key not required
    ],
)
def test_streaming_supported_matrix(sdk_obj, require_api_key, key, expected):
    assert ( # nosec B101
        streaming_supported(
            sdk_obj, require_api_key=require_api_key, api_key_getter=_fake_key_getter(key)
        )
        is expected
    )


@pytest.fixture()
def patched_provider(monkeypatch):
    # Inject a fake API key into provider config getter (openai only)
    from crux_providers.config import get_provider_config as real_get_cfg

    def fake_get_cfg(name: str):
        cfg = real_get_cfg(name)
        if name == "openai":
            api_section = cfg.setdefault("api", {})
            openai_section = api_section.setdefault("openai", {})
            openai_section["api_key"] = "sk-test"  # pragma: allowlist secret (test stub)
        return cfg

    monkeypatch.setattr(
    "crux_providers.openai.client.get_provider_config", fake_get_cfg
    )
    # Always stub SDK symbol to guarantee streaming_supported() path
    monkeypatch.setattr(
    "crux_providers.openai.client._OpenAIClient", _FakeSDK
    )
    return OpenAIProvider()


@pytest.mark.parametrize(
    "req_kwargs",
    [
        {"response_format": "json_object"},
        {"json_schema": {"type": "object", "properties": {}}},
        {"tools": [{"name": "dummy", "description": "d"}]},
    ],
)
def test_openai_provider_structured_streaming_guard(patched_provider, req_kwargs):
    base_messages = [Message(role="user", content="hello")]
    req = ChatRequest(model="gpt-test", messages=base_messages, **req_kwargs)
    events = list(patched_provider.stream_chat(req))
    assert len(events) == 1 # nosec B101
    assert events[0].error is not None # nosec B101


def test_openai_provider_stream_chat_non_structured(patched_provider):
    base_messages = [Message(role="user", content="hello")]
    req = ChatRequest(model="gpt-test", messages=base_messages)
    events = list(patched_provider.stream_chat(req))
    # We only assert absence of structured policy error sentinel.
    assert ( # nosec B101
        len(events) != 1
        or events[0].error != "STRUCTURED_STREAMING_UNSUPPORTED"
    )
