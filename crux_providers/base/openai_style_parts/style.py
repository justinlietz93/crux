"""Compatibility layer for OpenAI-style base abstractions.

This module now re-exports the split classes and protocols from
``crux_providers.base.openai_style_parts`` to preserve the public import surface
(`from crux_providers.base.openai_style_parts import BaseOpenAIStyleProvider, _ProviderInit, _ChatCompletionsClient`).

The implementation has been decomposed to satisfy architecture governance:
- ≤500 LOC per file
- Maximum of one class per file
"""

from __future__ import annotations

from . import BaseOpenAIStyleProvider, _ProviderInit, _ChatCompletionsClient

__all__ = [
    "BaseOpenAIStyleProvider",
    "_ProviderInit",
    "_ChatCompletionsClient",
]
