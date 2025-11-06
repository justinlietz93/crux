"""Context management package.

Provides token counting, context window management, and conversation pruning.
"""

from .manager import BaseContextManager, MODEL_CONTEXT_LIMITS

__all__ = ["BaseContextManager", "MODEL_CONTEXT_LIMITS"]
