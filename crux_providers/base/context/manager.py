"""Base implementation of IContextManager for token counting and context management.

This module provides a default implementation that uses tiktoken for OpenAI-style
tokenization and manages conversation context within model limits.
"""

from __future__ import annotations

from typing import List, Optional

try:
    import tiktoken  # type: ignore
except ImportError:  # pragma: no cover
    tiktoken = None  # type: ignore

from ..interfaces import IContextManager
from ..models import Message
from ..logging import get_logger


# Model context limits (in tokens)
MODEL_CONTEXT_LIMITS = {
    # OpenAI models
    "gpt-4": 8192,
    "gpt-4-32k": 32768,
    "gpt-4-turbo": 128000,
    "gpt-4o": 128000,
    "gpt-4o-mini": 128000,
    "o1": 200000,
    "o1-mini": 128000,
    "o3": 200000,
    "o3-mini": 200000,
    "gpt-3.5-turbo": 16385,
    "gpt-3.5-turbo-16k": 16385,
    # Anthropic models
    "claude-3-opus": 200000,
    "claude-3-sonnet": 200000,
    "claude-3-haiku": 200000,
    "claude-3-5-sonnet": 200000,
    "claude-3-5-haiku": 200000,
    # Gemini models
    "gemini-1.5-pro": 2000000,
    "gemini-1.5-flash": 1000000,
    "gemini-1.0-pro": 32760,
}

# Default encoding for models
DEFAULT_ENCODING = "cl100k_base"  # Used by GPT-4, GPT-3.5-turbo


class BaseContextManager:
    """Base implementation of context management with tiktoken support.

    This implementation provides:
    - Token counting using tiktoken (falls back to character estimation)
    - Context window validation
    - Message pruning strategies (oldest_first, sliding_window)

    Attributes:
        logger: Structured logger instance.
        encoding: Tiktoken encoding for tokenization.
    """

    def __init__(self, encoding_name: str = DEFAULT_ENCODING) -> None:
        """Initialize the context manager.

        Args:
            encoding_name: Tiktoken encoding name to use for tokenization.
        """
        self.logger = get_logger("context_manager")
        self.encoding = None
        if tiktoken:
            try:
                self.encoding = tiktoken.get_encoding(encoding_name)
            except Exception as e:  # pragma: no cover
                self.logger.warning(
                    "Failed to load tiktoken encoding",
                    extra={"encoding": encoding_name, "error": str(e)},
                )

    def count_tokens(self, content: str | List[Message]) -> int:
        """Count tokens in content or message list.

        Args:
            content: String content or list of Message objects.

        Returns:
            int: Token count for the content.

        Raises:
            ValueError: If content cannot be tokenized.
        """
        if isinstance(content, str):
            return self._count_string_tokens(content)

        # Count tokens for all messages
        total = 0
        for msg in content:
            # Add tokens for role overhead (~4 tokens)
            total += 4
            
            if isinstance(msg.content, str):
                total += self._count_string_tokens(msg.content)
            else:
                # Handle structured content parts
                for part in msg.content:
                    if hasattr(part, "text") and part.text:
                        total += self._count_string_tokens(part.text)
                    # Images/other content: rough estimate
                    if hasattr(part, "type") and part.type == "image":
                        total += 85  # Rough estimate for image tokens
        
        # Add overhead for message formatting
        total += 3  # Base overhead
        return total

    def _count_string_tokens(self, text: str) -> int:
        """Count tokens in a string using tiktoken or fallback.

        Args:
            text: String to tokenize.

        Returns:
            int: Token count.
        """
        if self.encoding:
            try:
                return len(self.encoding.encode(text))
            except Exception:  # pragma: no cover
                pass
        
        # Fallback: rough character-based estimate
        # Roughly 4 characters per token on average
        return len(text) // 4

    def get_context_limit(self, model: str) -> int:
        """Get the maximum context window size for a model.

        Args:
            model: Model identifier.

        Returns:
            int: Maximum tokens allowed in context window.

        Raises:
            ValueError: If model is not recognized.
        """
        # Try exact match first
        if model in MODEL_CONTEXT_LIMITS:
            return MODEL_CONTEXT_LIMITS[model]
        
        # Try partial match for model families
        model_lower = model.lower()
        for key in MODEL_CONTEXT_LIMITS:
            if key.lower() in model_lower:
                return MODEL_CONTEXT_LIMITS[key]
        
        # Default fallback for unknown models
        self.logger.warning(
            "Unknown model, using default context limit",
            extra={"model": model, "default_limit": 4096},
        )
        return 4096

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
        limit = self.get_context_limit(model)
        used = self.count_tokens(messages)
        reserved = max_completion_tokens or 0
        
        fits = (used + reserved) <= limit
        
        if not fits:
            self.logger.debug(
                "Context validation failed",
                extra={
                    "model": model,
                    "limit": limit,
                    "used": used,
                    "reserved": reserved,
                    "total": used + reserved,
                },
            )
        
        return fits

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
            strategy: Pruning strategy ("oldest_first", "sliding_window").

        Returns:
            List[Message]: Pruned message list that fits in context.

        Raises:
            ValueError: If messages cannot be pruned to fit.
        """
        if self.validate_context(messages, model, max_completion_tokens):
            return messages

        limit = self.get_context_limit(model)
        reserved = max_completion_tokens or 0
        available = limit - reserved

        if strategy == "oldest_first":
            return self._prune_oldest_first(messages, available)
        elif strategy == "sliding_window":
            return self._prune_sliding_window(messages, available)
        else:
            raise ValueError(f"Unknown pruning strategy: {strategy}")

    def _prune_oldest_first(
        self, messages: List[Message], available: int
    ) -> List[Message]:
        """Prune oldest messages first, keeping system messages.

        Args:
            messages: Messages to prune.
            available: Available token budget.

        Returns:
            List[Message]: Pruned messages.

        Raises:
            ValueError: If cannot fit even system message and last user message.
        """
        if not messages:
            return []

        # Separate system messages and conversation
        system_msgs = [m for m in messages if m.role == "system"]
        conv_msgs = [m for m in messages if m.role != "system"]

        # Always keep system messages
        result = system_msgs[:]
        current_tokens = self.count_tokens(result)

        # Add messages from the end, working backwards
        for msg in reversed(conv_msgs):
            msg_tokens = self.count_tokens([msg])
            if current_tokens + msg_tokens <= available:
                result.insert(len(system_msgs), msg)
                current_tokens += msg_tokens
            else:
                break

        if len(result) <= len(system_msgs):
            raise ValueError(
                "Cannot fit messages in context even after pruning"
            )

        return result

    def _prune_sliding_window(
        self, messages: List[Message], available: int
    ) -> List[Message]:
        """Keep most recent messages in a sliding window.

        Args:
            messages: Messages to prune.
            available: Available token budget.

        Returns:
            List[Message]: Pruned messages.
        """
        return self._prune_oldest_first(messages, available)


__all__ = ["BaseContextManager", "MODEL_CONTEXT_LIMITS"]
