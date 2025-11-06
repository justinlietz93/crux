# 🎉 New Universal Framework Capabilities

The Crux Provider Framework has been enhanced with powerful new capabilities that make it a truly universal LLM abstraction layer!

## What's New

### 🛠️ Tool Use / Function Calling
- **`SupportsToolUse` Interface**: Enable providers to execute tools and functions
- **Streaming & Non-Streaming**: Support for both execution modes
- **Provider Agnostic**: Works across OpenAI, Anthropic, Gemini, and more

### 🧠 Context Management
- **`IContextManager` Interface**: Token counting and context window management
- **Smart Pruning**: Automatically fit conversations within model limits
- **15+ Model Support**: Pre-configured limits for all major LLM models
- **Tiktoken Integration**: Accurate token counting with fallback support

### 🤖 Agent Runtime
- **`IAgentRuntime` Interface**: Multi-step orchestration with tool execution
- **Automatic Loops**: LLM → Tool → LLM cycles handled automatically
- **Streaming Progress**: Real-time updates during agent execution
- **History Management**: Full conversation tracking

### 🔌 Plugin System
- **`PluginRegistry`**: Centralized plugin lifecycle management
- **MCP Support**: Model Context Protocol base implementation
- **Dependency Resolution**: Automatic plugin dependency checking
- **Capability Discovery**: Find plugins by what they can do

## Quick Start

```python
from crux_providers.base import ProviderFactory
from crux_providers.base.context import BaseContextManager
from crux_providers.base.agent import BaseAgentRuntime

# Get provider
provider = ProviderFactory.create("openai")

# Setup context manager
context_manager = BaseContextManager()

# Create agent runtime
runtime = BaseAgentRuntime(provider)

# Register tools
runtime.register_tool("calculator", my_calculator_func)

# Execute with context management
response = runtime.execute(
    goal="Calculate 42 * 137",
    tools=tool_specs,
    max_iterations=5
)
```

## Documentation

📚 **[Complete Guide](./UNIVERSAL_FRAMEWORK_GUIDE.md)** - Comprehensive usage guide with examples

🏗️ **[Architecture Decisions](./ARCHITECTURE_DECISIONS.md)** - Design rationale and ADRs

📖 **[Main README](../crux_providers/README.md)** - Provider framework overview

## Key Benefits

✅ **Unified Interface**: One API for all providers
✅ **Selective Capabilities**: Enable only what you need
✅ **Production Ready**: Comprehensive tests and error handling
✅ **Well Documented**: Every public API has detailed docstrings
✅ **Clean Architecture**: Follows SOLID principles
✅ **Extensible**: Easy to add new capabilities via plugins

## What's Included

### Core Interfaces
- `SupportsToolUse` - Tool/function calling protocol
- `IContextManager` - Token counting and management
- `IAgentRuntime` - Multi-step orchestration
- `Plugin` - Extensibility protocol

### Base Implementations
- `BaseContextManager` - Token counting with tiktoken
- `BaseAgentRuntime` - Agent orchestration engine
- `PluginRegistry` - Plugin lifecycle manager
- `MCPPlugin` - Model Context Protocol base

### Testing
- 12 comprehensive tests (all passing ✅)
- Architecture compliance validation
- Capability coverage verification

## Upgrade Path

The new capabilities are **fully backward compatible**:

```python
# Old code still works
provider = ProviderFactory.create("openai")
response = provider.chat(request)

# New capabilities are opt-in
from crux_providers.base.context import BaseContextManager
manager = BaseContextManager()
# Use new features when ready
```

## Contributing

To add new capabilities:

1. Define Protocol interface in `interfaces_parts/`
2. Add capability constant to `capabilities/core.py`
3. Implement base class (optional)
4. Update capability detection
5. Add tests
6. Update documentation

See [Architecture Decisions](./ARCHITECTURE_DECISIONS.md) for guidelines.

## Examples

### Token Counting
```python
from crux_providers.base.context import BaseContextManager

manager = BaseContextManager()
tokens = manager.count_tokens(messages)
print(f"This conversation uses {tokens} tokens")
```

### Agent with Tools
```python
from crux_providers.base.agent import BaseAgentRuntime

runtime = BaseAgentRuntime(provider)
runtime.register_tool("search", search_func)
runtime.register_tool("calculate", calc_func)

response = runtime.execute(
    goal="Find GDP of France and divide by population",
    tools=tool_specs
)
```

### Plugin System
```python
from crux_providers.base.plugins import PluginRegistry, MCPPlugin

registry = PluginRegistry()
plugin = MyCustomPlugin()
registry.register(plugin)
```

## Next Steps

1. **Read the Guide**: [UNIVERSAL_FRAMEWORK_GUIDE.md](./UNIVERSAL_FRAMEWORK_GUIDE.md)
2. **Try Examples**: See guide for complete working examples
3. **Build Agents**: Use `BaseAgentRuntime` for your use case
4. **Create Plugins**: Extend with custom capabilities

## Support

- 📝 Issues: [GitHub Issues](https://github.com/justinlietz93/crux/issues)
- 💬 Discussions: [GitHub Discussions](https://github.com/justinlietz93/crux/discussions)
- 📖 Docs: This directory

---

**Status**: ✅ Production Ready | 🧪 Fully Tested | 📚 Well Documented
