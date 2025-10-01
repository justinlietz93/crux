"""Protocol definition for OpenAI-style chat completions clients.

Purpose:
- Describe the minimal client surface required by ``BaseOpenAIStyleProvider``
  without tying the base class to a concrete SDK implementation.

External dependencies:
- None (typing only). Concrete providers supply an SDK client instance that
  conforms to this protocol at runtime.

Fallback/Timeout:
- This module defines no behavior; see ``base.py`` for timeout and fallback
  semantics in the calling code.
"""

from __future__ import annotations

from typing import Protocol


class _ChatCompletionsClient(Protocol):
    """Protocol describing an OpenAI-compatible chat completions client.

    Implementations are expected to expose ``chat.completions.create(**params)``
    returning either a non-streaming response object (with ``choices[0].message``)
    or a streaming iterator yielding chunks with ``choices[0].delta.content``.
    """

    class _ChatNS(Protocol):  # pragma: no cover - structural hint only
        class _CompletionsNS(Protocol):
            def create(self, **params):  # noqa: D401 - SDK parity
                """Start a chat completion request (streaming or non-streaming)."""
                ...

        completions: _CompletionsNS

    chat: _ChatNS


__all__ = ["_ChatCompletionsClient"]
