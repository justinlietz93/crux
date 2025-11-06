# Universal Provider Framework Documentation

## Overview

The Universal Provider Framework extends Crux Providers with a capability-based routing system that enables selective SDK feature usage, intelligent provider selection, and extensible plugin architecture.

## Core Concepts

### 1. Capability-Based Interfaces

The framework defines standard interfaces for common LLM capabilities:

#### SupportsToolUse
Enables function/tool calling across providers with a unified interface:
```python
from crux_providers.base.interfaces import SupportsToolUse

if isinstance(provider, SupportsToolUse) and provider.supports_tool_use():
    response = provider.execute_with_tools(request, tools=my_tools)
```

#### IMemoryStore
Manages conversation history and semantic memory:
```python
from crux_providers.base.interfaces import IMemoryStore

memory = SqliteMemoryStore()
memory.store_message(conv_id, role="user", content="Hello")
context = memory.retrieve_context(conv_id, max_tokens=4000)
```

#### IContextManager
Optimizes context window usage:
```python
from crux_providers.base.interfaces import IContextManager

ctx_mgr = ContextManager(model="gpt-4o")
tokens = ctx_mgr.count_tokens(messages)
optimized = ctx_mgr.fit_to_budget(messages, token_budget=4000)
```

#### IAgentRuntime
Orchestrates multi-step agent execution:
```python
from crux_providers.base.interfaces import IAgentRuntime

agent = AgentRuntime(provider, memory_store)
agent.register_tool_executor("search", search_tool)
response = agent.execute_agent_loop(request, tools=available_tools)
```

#### IPluginRegistry
Manages extensible plugin lifecycle:
```python
from crux_providers.base.interfaces import IPluginRegistry

registry = PluginRegistry()
registry.register_plugin("analytics", AnalyticsPlugin, config={...})
registry.enable_plugin("analytics")
```

### 2. Universal Provider Router

The `ProviderRouter` intelligently routes requests based on capabilities, cost, and priorities:

```python
from crux_providers.base.routing.router import ProviderRouter
from crux_providers.base import ProviderFactory

# Initialize router
router = ProviderRouter()

# Register providers with priorities and costs
router.register_provider(
    "openai",
    ProviderFactory.create("openai"),
    priority=10,
    cost_per_1k_tokens=0.02
)

router.register_provider(
    "anthropic",
    ProviderFactory.create("anthropic"),
    priority=9,
    cost_per_1k_tokens=0.015
)

# Configure fallback chains
router.set_fallback_chain("openai", ["anthropic", "gemini"])

# Route based on capabilities
response = router.chat(
    request,
    required_capabilities=["streaming", "tool_use"],
    optimize_for="cost"
)
```

## Routing Strategies

### Capability-Based Routing

Route to providers that support specific capabilities:

```python
# Only use providers with streaming support
response = router.stream_chat(
    request,
    required_capabilities=["streaming"]
)

# Only use providers with tool use support
response = router.execute_with_tools(
    request,
    tools=my_tools,
    required_capabilities=["tool_use", "json_output"]
)
```

### Priority-Based Routing

Higher priority providers are tried first:

```python
router.register_provider("primary", primary_provider, priority=10)
router.register_provider("backup", backup_provider, priority=5)

# Will try primary_provider first
response = router.chat(request)
```

### Cost Optimization

Minimize costs by routing to cheaper providers:

```python
response = router.chat(
    request,
    optimize_for="cost"  # Selects cheapest provider meeting requirements
)
```

### Fallback Chains

Automatic fallback to alternative providers on failure:

```python
# Configure fallback: openai → anthropic → gemini
router.set_fallback_chain("openai", ["anthropic", "gemini"])

# If openai fails, automatically tries anthropic, then gemini
response = router.chat(request, preferred_provider="openai")
```

## Feature Comparison Matrix

| Feature | OpenAI | Anthropic | Gemini | Ollama | Deepseek | XAI | OpenRouter |
|---------|--------|-----------|--------|--------|----------|-----|------------|
| Chat | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Streaming | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Tool Use | ✅* | ✅* | ✅* | ⚠️ | ✅* | ✅* | ✅* |
| JSON Output | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Vision | ✅ | ✅ | ✅ | ⚠️ | ❌ | ⚠️ | ✅ |

*✅ = Fully supported
*⚠️ = Partial support or model-dependent
*❌ = Not supported
*\* = Requires implementation

## Advanced Usage

### Selective Capability Routing

Route different parts of your application to different providers:

