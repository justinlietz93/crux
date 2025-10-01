"""Split modules for OpenAI-style provider base abstractions.

This package contains focused modules extracted from the historical
``openai_style.py`` to align with governance:
- One class per file
- ≤500 LOC per file

Re-exports provide a stable import surface for convenience.
"""

from .base import BaseOpenAIStyleProvider
from .client_protocol import _ChatCompletionsClient
from .provider_init import _ProviderInit

__all__ = [
    "BaseOpenAIStyleProvider",
    "_ChatCompletionsClient",
    "_ProviderInit",
]
