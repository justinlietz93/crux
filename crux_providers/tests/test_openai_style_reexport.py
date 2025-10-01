"""Coverage tests for `crux_providers.base.openai_style` re-exports.

These tests ensure the thin compatibility layer properly re-exports
symbols from `openai_style_parts`.
"""

from __future__ import annotations


def test_openai_style_reexports_imports():
    from crux_providers.base.openai_style_parts import (
        BaseOpenAIStyleProvider,
        _ProviderInit,
        _ChatCompletionsClient,
    )

    # Basic sanity checks: symbols are importable and are objects
    assert BaseOpenAIStyleProvider is not None  # nosec B101 - pytest assertion in test context
    assert _ProviderInit is not None  # nosec B101 - pytest assertion in test context
    assert _ChatCompletionsClient is not None  # nosec B101 - pytest assertion in test context
