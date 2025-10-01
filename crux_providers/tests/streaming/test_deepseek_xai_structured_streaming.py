"""Structured streaming parity tests for Deepseek and XAI providers.

These tests validate that our OpenAI-style structured translator surfaces
function-call partials and metadata without disrupting text deltas or metrics.
We avoid real SDK objects by using simple stubs that mimic the attribute shape
used by the translator: ``choices[0].delta.tool_calls[0].function.{name,arguments}``.
"""

from __future__ import annotations

from typing import Iterable, Optional

from crux_providers.base.streaming.streaming_adapter import BaseStreamingAdapter
from crux_providers.base.logging import LogContext
from crux_providers.base.resilience.retry import RetryConfig
from crux_providers.base.openai_style_parts.structured import translate_openai_structured_chunk


class _Delta:
    def __init__(self, content: Optional[str] = None, *, name: Optional[str] = None, args: Optional[str] = None):
        self.content = content
        if name is not None or args is not None:
            self.tool_calls = [type("_TC", (), {"function": type("_FN", (), {"name": name, "arguments": args})()})()]


class _Chunk:
    def __init__(self, content: Optional[str] = None, *, name: Optional[str] = None, args: Optional[str] = None):
        self.choices = [type("_Choice", (), {"delta": _Delta(content, name=name, args=args)})()]


def _retry_factory(_op: str) -> RetryConfig:
    return RetryConfig(max_attempts=1, delay_base=1.0)


def _translator(ch: _Chunk) -> Optional[str]:
    try:
        return ch.choices[0].delta.content
    except Exception:  # pragma: no cover - resilient translator
        return None


def _mk_adapter(chunks: list[_Chunk]) -> BaseStreamingAdapter:
    return BaseStreamingAdapter(
        ctx=LogContext(provider="openai-style", model="fake-model", request_id=None, response_id=None),
        provider_name="openai-style",
        model="fake-model",
        starter=lambda: chunks,
        translator=_translator,
        structured_translator=translate_openai_structured_chunk,
        retry_config_factory=_retry_factory,
        logger=type("_L", (), {"isEnabledFor": lambda *_: False, "info": lambda *_: None})(),
    )


def test_deepseek_like_stream_emits_structured_partials_and_name():
    # Simulate Deepseek/XAI OpenAI-style partials then a name-only chunk
    chunks: list[_Chunk] = [
        _Chunk(content="Hello", args="{\"a\":"),
        _Chunk(content=", world", args="1}"),
        _Chunk(content=None, name="tool_do"),
    ]
    events = list(_mk_adapter(chunks).run())
    # Expect three mid-stream + one terminal
    assert len(events) == 4  # nosec B101 - test assertion
    assert events[-1].finish is True  # nosec B101
    mids = events[:-1]
    assert any(e.delta for e in mids)  # nosec B101
    assert any(e.structured and e.structured.partial for e in mids)  # nosec B101
    assert any(e.structured and e.structured.metadata for e in mids)  # nosec B101
    # Metrics sanity
    adapter = _mk_adapter(chunks)
    list(adapter.run())
    assert adapter.metrics.emitted == 3  # nosec B101
    assert adapter.metrics.time_to_first_token_ms is not None  # nosec B101
