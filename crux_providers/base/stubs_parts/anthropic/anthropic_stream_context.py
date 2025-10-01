"""Protocol for Anthropic streaming context objects.

Purpose:
        Provide a minimal, provider-shaped structural Protocol used by shared
        streaming helpers to "duck type" Anthropic SDK objects without importing
        the SDK. Centralizing Protocols under ``base/stubs_parts`` ensures:

        - Inward dependency flow: shared code (``base``) never imports provider
            packages; providers depend on ``base`` — not the other way around.
        - Optional SDK handling: importing this module does not require the
            Anthropic SDK to be installed, avoiding hard dependencies and import
            errors on environments where a provider is unused.
        - Cross-provider normalization: consistent naming and behavior for
            streaming and usage shapes across providers, reducing duplication.

Context modeled:
        Some Anthropic SDK versions expose a context manager from
        ``client.messages.stream(**params)`` whose yielded object offers either an
        iterator interface directly or a nested ``text_stream`` iterator. This
        Protocol models the latter to allow structural checks without brittle
        ``getattr`` chains.

External dependencies:
        - None. This file defines typing-only Protocols and introduces no SDK
            imports or side effects.

Fallback semantics:
        - Callers should gracefully handle objects that do not satisfy this
            Protocol (e.g., treat the yielded object as a generic iterable of text
            segments when available).

Timeout strategy:
        - Not applicable. Protocol definitions contain no blocking operations.
"""

from __future__ import annotations

from typing import Iterable, Protocol, runtime_checkable


@runtime_checkable
class AnthropicStreamContext(Protocol):
    """Structural contract for contexts exposing a ``text_stream`` iterator."""

    @property
    def text_stream(self) -> Iterable[str]:  # pragma: no cover - structural
        """An iterator of text deltas produced by the streaming session."""