```python
# Use OpenAI for tool-heavy tasks
tool_router = ProviderRouter()
tool_router.register_provider("openai", openai_provider)
tool_response = tool_router.execute_with_tools(request, tools)

# Use Anthropic for general chat
chat_router = ProviderRouter()
chat_router.register_provider("anthropic", anthropic_provider)
chat_response = chat_router.chat(request)
```

### Multi-Provider Ensemble

Use multiple providers and aggregate results:

```python
results = []
for provider_id in ["openai", "anthropic", "gemini"]:
    provider = router._providers[provider_id]["provider"]
    try:
        response = provider.chat(request)
        results.append(response)
    except Exception:
        continue

# Aggregate or select best response
best_response = select_best(results)
```

### Custom Routing Logic

Extend the router for custom routing strategies:

```python
class CustomRouter(ProviderRouter):
    def route_by_model_size(self, request, prefer_large=True):
        # Custom logic to route based on model size
        candidates = self._select_candidates()
        # ... custom selection logic
        return self.chat(request, preferred_provider=selected)
```

## Integration with Existing Code

The framework is designed for seamless integration:

### Backward Compatibility

All existing code continues to work:

```python
# Old way still works
provider = ProviderFactory.create("openai")
response = provider.chat(request)

# New way adds capabilities
router = ProviderRouter()
router.register_provider("openai", provider)
response = router.chat(request, required_capabilities=["streaming"])
```

### Gradual Migration

Migrate incrementally by routing only new features:

```python
# Legacy code paths
if use_legacy:
    response = legacy_provider.chat(request)
else:
    # New router for new features
    response = router.chat(request, required_capabilities=["tool_use"])
```

## Performance Considerations

### Provider Registration Overhead

Provider registration is lightweight (O(1)):
- No network calls during registration
- Capability detection is fast (isinstance checks)
- Minimal memory overhead per provider

### Routing Overhead

Routing adds minimal latency:
- Candidate selection: O(n) where n = number of providers
- Typical: <1ms for 10 providers
- No network calls until execution

### Fallback Performance

Fallback chains execute serially:
- Each provider attempt includes full request timeout
- Configure timeouts appropriately for your use case
- Consider async execution for parallel fallback attempts

## Testing

The framework includes comprehensive tests:

```bash
# Run router tests
pytest crux_providers/tests/base/test_router.py -v

# Run all interface tests
pytest crux_providers/tests/base/ -v
```

## Future Enhancements

Planned features:
- [ ] Async provider execution for parallel fallback
- [ ] Provider health monitoring and circuit breakers
- [ ] Request/response caching layer
- [ ] Provider cost tracking and budgeting
- [ ] A/B testing framework for provider comparison
- [ ] Streaming with tool use
- [ ] MCP (Model Context Protocol) integration
- [ ] Plugin marketplace and discovery

## Architecture Alignment

This framework aligns with clean architecture principles:

1. **Interfaces First**: All capabilities defined as protocols
2. **Dependency Inversion**: Providers implement interfaces
3. **Single Responsibility**: Each interface has one concern
4. **Open/Closed**: Extensible via plugins without modification
5. **File Size Compliance**: All files under 500 LOC

## Best Practices

### 1. Register All Available Providers

```python
# Register all providers upfront for full routing flexibility
for name in ["openai", "anthropic", "gemini", "ollama"]:
    try:
        provider = ProviderFactory.create(name)
        router.register_provider(name, provider)
    except Exception as e:
        logger.warning(f"Failed to register {name}: {e}")
```

### 2. Configure Appropriate Fallbacks

```python
# Set fallbacks based on capability similarity
router.set_fallback_chain("openai", ["deepseek", "xai"])  # OpenAI-compatible
router.set_fallback_chain("anthropic", ["gemini"])  # Similar capabilities
```

### 3. Use Specific Capability Requirements

```python
# Be specific about what you need
response = router.chat(
    request,
    required_capabilities=["streaming", "json_output"],  # Not just ["streaming"]
    optimize_for="cost"
)
```

### 4. Handle Router Exceptions

```python
from crux_providers.base.errors import ProviderError

try:
    response = router.chat(request, required_capabilities=["tool_use"])
except ProviderError as e:
    logger.error(f"Routing failed: {e}")
    # Fallback to direct provider or error response
```

## Support

For issues or questions:
- Check existing tests for examples
- Review interface docstrings
- File issues on GitHub

## License

Same as Crux Providers (MIT)
