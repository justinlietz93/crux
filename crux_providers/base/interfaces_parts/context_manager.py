"""IContextManager Protocol (single-class module).

Interface for context window management and optimization.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

from ..models import Message


@runtime_checkable
class IContextManager(Protocol):
    """Interface for context window management and optimization.

    Implementations handle:
    - Token counting and budget management
    - Message prioritization and pruning
    - Context compression strategies
    - Sliding window management
    """

    def count_tokens(
        self,
        messages: List[Message],
        model: Optional[str] = None,
    ) -> int:  # pragma: no cover - interface
        """Count tokens in a message list for a specific model.
        
        Parameters
        ----------
        messages:
            List of messages to count.
        model:
            Optional model identifier for model-specific tokenization.
            
        Returns
        -------
        int
            Estimated token count.
        """
        ...

    def fit_to_budget(
        self,
        messages: List[Message],
        token_budget: int,
        model: Optional[str] = None,
        strategy: str = "sliding_window",
    ) -> List[Message]:  # pragma: no cover - interface
        """Fit messages into a token budget using the specified strategy.
        
        Parameters
        ----------
        messages:
            Full list of messages.
        token_budget:
            Maximum tokens allowed.
        model:
            Model for tokenization.
        strategy:
            Strategy to use: 'sliding_window', 'priority', 'summarize'.
            
        Returns
        -------
        List[Message]
            Optimized message list fitting the budget.
        """
        ...

    def prioritize_messages(
        self,
        messages: List[Message],
        context: Optional[Dict[str, Any]] = None,
    ) -> List[Message]:  # pragma: no cover - interface
        """Assign priorities to messages based on importance.
        
        Parameters
        ----------
        messages:
            Messages to prioritize.
        context:
            Optional context for priority calculation (current task, etc.).
            
        Returns
        -------
        List[Message]
            Messages with priority scores in metadata.
        """
        ...

    def compress_context(
        self,
        messages: List[Message],
        target_reduction: float = 0.5,
        model: Optional[str] = None,
    ) -> List[Message]:  # pragma: no cover - interface
        """Compress context using summarization or other techniques.
        
        Parameters
        ----------
        messages:
            Messages to compress.
        target_reduction:
            Target compression ratio (0.5 = reduce to 50% of original).
        model:
            Model for summarization if applicable.
            
        Returns
        -------
        List[Message]
            Compressed message list.
        """
        ...
