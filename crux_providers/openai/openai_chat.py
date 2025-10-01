"""Retired module: legacy OpenAI chat helpers.

Purpose:
- This module was removed in favor of the unified provider implementation.
- It remains only to raise an explicit error if older import paths are used.

Use instead:
- ``OpenAIProvider`` from ``crux_providers.openai.client`` implementing the
    standardized ``BaseOpenAIStyleProvider`` contract.

External dependencies: None.
Fallback semantics: Not applicable (module import always fails).
Timeout strategy: Not applicable (no I/O is performed).
"""

raise ImportError(
    "crux_providers.openai.openai_chat was removed. Use OpenAIProvider from "
    "crux_providers.openai.client."
)
