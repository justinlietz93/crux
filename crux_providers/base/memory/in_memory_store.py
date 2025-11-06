"""In-memory implementation of IMemoryStore.

Simple reference implementation for memory management using Python dictionaries.
Suitable for development, testing, and single-process applications.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from datetime import datetime, timezone
from uuid import uuid4

from ..interfaces import IMemoryStore


class InMemoryStore:
    """In-memory implementation of memory store.
    
    This is a reference implementation suitable for development and testing.
    For production, consider using SqliteMemoryStore or an external database.
    
    Thread safety: Not thread-safe. Use locks if accessing from multiple threads.
    """

    def __init__(self) -> None:
        """Initialize the in-memory store."""
        self._conversations: Dict[str, List[Dict[str, Any]]] = {}
        self._facts: Dict[str, List[Dict[str, Any]]] = {}

    def store_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
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
        if conversation_id not in self._conversations:
            self._conversations[conversation_id] = []

        message_id = str(uuid4())
        message = {
            "id": message_id,
            "role": role,
            "content": content,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "metadata": metadata or {},
        }
        
        self._conversations[conversation_id].append(message)
        return message_id

    def retrieve_context(
        self,
        conversation_id: str,
        max_tokens: Optional[int] = None,
        max_messages: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Retrieve conversation context optimized for the request.
        
        Parameters
        ----------
        conversation_id:
            Unique identifier for the conversation.
        max_tokens:
            Optional token budget for context window (simplified estimate).
        max_messages:
            Optional maximum number of messages to retrieve.
            
        Returns
        -------
        List[Dict[str, Any]]
            List of messages in chronological order.
        """
        if conversation_id not in self._conversations:
            return []

        messages = self._conversations[conversation_id]
        
        # Apply message limit
        if max_messages is not None:
            messages = messages[-max_messages:]
        
        # Simple token estimation (4 chars ≈ 1 token)
        if max_tokens is not None:
            result = []
            token_count = 0
            # Process messages from most recent backwards
            for msg in reversed(messages):
                msg_tokens = len(msg["content"]) // 4
                # Add message if it fits in budget
                if token_count + msg_tokens <= max_tokens:
                    result.insert(0, msg)
                    token_count += msg_tokens
            return result
        
        return messages

    def store_fact(
        self,
        conversation_id: str,
        fact: str,
        source: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
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
        if conversation_id not in self._facts:
            self._facts[conversation_id] = []

        fact_id = str(uuid4())
        fact_entry = {
            "id": fact_id,
            "fact": fact,
            "source": source,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "metadata": metadata or {},
        }
        
        self._facts[conversation_id].append(fact_entry)
        return fact_id

    def retrieve_relevant_facts(
        self,
        conversation_id: str,
        query: Optional[str] = None,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """Retrieve facts relevant to the current query/context.
        
        Parameters
        ----------
        conversation_id:
            Conversation context.
        query:
            Optional query for semantic similarity search (simple keyword match).
        limit:
            Maximum number of facts to return.
            
        Returns
        -------
        List[Dict[str, Any]]
            List of relevant facts with metadata.
        """
        if conversation_id not in self._facts:
            return []

        facts = self._facts[conversation_id]
        
        # Simple keyword-based relevance (for production use embedding similarity)
        if query:
            query_lower = query.lower()
            relevant = [
                f for f in facts 
                if any(word in f["fact"].lower() for word in query_lower.split())
            ]
        else:
            relevant = facts
        
        # Return most recent facts up to limit
        return relevant[-limit:]

    def clear_conversation(self, conversation_id: str) -> None:
        """Clear all messages and facts for a conversation.
        
        Parameters
        ----------
        conversation_id:
            Conversation to clear.
        """
        if conversation_id in self._conversations:
            del self._conversations[conversation_id]
        if conversation_id in self._facts:
            del self._facts[conversation_id]

    def list_conversations(self) -> List[str]:
        """List all conversation IDs.
        
        Returns
        -------
        List[str]
            List of conversation identifiers.
        """
        return list(self._conversations.keys())

    def get_conversation_stats(self, conversation_id: str) -> Dict[str, Any]:
        """Get statistics for a conversation.
        
        Parameters
        ----------
        conversation_id:
            Conversation to analyze.
            
        Returns
        -------
        Dict[str, Any]
            Statistics including message count, fact count, etc.
        """
        return {
            "message_count": len(self._conversations.get(conversation_id, [])),
            "fact_count": len(self._facts.get(conversation_id, [])),
            "exists": conversation_id in self._conversations,
        }


__all__ = ["InMemoryStore"]
