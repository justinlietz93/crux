# Universal LLM Provider Framework - Complete Guide

## Overview

The Crux Provider Framework is now a **truly universal LLM abstraction layer** that enables you to:

- **Route any provider model** through a single simplified contract
- **Selectively enable/disable capabilities** (streaming, tools, JSON, etc.) per provider
- **Build tool-augmented agents** with multi-step orchestration
- **Manage conversation context** with automatic token counting and pruning
- **Extend functionality** with plugins and MCP (Model Context Protocol) support

## Architecture

The framework follows **Clean Architecture** principles with clear separation of concerns:

```
┌─────────────────────────────────────────────────────────┐
│  Presentation Layer (Your Application)                 │
│  - Uses provider-agnostic interfaces                   │
│  - Depends on abstractions, not implementations        │
└─────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────┐
│  Application Layer (Business Logic)                    │
│  - Agent Runtime (IAgentRuntime)                       │
│  - Context Manager (IContextManager)                   │
│  - Plugin Registry                                      │
└─────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────┐
│  Domain Layer (Core Models)                            │
│  - ChatRequest / ChatResponse                          │
│  - Message / ContentPart                               │
│  - ToolResultDTO                                       │
└─────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────┐
│  Infrastructure Layer (Provider Adapters)               │
│  - OpenAI, Anthropic, Gemini, Ollama, etc.            │
│  - Implement: LLMProvider, SupportsToolUse, etc.       │
└─────────────────────────────────────────────────────────┘
```

## Core Capabilities

### 1. Tool Use (Function Calling)

The `SupportsToolUse` interface enables providers to execute tools/functions:

```python
from crux_providers.base import ProviderFactory, ChatRequest, Message

# Check if provider supports tools
provider = ProviderFactory.create("openai")
supports_tools = isinstance(provider, SupportsToolUse)

# Define tools
tools = [
    {
        "name": "get_weather",
        "description": "Get weather for a location",
        "parameters": {
            "type": "object",
            "properties": {
                "location": {"type": "string"}
            }
        }
    }
]

# Make request with tools
request = ChatRequest(
    model="gpt-4",
    messages=[Message(role="user", content="What's the weather in NYC?")],
    tools=tools
)

if supports_tools:
    response = provider.chat_with_tools(request)
else:
    response = provider.chat(request)
```

### 2. Context Management

The `BaseContextManager` provides token counting and context window management:

```python
from crux_providers.base.context import BaseContextManager
from crux_providers.base.models import Message

manager = BaseContextManager()

# Count tokens
messages = [
    Message(role="system", content="You are helpful."),
    Message(role="user", content="Hello!")
]
token_count = manager.count_tokens(messages)
print(f"Messages use {token_count} tokens")

# Get model limits
limit = manager.get_context_limit("gpt-4")
print(f"GPT-4 context limit: {limit} tokens")

# Validate context fits
is_valid = manager.validate_context(
    messages, 
    model="gpt-4",
    max_completion_tokens=1000
)

# Prune if needed
if not is_valid:
    messages = manager.prune_context(
        messages,
        model="gpt-4",
        strategy="oldest_first"
    )
```

**Supported Models:**
- OpenAI: GPT-4, GPT-4o, O1, O3, GPT-3.5-turbo
- Anthropic: Claude 3 Opus/Sonnet/Haiku, Claude 3.5
- Gemini: 1.5 Pro/Flash, 1.0 Pro

### 3. Agent Runtime (Multi-Step Orchestration)

The `BaseAgentRuntime` coordinates LLM interactions with tool execution:

```python
from crux_providers.base.agent import BaseAgentRuntime
from crux_providers.base import ProviderFactory

# Create provider and runtime
provider = ProviderFactory.create("openai")
runtime = BaseAgentRuntime(provider)

# Register tools
def get_weather(params):
    location = params.get("location", "")
    return f"Weather in {location}: Sunny, 72°F"

runtime.register_tool("get_weather", get_weather)

# Define tool specification
tools = [{
    "name": "get_weather",
    "description": "Get weather for a location",
    "parameters": {
        "type": "object",
        "properties": {
            "location": {"type": "string", "description": "City name"}
        },
        "required": ["location"]
    }
}]

# Execute agent task
response = runtime.execute(
    goal="What's the weather in Paris?",
    tools=tools,
    max_iterations=10
)
print(response.text)

# Or stream progress
for event in runtime.execute_streaming(
    goal="What's the weather in Paris?",
    tools=tools
):
    print(f"{event['type']}: {event['content']}")
```

### 4. Plugin System

The plugin system enables extensible functionality:

```python
from crux_providers.base.plugins import PluginRegistry, MCPPlugin

# Create registry
registry = PluginRegistry()

# Create custom MCP plugin
class CustomContextPlugin(MCPPlugin):
    def __init__(self):
        super().__init__(
            name="custom_context",
            version="1.0.0",
            capabilities=["mcp", "context_query"]
        )
    
    def query_context(self, query: str):
        # Your implementation
        return {"result": "context data"}
    
    def update_context(self, data):
        # Your implementation
        return True

# Register plugin
plugin = CustomContextPlugin()
registry.register(plugin)

# Query by capability
context_plugins = registry.find_by_capability("context_query")

# Use plugin
result = plugin.query_context("user preferences")
```

