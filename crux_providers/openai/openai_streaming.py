"""Retired module: OpenAI streaming mixin.

This module has been removed in favor of the unified streaming implementation
powered by ``BaseStreamingAdapter`` (see ``base.openai_style_parts``). Any
import of this module is considered a bug and intentionally fails fast to
prevent accidental usage and duplicated logic.

Timeouts & retries are handled centrally by the shared base provider.
"""

raise ImportError(
    "crux_providers.openai.openai_streaming was removed. Use OpenAIProvider "
    "from crux_providers.openai.client (BaseOpenAIStyleProvider-based)."
)
