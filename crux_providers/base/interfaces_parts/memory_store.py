"""IMemoryStore Protocol (single-class module).

Interface for memory and context management across conversations.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Protocol, runtime_checkable


@runtime_checkable
class IMemoryStore(Protocol):
    """Interface for persistent memory and context management.

    Implementations manage:
    - Conversation history storage and retrieval
    - Semantic memory (facts, relationships)
    - Episodic memory (past interactions)
    - Context window optimization
    """

    def store_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:  # pragma: no cover - interface
        """Store a message in the conversation history.
        
        Parameters
        ----------
        conversation_id:
            Unique identifier for the conversation.
        role:
            Message role (user, assistant, system, tool).
        content:
            Message content.
        metadata:
            Optional metadata (timestamps, tokens, etc.).
            
        Returns
        -------
        str
            Unique message identifier.
        """
        ...

    def retrieve_context(
        self,
        conversation_id: str,
        max_tokens: Optional[int] = None,
        max_messages: Optional[int] = None,
    ) -> List[Dict[str, Any]]:  # pragma: no cover - interface
        """Retrieve conversation context optimized for the request.
        
        Parameters
        ----------
        conversation_id:
            Unique identifier for the conversation.
        max_tokens:
            Optional token budget for context window.
        max_messages:
            Optional maximum number of messages to retrieve.
            
        Returns
        -------
        List[Dict[str, Any]]
            List of messages in chronological order.
        """
        ...

    def store_fact(
        self,
        conversation_id: str,
        fact: str,
        source: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:  # pragma: no cover - interface
        """Store a semantic fact extracted from conversation.
        
        Parameters
        ----------
        conversation_id:
            Conversation where the fact was learned.
        fact:
            The fact to store (e.g., "User prefers Python 3.9+").
        source:
            Optional source reference (message ID, external doc).
        metadata:
            Optional metadata (confidence, timestamp, etc.).
            
        Returns
        -------
        str
            Unique fact identifier.
        """
        ...

    def retrieve_relevant_facts(
        self,
        conversation_id: str,
        query: Optional[str] = None,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:  # pragma: no cover - interface
        """Retrieve facts relevant to the current query/context.
        
        Parameters
        ----------
        conversation_id:
            Conversation context.
        query:
            Optional query for semantic similarity search.
        limit:
            Maximum number of facts to return.
            
        Returns
        -------
        List[Dict[str, Any]]
            List of relevant facts with metadata.
        """
        ...

    def clear_conversation(self, conversation_id: str) -> None:  # pragma: no cover - interface
        """Clear all messages and facts for a conversation.
        
        Parameters
        ----------
        conversation_id:
            Conversation to clear.
        """
        ...
