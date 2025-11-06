"""Deterministic mock provider backed by JSON fixtures for offline testing.

Purpose
-------
Provide a lightweight adapter that implements the ``LLMProvider`` contract
while avoiding any network traffic. Responses are sourced from declarative
JSON fixtures so unit and integration tests can exercise higher layers (CLI,
logging, streaming) without relying on real providers.

External dependencies
---------------------
Standard library only. Fixtures are loaded via ``importlib.resources`` to keep
packaging simple and hermetic.

Timeout and retry semantics
---------------------------
No external calls are issued; retries are effectively disabled by returning a
single-attempt ``RetryConfig`` to the shared ``BaseStreamingAdapter``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from importlib import resources
from typing import Any, Dict, Iterable, Iterator, List, Mapping, Optional

from ..base.interfaces import HasDefaultModel, LLMProvider, SupportsStreaming
from ..base.logging import LogContext, get_logger, normalized_log_event
from ..base.models import ChatRequest, ChatResponse, ProviderMetadata
from ..base.streaming import ChatStreamEvent
from ..base.streaming.streaming_adapter import BaseStreamingAdapter
from ..base.resilience.retry import RetryConfig

_FIXTURE_RESOURCE = "chat_completions.json"


@dataclass
class FixtureResponse:
    """Container for a single fixture response entry."""

    text: str
    meta: Mapping[str, Any]
    stream: List[str]
    prompt_key: str


def load_fixture_catalog(resource: str = _FIXTURE_RESOURCE) -> Dict[str, Any]:
    """Load the JSON fixture catalog bundled with the mock provider.

    Parameters
    ----------
    resource: str, default ``chat_completions.json``
        Name of the resource file located under ``crux_providers.mock.fixtures``.

    Returns
    -------
    Dict[str, Any]
        Parsed JSON catalog describing provider defaults and responses.
    """

    package = "crux_providers.mock.fixtures"
    data = resources.files(package).joinpath(resource).read_text(encoding="utf-8")
    return json.loads(data)


class MockProvider(LLMProvider, SupportsStreaming, HasDefaultModel):
    """Adapter that returns canned responses from fixtures instead of live APIs."""

    def __init__(
        self,
        *,
        provider: str = "mock",
        fixture_name: str = "default",
        catalog: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Initialize the mock provider with fixture-backed responses.

        Parameters
        ----------
        provider: str, default ``"mock"``
            Logical provider name used for metadata and logging. When the factory
            routes real providers through mock mode, this is set to the original
            provider key (e.g., ``"openai"``).
        fixture_name: str, default ``"default"``
            Label stored in metadata to aid debugging when multiple fixture sets
            exist. Currently informational; reserved for future multi-fixture
            routing.
        catalog: Optional[Dict[str, Any]]
            Pre-parsed fixture catalog. Primarily used by tests to inject custom
            catalogs without reading from disk.
        """

        self._provider = provider or "mock"
        self._fixture_name = fixture_name
        self._catalog = catalog or load_fixture_catalog()
        self._logger = get_logger(f"providers.mock.{self._provider}")
        self._provider_block = self._resolve_provider_block()
        self._fallback_block = self._catalog.get("providers", {}).get("*", {})
        fallback_model = self._fallback_block.get("model", self._catalog.get("default_model", "mock-gpt"))
        self._model = str(self._provider_block.get("model", fallback_model))
        self._responses: Mapping[str, Any] = self._provider_block.get("responses", {})
        self._fallback_responses: Mapping[str, Any] = self._fallback_block.get("responses", {})
        self._last_metadata: Optional[ProviderMetadata] = None

    # ------------------------------------------------------------------
    # Interface properties

    @property
    def provider_name(self) -> str:
        """Return the logical provider name represented by this mock instance."""

        return self._provider

    def default_model(self) -> Optional[str]:  # type: ignore[override]
        """Return the default model configured for this mock provider."""

        return self._model

    def supports_streaming(self) -> bool:  # type: ignore[override]
        """Streaming is always supported for the deterministic mock provider."""

        return True

    # ------------------------------------------------------------------
    # Core LLMProvider API

    def chat(self, request: ChatRequest) -> ChatResponse:
        """Return a deterministic chat response sourced from fixtures."""

        model = request.model or self._model
        entry = self._select_response(request)
        metadata = self._build_metadata(model, entry)
        ctx = LogContext(provider=self.provider_name, model=model)
        normalized_log_event(self._logger, "chat.start", ctx, phase="start", emitted=None, tokens=None)
        response = ChatResponse(text=entry.text, parts=None, raw={"fixture": self._fixture_name}, meta=metadata)
        normalized_log_event(self._logger, "chat.end", ctx, phase="finalize", emitted=True, tokens=None)
        self._last_metadata = metadata
        return response

    def stream_chat(self, request: ChatRequest) -> Iterator[ChatStreamEvent]:
        """Yield streaming deltas using the shared ``BaseStreamingAdapter``."""

        model = request.model or self._model
        entry = self._select_response(request)
        metadata = self._build_metadata(model, entry)
        ctx = LogContext(provider=self.provider_name, model=model)
        normalized_log_event(self._logger, "stream.start", ctx, phase="start", emitted=None, tokens=None)

        deltas = list(entry.stream) if entry.stream else _chunk_text(entry.text)

        def _starter() -> Iterable[str]:
            return list(deltas)

        adapter = BaseStreamingAdapter(
            ctx=ctx,
            provider_name=self.provider_name,
            model=model,
            starter=_starter,
            translator=lambda chunk: str(chunk),
            retry_config_factory=lambda phase: RetryConfig(max_attempts=1, delay_base=1.0),
            logger=self._logger,
            on_complete=lambda emitted: self._on_stream_complete(metadata, emitted),
        )

        for event in adapter.run():
            if event.finish and not event.error:
                event.raw = {"metadata": metadata.to_dict()}
                self._last_metadata = metadata
            yield event

    # ------------------------------------------------------------------
    # Helper utilities

    def _resolve_provider_block(self) -> Mapping[str, Any]:
        """Return the provider-specific fixture block with wildcard fallback.

        Returns
        -------
        Mapping[str, Any]
            Fixture section for ``self._provider`` or the ``"*"`` fallback.
        """

        providers = self._catalog.get("providers", {})
        return providers.get(self._provider, providers.get("*", {}))

    def _select_response(self, request: ChatRequest) -> FixtureResponse:
        """Select the best matching fixture response for the given request.

        Parameters
        ----------
        request: ChatRequest
            Structured chat request submitted by the caller.

        Returns
        -------
        FixtureResponse
            Parsed fixture entry containing response text, metadata, and stream deltas.
        """

        prompt = _extract_prompt(request)
        responses = self._responses
        raw = (
            responses.get(prompt)
            or responses.get(prompt.lower())
            or self._fallback_responses.get(prompt)
            or self._fallback_responses.get(prompt.lower())
            or responses.get("*")
            or self._fallback_responses.get("*")
            or {"text": "", "meta": {"extra": {"source": "fixture", "variant": "missing"}}}
        )
        text = str(raw.get("text", ""))
        meta = raw.get("meta", {}) or {}
        stream = list(raw.get("stream", []))
        if not stream and text:
            stream = _chunk_text(text)
        return FixtureResponse(text=text, meta=meta, stream=stream, prompt_key=prompt)

    def _build_metadata(self, model: str, entry: FixtureResponse) -> ProviderMetadata:
        """Construct ProviderMetadata enriched with fixture annotations.

        Parameters
        ----------
        model: str
            Effective model identifier resolved for the current request.
        entry: FixtureResponse
            Fixture entry selected for the chat invocation.

        Returns
        -------
        ProviderMetadata
            Metadata populated with fixture diagnostics and mock markers.
        """

        raw_meta = dict(entry.meta or {})
        extra = dict(raw_meta.get("extra", {}))
        extra.setdefault("fixture_name", self._fixture_name)
        extra.setdefault("prompt_key", entry.prompt_key)
        extra.setdefault("mock_provider", True)
        metadata = ProviderMetadata(
            provider_name=self.provider_name,
            model_name=model,
            token_param_used=raw_meta.get("token_param_used"),
            temperature_included=raw_meta.get("temperature_included"),
            http_status=raw_meta.get("http_status"),
            request_id=raw_meta.get("request_id"),
            response_id=raw_meta.get("response_id"),
            latency_ms=raw_meta.get("latency_ms"),
            extra=extra,
        )
        return metadata

    def _on_stream_complete(self, metadata: ProviderMetadata, emitted: bool) -> None:
        """Update metadata extra fields once streaming finishes.

        Parameters
        ----------
        metadata: ProviderMetadata
            Metadata object associated with the streaming invocation.
        emitted: bool
            Indicates whether any token deltas were produced.
        """

        metadata.extra.setdefault("stream_emitted", emitted)
        normalized_log_event(
            self._logger,
            "stream.mock.complete",
            LogContext(provider=self.provider_name, model=metadata.model_name),
            phase="finalize",
            emitted=emitted,
            tokens=None,
        )


# ---------------------------------------------------------------------------
# Module-level helpers


def _chunk_text(text: str, chunk_size: int = 16) -> List[str]:
    """Split text into readable chunks for deterministic streaming.

    Parameters
    ----------
    text: str
        Response text to segment into streaming deltas.
    chunk_size: int, default 16
        Maximum number of characters per chunk.

    Returns
    -------
    list[str]
        Ordered sequence of chunk strings.
    """

    if not text:
        return []
    return [text[i : i + chunk_size] for i in range(0, len(text), chunk_size)]


def _extract_prompt(request: ChatRequest) -> str:
    """Return the final user message from the chat request for fixture lookup.

    Parameters
    ----------
    request: ChatRequest
        Chat request whose final user message should be used as lookup key.

    Returns
    -------
    str
        Normalized prompt string or ``"*"`` when unavailable.
    """

    if not request.messages:
        return "*"
    last = request.messages[-1]
    content = getattr(last, "content", "")
    return str(content).strip() or "*"


__all__ = ["MockProvider", "load_fixture_catalog"]
