"""Streaming helpers for the OpenRouter provider.

Purpose:
- Provide small, reusable helpers to keep ``client.py`` below the 500 LOC
    architecture limit and centralize streaming-related utilities.
- Expose a minimal retry-config factory and streaming translators for text and
    structured (function-call style) outputs that integrate with
    ``BaseStreamingAdapter``.

Notes:
- These helpers do not perform I/O. They are pure translation utilities or
    provider-agnostic configuration shims. They are intentionally defensive and
    resilient to malformed or partial stream lines.
"""

from __future__ import annotations

from typing import Optional, Any
import json

from ..base.dto.structured_output import StructuredOutputDTO


class OpenRouterStreamingMixin:
    """Mixin providing streaming-related helper hooks."""

    def _default_retry_config(self, phase: str):
        """Return a default retry configuration for streaming start phase.

        Parameters:
            phase: Adapter lifecycle phase requesting a retry config.

        Returns:
            A ``RetryConfig`` instance representing the default policy.
        """
        from ..base.resilience.retry import RetryConfig

        return RetryConfig()


def translate_text_from_line(resp_line: Any) -> Optional[str]:  # noqa: ANN401 - external types
    """Translate an OpenRouter SSE line into a text delta.

    Parameters:
        resp_line: Raw line emitted by ``httpx.Response.iter_lines()``. Can be
            ``bytes`` or ``str``; may include the ``"data:"`` prefix.

    Returns:
        The string delta content if present, otherwise ``None``.

    Failure modes:
        - Malformed JSON or unexpected shapes return ``None``. This function is
          intentionally non-throwing to keep streaming robust under partials.
    """
    if not resp_line:
        return None
    try:
        line = resp_line
        if isinstance(line, bytes):
            if line.startswith(b"data:"):
                line = line[5:].strip()
            if line == b"[DONE]":
                return None
            data = json.loads(line)
        else:
            s = str(line)
            if s.startswith("data:"):
                s = s[5:].strip()
            if s == "[DONE]":
                return None
            data = json.loads(s)
        return data.get("choices", [{}])[0].get("delta", {}).get("content")
    except Exception:  # pragma: no cover - translator must be resilient
        return None


def translate_structured_from_line(resp_line: Any) -> Optional[StructuredOutputDTO]:    # noqa: ANN401 - external types
    """Translate an OpenRouter SSE line into a structured payload if present.

    This translator surfaces function-call style tool invocations as either
    partial argument fragments (``StructuredOutputDTO.partial``) or metadata
    when only the function name is available. It remains stateless by design
    and does not attempt to accumulate or parse full JSON arguments.

    Parameters:
        resp_line: Raw line emitted by ``httpx.Response.iter_lines()``. Can be
            ``bytes`` or ``str``; may include the ``"data:"`` prefix.

    Returns:
        A ``StructuredOutputDTO`` when structured info is present; otherwise
        ``None``.

    Failure modes:
        - Malformed JSON or unexpected shapes return ``None``. This function is
          intentionally non-throwing to keep streaming robust under partials.
    """
    if not resp_line:
        return None
    try:
        return extract_tool_invocation(resp_line)
    except Exception:  # pragma: no cover - translator must be resilient
        return None

def extract_tool_invocation(resp_line):
    """Extracts structured output information from an OpenRouter SSE line.

    This function parses a single SSE line and attempts to extract function-call
    style tool invocation fragments or metadata. It returns a StructuredOutputDTO
    containing either partial arguments or function name metadata, or None if no
    structured information is present.

    Args:
        resp_line: Raw line emitted by ``httpx.Response.iter_lines()``. Can be
            ``bytes`` or ``str``; may include the ``"data:"`` prefix.

    Returns:
        StructuredOutputDTO with partial arguments or metadata, or None if not found.
    """
    line = resp_line
    if isinstance(line, bytes):
        if line.startswith(b"data:"):
            line = line[5:].strip()
        if line == b"[DONE]":
            return None
        data = json.loads(line)
    else:
        s = str(line)
        if s.startswith("data:"):
            s = s[5:].strip()
        if s == "[DONE]":
            return None
        data = json.loads(s)

    delta = data.get("choices", [{}])[0].get("delta", {})
    tool_calls = delta.get("tool_calls")
    if not tool_calls:
        return None
    first = tool_calls[0] or {}
    fn = first.get("function") or {}
    if args_fragment := fn.get("arguments"):
        return StructuredOutputDTO(partial=str(args_fragment))
    if name := fn.get("name"):
        return StructuredOutputDTO(metadata={"function_name": str(name)})
    return None

__all__ = [
    "OpenRouterStreamingMixin",
    "translate_text_from_line",
    "translate_structured_from_line",
]
