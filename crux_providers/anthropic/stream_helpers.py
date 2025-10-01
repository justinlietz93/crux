"""Anthropic streaming helpers.

Purpose:
- Hold streaming-specific helpers to keep `helpers.py` under LOC and
  complexity budgets while preserving behavior.
"""

from __future__ import annotations

from typing import Any, Optional, Iterable

from ..base.errors import ErrorCode, ProviderError, classify_exception
from ..base.stubs import AnthropicStreamContext


def start_stream_context(client: Any, params: dict, model: str, provider_name: str):
    """Start a streaming context via `client.messages.stream`.

    Returns the SDK-provided context manager. Errors are normalized to
    `ProviderError` for unified retry and logging behavior by the caller.
    """
    try:
        return client.messages.stream(**params)
    except Exception as e:  # pragma: no cover
        code = classify_exception(e)
        raise ProviderError(
            code=code,
            message=str(e),
            provider=provider_name,
            model=model,
            retryable=code in (ErrorCode.TRANSIENT, ErrorCode.RATE_LIMIT, ErrorCode.TIMEOUT),
            raw=e,
        ) from e


def translate_stream_chunk(native_chunk: Any) -> Optional[str]:  # noqa: ANN401 - SDK type
    """Map Anthropic stream events to text deltas using Protocol stubs."""
    if native_chunk is None:
        return None
    if isinstance(native_chunk, str):
        return native_chunk or None
    try:
        from ..base.stubs import AnthropicStreamChunk  # local import, safe stub

        typed: AnthropicStreamChunk = native_chunk  # type: ignore[assignment]
        if typed.text:
            return typed.text or None
        if typed.delta and typed.delta.text:
            return typed.delta.text or None
    except Exception:  # pragma: no cover - translator must be resilient
        return None
    return None


def iterate_stream(stream_obj: Any) -> Iterable[str]:
    """Yield text deltas from a streaming context or iterator.

    This helper prefers the structural ``AnthropicStreamContext`` Protocol for
    objects exposing ``text_stream``; otherwise if the object is already an
    iterable of strings it is returned as-is.

    Parameters:
        stream_obj: The object yielded by the Anthropic SDK stream context.

    Yields:
        ``str`` text delta segments.
    """
    if isinstance(stream_obj, AnthropicStreamContext):  # structural check
        yield from stream_obj.text_stream
        return
    if isinstance(stream_obj, Iterable):  # best-effort generic fallback
        # mypy: cannot narrow element type; runtime relies on SDK contract
        yield from stream_obj  # type: ignore[misc]
