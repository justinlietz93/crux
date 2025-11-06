"""Tests for universal provider router."""

from __future__ import annotations

import pytest
from unittest.mock import Mock

from crux_providers.base.routing.router import ProviderRouter
from crux_providers.base.models import ChatRequest, ChatResponse, Message, ProviderMetadata
from crux_providers.base.errors import ProviderError, ErrorCode


def test_router_registers_provider():
    """Test: Router registers a provider and detects capabilities."""
    router = ProviderRouter()
    mock_provider = Mock()
    mock_provider.provider_name = "test"
    mock_provider.chat.return_value = ChatResponse(
        text="Hello",
        parts=None,
        raw=None,
        meta=ProviderMetadata(provider_name="test", model_name="test-model", extra={}),
    )
    
    router.register_provider("test", mock_provider, priority=10)
    
    providers = router.list_providers()
    assert len(providers) == 1
    assert providers[0]["id"] == "test"
    assert providers[0]["priority"] == 10


def test_router_selects_by_capability():
    """Test: Router selects provider based on required capabilities."""
    router = ProviderRouter()
    
    # Provider without streaming
    basic_provider = Mock()
    basic_provider.provider_name = "basic"
    
    # Provider with streaming
    streaming_provider = Mock()
    streaming_provider.provider_name = "streaming"
    streaming_provider.supports_streaming.return_value = True
    
    router.register_provider(
        "basic",
        basic_provider,
        capabilities=frozenset(),
    )
    router.register_provider(
        "streaming",
        streaming_provider,
        capabilities=frozenset(["streaming"]),
    )
    
    # Should only return streaming provider
    providers = router.list_providers(capability_filter=["streaming"])
    assert len(providers) == 1
    assert providers[0]["id"] == "streaming"


def test_router_fallback_chain():
    """Test: Router tries fallback providers on failure."""
    router = ProviderRouter()
    
    primary_provider = Mock()
    primary_provider.provider_name = "primary"
    primary_provider.chat.side_effect = Exception("Primary failed")
    
    fallback_provider = Mock()
    fallback_provider.provider_name = "fallback"
    fallback_provider.chat.return_value = ChatResponse(
        text="Fallback success",
        parts=None,
        raw=None,
        meta=ProviderMetadata(provider_name="fallback", model_name="test", extra={}),
    )
    
    router.register_provider("primary", primary_provider)
    router.register_provider("fallback", fallback_provider)
    router.set_fallback_chain("primary", ["fallback"])
    
    request = ChatRequest(
        model="test",
        messages=[Message(role="user", content="Hello")],
    )
    
    response = router.chat(request, preferred_provider="primary")
    assert response.text == "Fallback success"
    assert primary_provider.chat.called
    assert fallback_provider.chat.called


def test_router_priority_ordering():
    """Test: Router respects provider priority."""
    router = ProviderRouter()
    
    low_priority = Mock()
    low_priority.provider_name = "low"
    low_priority.chat.return_value = ChatResponse(
        text="Low priority",
        parts=None,
        raw=None,
        meta=ProviderMetadata(provider_name="low", model_name="test", extra={}),
    )
    
    high_priority = Mock()
    high_priority.provider_name = "high"
    high_priority.chat.return_value = ChatResponse(
        text="High priority",
        parts=None,
        raw=None,
        meta=ProviderMetadata(provider_name="high", model_name="test", extra={}),
    )
    
    router.register_provider("low", low_priority, priority=1)
    router.register_provider("high", high_priority, priority=10)
    
    request = ChatRequest(
        model="test",
        messages=[Message(role="user", content="Hello")],
    )
    
    response = router.chat(request)
    assert response.text == "High priority"
    assert high_priority.chat.called
    assert not low_priority.chat.called


def test_router_cost_optimization():
    """Test: Router can optimize for cost."""
    router = ProviderRouter()
    
    expensive = Mock()
    expensive.provider_name = "expensive"
    expensive.chat.return_value = ChatResponse(
        text="Expensive",
        parts=None,
        raw=None,
        meta=ProviderMetadata(provider_name="expensive", model_name="test", extra={}),
    )
    
    cheap = Mock()
    cheap.provider_name = "cheap"
    cheap.chat.return_value = ChatResponse(
        text="Cheap",
        parts=None,
        raw=None,
        meta=ProviderMetadata(provider_name="cheap", model_name="test", extra={}),
    )
    
    router.register_provider("expensive", expensive, cost_per_1k_tokens=10.0)
    router.register_provider("cheap", cheap, cost_per_1k_tokens=1.0)
    
    request = ChatRequest(
        model="test",
        messages=[Message(role="user", content="Hello")],
    )
    
    response = router.chat(request, optimize_for="cost")
    assert response.text == "Cheap"
    assert cheap.chat.called
    assert not expensive.chat.called


def test_router_no_providers_raises():
    """Test: Router raises when no providers meet requirements."""
    router = ProviderRouter()
    
    basic_provider = Mock()
    basic_provider.provider_name = "basic"
    router.register_provider("basic", basic_provider, capabilities=frozenset())
    
    request = ChatRequest(
        model="test",
        messages=[Message(role="user", content="Hello")],
    )
    
    with pytest.raises(ProviderError) as exc_info:
        router.chat(request, required_capabilities=["streaming"])
    
    assert "failed" in str(exc_info.value).lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