## Capability Detection

The framework automatically detects provider capabilities:

```python
from crux_providers.base.capabilities import detect_capabilities

provider = ProviderFactory.create("openai")
caps = detect_capabilities(provider)

# Check for specific capabilities
from crux_providers.base.capabilities import (
    CAP_STREAMING,
    CAP_JSON,
    CAP_TOOL_USE,
    CAP_CONTEXT_MANAGEMENT,
    CAP_AGENT_RUNTIME
)

if CAP_STREAMING in caps:
    print("Provider supports streaming")

if CAP_TOOL_USE in caps:
    print("Provider supports tool use")
```

## Building a Complete Agent

Here's a complete example combining all features:

```python
from crux_providers.base import ProviderFactory, ChatRequest, Message
from crux_providers.base.context import BaseContextManager
from crux_providers.base.agent import BaseAgentRuntime

# Setup
provider = ProviderFactory.create("openai")
context_manager = BaseContextManager()
runtime = BaseAgentRuntime(provider)

# Register tools
def calculate(params):
    expr = params.get("expression", "")
    try:
        result = eval(expr)  # In production, use safe evaluation
        return f"Result: {result}"
    except Exception as e:
        return f"Error: {e}"

runtime.register_tool("calculate", calculate)

# Define available tools
tools = [{
    "name": "calculate",
    "description": "Evaluate a mathematical expression",
    "parameters": {
        "type": "object",
        "properties": {
            "expression": {"type": "string"}
        },
        "required": ["expression"]
    }
}]

# Build conversation with context management
messages = [
    Message(role="system", content="You are a helpful math assistant."),
    Message(role="user", content="What is 25 * 37?")
]

# Validate context
if not context_manager.validate_context(messages, "gpt-4"):
    messages = context_manager.prune_context(messages, "gpt-4")

# Execute with agent
response = runtime.execute(
    goal="What is 25 * 37?",
    tools=tools,
    context=messages,
    max_iterations=5
)

print(f"Agent response: {response.text}")
print(f"Total tokens used: {context_manager.count_tokens(runtime.get_conversation_history())}")
```

## Provider-Specific Tool Implementations

To add tool support to a provider, implement the `SupportsToolUse` interface:

```python
from crux_providers.base.interfaces import LLMProvider, SupportsToolUse

class MyProvider(LLMProvider, SupportsToolUse):
    def supports_tool_use(self) -> bool:
        return True
    
    def chat_with_tools(self, request, available_tools=None):
        # Map request.tools to provider SDK format
        # Execute provider API call
        # Parse tool calls from response
        # Return ChatResponse
        pass
    
    def stream_chat_with_tools(self, request, available_tools=None):
        # Stream version
        pass
```

## Best Practices

1. **Always check capabilities** before using advanced features
2. **Validate context** before making API calls to avoid errors
3. **Set iteration limits** on agents to prevent infinite loops
4. **Handle tool errors** gracefully in tool implementations
5. **Use structured logging** for debugging agent workflows
6. **Implement proper error recovery** in plugins
7. **Keep tool specifications consistent** with actual implementations

## Testing

The framework includes comprehensive tests:

```bash
# Run all tests
python -m pytest tests/ -v

# Run specific capability tests
python -m pytest tests/test_new_capabilities.py -v

# Run architecture compliance tests
python -m pytest tests/test_architecture_rules.py -v
```

## Migration Guide

If you have existing code using the old interfaces:

### Before (Basic Chat)
```python
provider = ProviderFactory.create("openai")
response = provider.chat(request)
```

### After (With New Capabilities)
```python
from crux_providers.base.context import BaseContextManager

provider = ProviderFactory.create("openai")
context_manager = BaseContextManager()

# Validate and prune if needed
if not context_manager.validate_context(request.messages, request.model):
    request.messages = context_manager.prune_context(
        request.messages, request.model
    )

response = provider.chat(request)
```

## Troubleshooting

### "Provider does not support tool use"
- Check if provider implements `SupportsToolUse` interface
- Some providers may require specific model versions for tools

### "Context exceeds model limit"
- Use `BaseContextManager.prune_context()` to fit messages
- Consider using models with larger context windows

### "Plugin initialization failed"
- Check plugin dependencies are registered first
- Verify plugin configuration is valid

### "Agent exceeded max iterations"
- Increase `max_iterations` parameter
- Check tool implementations return properly
- Verify agent has clear completion criteria

## API Reference

See inline documentation in:
- `crux_providers/base/interfaces_parts/` - Protocol definitions
- `crux_providers/base/context/` - Context management
- `crux_providers/base/agent/` - Agent runtime
- `crux_providers/base/plugins/` - Plugin system

## Contributing

When adding new capabilities:

1. Define Protocol interface in `interfaces_parts/`
2. Add capability constant in `capabilities/core.py`
3. Implement base class if applicable
4. Update capability detection in `detect_capabilities()`
5. Add comprehensive tests
6. Update this documentation

All code must:
- Stay under 500 LOC per file
- Follow clean architecture principles
- Include professional docstrings
- Pass all tests
