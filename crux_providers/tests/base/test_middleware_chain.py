"""Tests for middleware chain integration and ordering."""

from __future__ import annotations

from contextlib import suppress
from typing import Iterator

from crux_providers.base.middleware.chain import ChatMiddlewareChain
from crux_providers.base.middleware.middleware_base import Middleware
from crux_providers.base.middleware.registry import set_global_middleware
from crux_providers.base.models import ChatRequest, ChatResponse
from crux_providers.base.openai_style_parts.base import BaseOpenAIStyleProvider
from crux_providers.base.openai_style_parts.provider_init import _ProviderInit
from crux_providers.base.streaming import ChatStreamEvent
from crux_providers.tests.utils import assert_true


class _NoopProvider(BaseOpenAIStyleProvider):
    """Minimal provider for testing that doesn't call external SDKs."""

    @property
    def provider_name(self) -> str:  # pragma: no cover - trivial
        return "noop"

    def _make_client(self):  # pragma: no cover - not used in tests
        raise NotImplementedError

    def supports_streaming(self) -> bool:
        return False  # disable streaming; focus on middleware sequencing

    def _invoke_nonstream_chat(self, *, model: str, request: ChatRequest, ctx):
        return ChatResponse(text="ok", parts=None, raw=None, meta=None)  # type: ignore[arg-type]

    def _build_stream_starter(self, *args, **kwargs):  # noqa: ANN001
        def _start():  # pragma: no cover - not executed, adapter stubbed by supports
            return None

        return _start


class _Recorder(Middleware):
    def __init__(self, name: str, log: list[str]):
        self.name = name
        self.log = log

    def before_chat(self, ctx, request):
        self.log.append(f"{self.name}:before_chat")
        return request

    def after_chat(self, ctx, response):
        self.log.append(f"{self.name}:after_chat")
        return response

    def before_stream(self, ctx, request):
        self.log.append(f"{self.name}:before_stream")
        return request


def _make_provider() -> _NoopProvider:
    init = _ProviderInit(api_key="k", base_url=None, default_model="m", logger_name="t", sdk_sentinel=object(), structured_streaming_supported=True)
    return _NoopProvider(init)


def test_noop_chain_is_safe() -> None:
    set_global_middleware(ChatMiddlewareChain(items=[]))
    p = _make_provider()
    r = p.chat(ChatRequest(model="m", messages=[]))
    assert_true(isinstance(r, ChatResponse), "chat returns ChatResponse")


def test_ordering_of_hooks_chat() -> None:
    log: list[str] = []
    chain = ChatMiddlewareChain(items=[_Recorder("a", log), _Recorder("b", log)])
    set_global_middleware(chain)
    p = _make_provider()
    _ = p.chat(ChatRequest(model="m", messages=[]))
    assert_true(log == ["a:before_chat", "b:before_chat", "a:after_chat", "b:after_chat"], "chat hooks ordering")


def test_before_stream_runs_first() -> None:
    log: list[str] = []
    chain = ChatMiddlewareChain(items=[_Recorder("a", log), _Recorder("b", log)])
    set_global_middleware(chain)
    p = _make_provider()
    evs: Iterator[ChatStreamEvent] = p.stream_chat(ChatRequest(model="m", messages=[]))
    with suppress(StopIteration):
        next(evs)  # trigger path up to adapter creation
    assert_true(log[:2] == ["a:before_stream", "b:before_stream"], "before_stream ordering")
