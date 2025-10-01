"""Retired module: legacy OpenAI helpers.

Purpose:
- This module was removed as part of the legacy/shims cleanup (Issue #72).
- It exists only to fail fast if lingering imports remain in downstream code.

Behavior:
- Importing this module raises ``ImportError`` immediately to surface the
    problem during startup or test discovery.

External dependencies: None.
Fallback semantics: Not applicable (module import always fails).
Timeout strategy: Not applicable (no I/O is performed).
"""

raise ImportError(
    "providers.openai.openai_legacy was removed. Migrate to the unified provider "
    "interfaces (ProviderFactory + ChatRequest/Message) and BaseStreamingAdapter."
)
