"""Tests for InMemoryStore."""

from __future__ import annotations

import pytest
from crux_providers.base.memory.in_memory_store import InMemoryStore


def test_store_and_retrieve_messages():
    """Test: Store messages and retrieve conversation context."""
    store = InMemoryStore()
    conv_id = "test_conv"
    
    # Store messages
    msg_id_1 = store.store_message(conv_id, "user", "Hello")
    msg_id_2 = store.store_message(conv_id, "assistant", "Hi there!")
    
    assert msg_id_1 != msg_id_2
    
    # Retrieve context
    context = store.retrieve_context(conv_id)
    assert len(context) == 2
    assert context[0]["role"] == "user"
    assert context[0]["content"] == "Hello"
    assert context[1]["role"] == "assistant"
    assert context[1]["content"] == "Hi there!"


def test_retrieve_with_message_limit():
    """Test: Retrieve context with message limit."""
    store = InMemoryStore()
    conv_id = "test_conv"
    
    # Store 5 messages
    for i in range(5):
        store.store_message(conv_id, "user", f"Message {i}")
    
    # Retrieve last 3 messages
    context = store.retrieve_context(conv_id, max_messages=3)
    assert len(context) == 3
    assert context[0]["content"] == "Message 2"
    assert context[2]["content"] == "Message 4"


def test_retrieve_with_token_limit():
    """Test: Retrieve context with token budget."""
    store = InMemoryStore()
    conv_id = "test_conv"
    
    # Store messages of different lengths
    store.store_message(conv_id, "user", "x" * 100)  # ~25 tokens
    store.store_message(conv_id, "user", "x" * 200)  # ~50 tokens
    store.store_message(conv_id, "user", "x" * 400)  # ~100 tokens
    
    # Retrieve with 60 token budget (should get last message only)
    context = store.retrieve_context(conv_id, max_tokens=60)
    assert len(context) == 1
    assert len(context[0]["content"]) == 200


def test_store_and_retrieve_facts():
    """Test: Store and retrieve semantic facts."""
    store = InMemoryStore()
    conv_id = "test_conv"
    
    # Store facts
    fact_id = store.store_fact(
        conv_id,
        "User prefers Python 3.9+",
        source="msg_123",
        metadata={"confidence": 0.9}
    )
    
    assert fact_id is not None
    
    # Retrieve facts
    facts = store.retrieve_relevant_facts(conv_id)
    assert len(facts) == 1
    assert facts[0]["fact"] == "User prefers Python 3.9+"
    assert facts[0]["metadata"]["confidence"] == 0.9


def test_retrieve_facts_with_query():
    """Test: Retrieve facts with keyword query."""
    store = InMemoryStore()
    conv_id = "test_conv"
    
    store.store_fact(conv_id, "User prefers Python")
    store.store_fact(conv_id, "User likes JavaScript")
    store.store_fact(conv_id, "Favorite color is blue")
    
    # Query for Python
    facts = store.retrieve_relevant_facts(conv_id, query="Python")
    assert len(facts) == 1
    assert "Python" in facts[0]["fact"]


def test_clear_conversation():
    """Test: Clear all conversation data."""
    store = InMemoryStore()
    conv_id = "test_conv"
    
    store.store_message(conv_id, "user", "Hello")
    store.store_fact(conv_id, "Some fact")
    
    # Verify data exists
    assert len(store.retrieve_context(conv_id)) == 1
    assert len(store.retrieve_relevant_facts(conv_id)) == 1
    
    # Clear conversation
    store.clear_conversation(conv_id)
    
    # Verify data is gone
    assert len(store.retrieve_context(conv_id)) == 0
    assert len(store.retrieve_relevant_facts(conv_id)) == 0


def test_list_conversations():
    """Test: List all conversation IDs."""
    store = InMemoryStore()
    
    store.store_message("conv1", "user", "Hello")
    store.store_message("conv2", "user", "Hi")
    
    conversations = store.list_conversations()
    assert len(conversations) == 2
    assert "conv1" in conversations
    assert "conv2" in conversations


def test_conversation_stats():
    """Test: Get conversation statistics."""
    store = InMemoryStore()
    conv_id = "test_conv"
    
    store.store_message(conv_id, "user", "Hello")
    store.store_message(conv_id, "assistant", "Hi")
    store.store_fact(conv_id, "Some fact")
    
    stats = store.get_conversation_stats(conv_id)
    assert stats["message_count"] == 2
    assert stats["fact_count"] == 1
    assert stats["exists"] is True
    
    # Stats for non-existent conversation
    stats = store.get_conversation_stats("nonexistent")
    assert stats["message_count"] == 0
    assert stats["exists"] is False


def test_empty_conversation():
    """Test: Retrieve from non-existent conversation."""
    store = InMemoryStore()
    
    context = store.retrieve_context("nonexistent")
    assert len(context) == 0
    
    facts = store.retrieve_relevant_facts("nonexistent")
    assert len(facts) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
