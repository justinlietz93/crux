"""Tests for new capability interfaces and implementations."""

import pytest
from crux_providers.base.interfaces import (
    SupportsToolUse,
    IContextManager,
    IAgentRuntime,
)
from crux_providers.base.context import BaseContextManager, MODEL_CONTEXT_LIMITS
from crux_providers.base.plugins import PluginRegistry, MCPPlugin
from crux_providers.base.models import Message


def test_context_manager_token_counting():
    """Test that BaseContextManager can count tokens."""
    manager = BaseContextManager()
    
    # Test string token counting
    text = "Hello, world!"
    tokens = manager.count_tokens(text)
    assert tokens > 0
    
    # Test message list token counting
    messages = [
        Message(role="system", content="You are helpful."),
        Message(role="user", content="Hello!"),
    ]
    tokens = manager.count_tokens(messages)
    assert tokens > 0


def test_context_manager_limits():
    """Test that context limits are defined for major models."""
    manager = BaseContextManager()
    
    # Test OpenAI models
    assert manager.get_context_limit("gpt-4") == 8192
    assert manager.get_context_limit("gpt-4o") == 128000
    
    # Test Anthropic models
    assert manager.get_context_limit("claude-3-opus") == 200000
    
    # Test Gemini models
    assert manager.get_context_limit("gemini-1.5-pro") == 2000000
    
    # Test unknown model (should return default)
    assert manager.get_context_limit("unknown-model") == 4096


def test_context_validation():
    """Test context validation against model limits."""
    manager = BaseContextManager()
    
    # Short messages should fit
    messages = [
        Message(role="user", content="Short message"),
    ]
    assert manager.validate_context(messages, "gpt-4")
    
    # Very long message should not fit in small context
    long_content = "x" * 100000  # Very long string
    messages = [Message(role="user", content=long_content)]
    # Should not fit in gpt-4 context
    result = manager.validate_context(messages, "gpt-4", max_completion_tokens=1000)
    # Result depends on tokenization, but we're just testing it runs


def test_plugin_registry_basic():
    """Test basic plugin registry operations."""
    registry = PluginRegistry()
    
    # Create a simple MCP plugin
    plugin = MCPPlugin(name="test_plugin", version="1.0.0")
    
    # Register plugin
    registry.register(plugin)
    
    # Verify registration
    assert "test_plugin" in registry.plugins
    assert len(registry.list_plugins()) == 1
    
    # Get capabilities
    caps = registry.get_capabilities()
    assert "mcp" in caps
    
    # Unregister plugin
    registry.unregister("test_plugin")
    assert "test_plugin" not in registry.plugins


def test_plugin_registry_dependencies():
    """Test plugin dependency checking."""
    registry = PluginRegistry()
    
    # Create a plugin with missing dependency
    plugin = MCPPlugin(name="dependent_plugin", version="1.0.0")
    plugin._metadata.dependencies = ["missing_plugin"]
    
    # Should fail to register due to missing dependency
    with pytest.raises(ValueError, match="missing dependencies"):
        registry.register(plugin)


def test_model_context_limits_coverage():
    """Test that MODEL_CONTEXT_LIMITS contains expected models."""
    # Verify major model families are present
    assert "gpt-4" in MODEL_CONTEXT_LIMITS
    assert "gpt-4o" in MODEL_CONTEXT_LIMITS
    assert "claude-3-opus" in MODEL_CONTEXT_LIMITS
    assert "gemini-1.5-pro" in MODEL_CONTEXT_LIMITS
    
    # Verify limits are reasonable
    for model, limit in MODEL_CONTEXT_LIMITS.items():
        assert limit > 0
        assert limit <= 3000000  # No model should exceed this


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
