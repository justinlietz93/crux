"""IContextManager Protocol (single-class module).

Interface for managing conversation context, token counting, and context
window constraints. This enables providers to track and enforce token limits
across multi-turn conversations.
"""

from __future__ import annotations

from typing import List, Optional, Protocol, runtime_checkable

from ..models import Message


@runtime_checkable
class IContextManager(Protocol):
    """Interface for context management and token counting.

    Implementations should:
    - Count tokens for messages and completions
    - Track cumulative context across conversation turns
    - Enforce model-specific context window limits
    - Provide context pruning strategies when limits are approached

    Context management flow:
    1. Client adds messages to context
    2. Manager counts tokens and validates against limits
    3. Manager applies pruning strategy if needed
    4. Provider uses validated context for requests
    """

    def count_tokens(self, content: str | List[Message]) -> int:
        """Count tokens in content or message list.

        Args:
            content: String content or list of Message objects.

        Returns:
            int: Token count for the content.

        Raises:
            ValueError: If content cannot be tokenized.
        """
        ...

    def get_context_limit(self, model: str) -> int:
        """Get the maximum context window size for a model.

        Args:
            model: Model identifier.

        Returns:
            int: Maximum tokens allowed in context window.

        Raises:
            ValueError: If model is not recognized.
        """
        ...

    def validate_context(
        self,
        messages: List[Message],
        model: str,
        max_completion_tokens: Optional[int] = None,
    ) -> bool:
        """Validate that messages fit within model context limits.

        Args:
            messages: List of Message objects to validate.
            model: Target model identifier.
            max_completion_tokens: Optional reserved space for completion.

        Returns:
            bool: True if context is valid, False otherwise.
        """
        ...

    def prune_context(
        self,
        messages: List[Message],
        model: str,
        max_completion_tokens: Optional[int] = None,
        strategy: str = "oldest_first",
    ) -> List[Message]:
        """Prune messages to fit within context limits.

        Args:
            messages: List of Message objects to prune.
            model: Target model identifier.
            max_completion_tokens: Optional reserved space for completion.
            strategy: Pruning strategy ("oldest_first", "summarize", "sliding_window").

        Returns:
            List[Message]: Pruned message list that fits in context.

        Raises:
            ValueError: If messages cannot be pruned to fit.
        """
        ...


__all__ = ["IContextManager"]
