"""Translate OpenAI-style streaming deltas into structured output DTOs.

Pure, side-effect-free translator that extracts OpenAI Chat Completions
``tool_calls.function`` fragments and returns a provider-agnostic envelope.

- Returns finalized function calls when arguments are a mapping or valid JSON
- Returns partial text fragments while JSON is incomplete
- Returns metadata with name-only when only the function name is available
- Returns None when the chunk carries no relevant tool/function payload

This module has no provider SDK dependencies and performs no I/O.
"""

from __future__ import annotations

import json
from typing import Any, Mapping
from ..dto.structured_output import StructuredOutputDTO  # type: ignore
from ..dto.function_call import FunctionCallDTO  # type: ignore


def translate_openai_structured_chunk(chunk: Any):  # -> Optional[StructuredOutputDTO]
    """Convert a single streaming chunk into a structured output envelope.

    Parameters
    ----------
    chunk: Any
        Object exposing an OpenAI-style shape with
        ``choices[0].delta.tool_calls[0].function`` (``name`` and ``arguments``).
        Attribute access is attempted first; dict-like access is tolerated.

    Returns
    -------
    StructuredOutputDTO | None
        See module docstring for behavior variants.
    """
    try:
        # Translator body; be resilient to shape mismatches

        choices = getattr(chunk, "choices", None)
        if not choices:
            return None
        choice0 = choices[0]
        delta = getattr(choice0, "delta", None)
        if delta is None:
            return None
        tool_calls = getattr(delta, "tool_calls", None)
        if not tool_calls:
            return None
        first = tool_calls[0]
        fn = getattr(first, "function", None)
        if fn is None:
            return None

        name = getattr(fn, "name", None)
        args_fragment = getattr(fn, "arguments", None)

        # Mapping arguments → finalized function call
        if isinstance(args_fragment, Mapping):
            return StructuredOutputDTO(
                function_call=FunctionCallDTO(
                    name=str(name) if name else "",
                    arguments=dict(args_fragment),
                ),
                metadata={"function_name": str(name)} if name else {},
            )

        # String/bytes arguments → parse JSON or emit partial
        if isinstance(args_fragment, (str, bytes)):
            arg_text = (
                args_fragment.decode("utf-8")
                if isinstance(args_fragment, bytes)
                else args_fragment
            )
            if name:
                try:
                    parsed = json.loads(arg_text)
                except Exception:
                    return StructuredOutputDTO(
                        partial=str(arg_text),
                        metadata={"function_name": str(name)},
                    )
                else:
                    if isinstance(parsed, dict):
                        return StructuredOutputDTO(
                            function_call=FunctionCallDTO(
                                name=str(name), arguments=parsed
                            ),
                            metadata={"function_name": str(name)},
                        )
                    return StructuredOutputDTO(
                        partial=str(arg_text),
                        metadata={"function_name": str(name)},
                    )
            return StructuredOutputDTO(partial=str(arg_text))

        # Name-only without arguments
        if name:
            return StructuredOutputDTO(metadata={"function_name": str(name)})

        return None
    except Exception:  # pragma: no cover - translator must be resilient
        return None


__all__ = ["translate_openai_structured_chunk"]
