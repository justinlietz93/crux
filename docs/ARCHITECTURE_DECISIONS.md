# Architecture Decision Records (ADR)

## ADR-001: Protocol-Based Interface Design

**Status:** Accepted

**Context:**
Need extensible capability system that allows providers to selectively implement features without breaking existing code.

**Decision:**
Use Python Protocol classes (PEP 544) for all interfaces:
- `LLMProvider` - Core chat interface
- `SupportsStreaming` - Streaming capability
- `SupportsToolUse` - Tool/function calling
- `IContextManager` - Token counting and context management
- `IAgentRuntime` - Multi-step orchestration

**Consequences:**
✅ Runtime capability detection via `isinstance()`
✅ No forced inheritance hierarchies
✅ Incremental adoption by providers
✅ Type checking with mypy/pyright
❌ Slightly more verbose than ABC

---

## ADR-002: Separate Interface and Implementation

**Status:** Accepted

**Context:**
Clean architecture requires separation between contracts (interfaces) and implementations.

**Decision:**
- Interfaces in `crux_providers/base/interfaces_parts/`
- Implementations in `crux_providers/base/{context,agent,plugins}/`
- Never import implementations in interface modules

**Consequences:**
✅ Clear dependency direction (inward)
✅ Easy to swap implementations
✅ Testable via mocking protocols
✅ No circular dependencies
❌ Slightly more files to navigate

---

## ADR-003: File Size Limit of 500 LOC

**Status:** Accepted

**Context:**
Large files become unmaintainable and violate single responsibility principle.

**Decision:**
Enforce maximum 500 lines of code per file via:
- Architecture tests
- Code review
- Breaking large modules into focused submodules

**Consequences:**
✅ Better code organization
✅ Easier code review
✅ Encourages single responsibility
✅ Faster to locate functionality
❌ More files in project
❌ Requires thoughtful decomposition

---

## ADR-004: BaseContextManager with Tiktoken

**Status:** Accepted

**Context:**
Need accurate token counting for context management across different model providers.

**Decision:**
- Use tiktoken library for OpenAI-compatible tokenization
- Fallback to character-based estimation (÷4) when tiktoken unavailable
- Maintain hardcoded context limits for major models
- Support partial model name matching

**Consequences:**
✅ Accurate token counts for most use cases
✅ Works without tiktoken (degraded mode)
✅ Simple API for users
❌ Context limits require manual updates
❌ May not be 100% accurate for all providers

**Alternatives Considered:**
- Provider-specific tokenizers: Rejected (too complex, tight coupling)
- Always use character estimation: Rejected (too inaccurate)

---

## ADR-005: Agent Runtime with Tool Router

**Status:** Accepted

**Context:**
Need orchestration layer that can execute tools requested by LLM in multi-turn conversations.

**Decision:**
- `BaseAgentRuntime` manages conversation loop
- `SimpleToolRouter` dispatches tool calls to handlers
- Support both streaming and non-streaming execution
- Iteration limit to prevent infinite loops

**Consequences:**
✅ Simple, focused implementations
✅ Easy to extend with custom tools
✅ Works with any provider
✅ Automatic error recovery
❌ Basic implementation (no planning, reflection)
❌ Sequential tool execution only

**Future Enhancements:**
- Parallel tool execution
- Tool result caching
- Advanced planning strategies

---

## ADR-006: Plugin System with MCP Support

**Status:** Accepted

**Context:**
Need extensibility mechanism for adding capabilities without modifying core framework.

**Decision:**
- Protocol-based `Plugin` interface
- `PluginRegistry` for lifecycle management
- `MCPPlugin` base class for Model Context Protocol support
- Dependency checking at registration time

**Consequences:**
✅ Clean extension points
✅ MCP compatibility
✅ Dependency validation
✅ Capability-based plugin discovery
❌ Basic implementation (no hot reload)
❌ No plugin marketplace/distribution

---

## ADR-007: Tool Use Interface Design

**Status:** Accepted

**Context:**
Different providers have different tool calling APIs (OpenAI functions, Anthropic tools, etc.)

**Decision:**
- `SupportsToolUse` Protocol with methods:
  - `chat_with_tools()` for non-streaming
  - `stream_chat_with_tools()` for streaming
- Tool specifications in ChatRequest.tools
- Tool calls returned in ContentPart with type="tool_call"

**Consequences:**
✅ Provider-agnostic tool interface
✅ Works with existing ChatRequest/ChatResponse
✅ Supports both execution modes
❌ Requires provider-specific mapping logic
❌ Not all providers may support streaming tools

---

## ADR-008: Capability Detection System

**Status:** Accepted

**Context:**
Need runtime capability detection to gate features and guide users.

**Decision:**
- String constants for capability names (avoid Enum overhead)
- `detect_capabilities()` inspects provider at runtime
- Capability constants: `CAP_STREAMING`, `CAP_TOOL_USE`, etc.
- `should_attempt()` for permissive capability checking

**Consequences:**
✅ Fast runtime checks
✅ No registration ceremony
✅ Works with Protocol instances
✅ Extensible via simple string constants
❌ No compile-time capability validation
❌ Possible typos in capability names

---

## ADR-009: Context Pruning Strategies

**Status:** Accepted

**Context:**
When messages exceed context window, need strategies to fit them.

**Decision:**
Support multiple pruning strategies:
- `oldest_first`: Keep system messages, remove oldest user/assistant pairs
- `sliding_window`: Keep most recent messages
- Always preserve system messages

**Consequences:**
✅ Flexible pruning options
✅ Never lose system context
✅ Predictable behavior
❌ May lose important context
❌ No semantic-aware pruning

**Future Enhancements:**
- Summarization-based pruning
- Importance scoring
- Embedding-based relevance

---

## ADR-010: Testing Strategy

**Status:** Accepted

**Context:**
Need comprehensive testing without requiring live API keys.

**Decision:**
- Unit tests for all core functionality
- Mock provider implementations for testing
- Architecture compliance tests (file size, imports)
- Capability-focused tests
- No integration tests requiring API keys (yet)

**Consequences:**
✅ Fast test execution
✅ No API costs
✅ Consistent test results
✅ Easy to run in CI/CD
❌ May miss provider-specific edge cases
❌ Mock drift from real providers

---

## ADR-011: Error Handling Philosophy

**Status:** Accepted

**Context:**
Need consistent error handling across all framework components.

**Decision:**
- Protocols define expected exceptions in docstrings
- Implementations catch and wrap provider errors
- Log structured error context
- Never fail silently
- Provide fallback behaviors where reasonable

**Consequences:**
✅ Predictable error behavior
✅ Better debugging experience
✅ Graceful degradation
✅ Consistent logging
❌ More try/except blocks
❌ Potential performance overhead

---

## Decision Review Process

ADRs should be reviewed when:
1. User feedback indicates design issues
2. New major features require architectural changes
3. Performance bottlenecks emerge
4. Annually for general review

To propose a new ADR:
1. Create a draft following the template
2. Discuss in issue/PR
3. Get approval from maintainers
4. Update this document
5. Implement the decision
