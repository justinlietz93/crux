# Code Map: Key Modules and Classes

**Repository:** justinlietz93/crux  
**Commit:** 5f656cd2c1962d2bde2dcfa17252b1821885c998  
**Generated:** 2025-12-05  

---

## Provider Adapters

| Module | Path | LOC | Classes | Functions | Responsibility |
|--------|------|-----|---------|-----------|----------------|
| `openai.client` | `crux_providers/openai/client.py` | 196 | 1 | 2 | OpenAI provider adapter implementing LLMProvider, SupportsJSONOutput |
| `openai.get_openai_models` | `crux_providers/openai/get_openai_models.py` | 290 | 0 | 1 | Fetch OpenAI model metadata via API |
| `anthropic.client` | `crux_providers/anthropic/client.py` | 221 | 1 | 2 | Anthropic provider adapter with streaming and tool use |
| `anthropic.chat_helpers` | `crux_providers/anthropic/chat_helpers.py` | 297 | 0 | 4 | Request/response normalization for Anthropic API |
| `anthropic.stream_helpers` | `crux_providers/anthropic/stream_helpers.py` | 85 | 0 | 2 | Streaming delta aggregation helpers |
| `anthropic.get_anthropic_models` | `crux_providers/anthropic/get_anthropic_models.py` | 290 | 0 | 1 | Fetch Anthropic model metadata via API |
| `gemini.client` | `crux_providers/gemini/client.py` | 507 | 1 | 6 | **[FILE SIZE VIOLATION]** Gemini adapter with streaming support |
| `gemini.get_gemini_models` | `crux_providers/gemini/get_gemini_models.py` | 131 | 0 | 1 | Fetch Gemini model metadata via Google API |
| `ollama.client` | `crux_providers/ollama/client.py` | 213 | 1 | 3 | Ollama local LLM adapter |
| `ollama.helpers` | `crux_providers/ollama/helpers.py` | 181 | 0 | 5 | Request transformation for Ollama API |
| `ollama.get_ollama_models` | `crux_providers/ollama/get_ollama_models.py` | 112 | 0 | 1 | List local Ollama models |
| `openrouter.client` | `crux_providers/openrouter/client.py` | 297 | 1 | 3 | OpenRouter multi-provider gateway adapter |
| `deepseek.client` | `crux_providers/deepseek/client.py` | 50 | 1 | 0 | Deepseek adapter (OpenAI-compatible) |
| `xai.client` | `crux_providers/xai/client.py` | 53 | 1 | 0 | xAI/Grok adapter (OpenAI-compatible) |

**Note:** Gemini client (507 LOC) exceeds the 500 LOC architectural constraint and is flagged for decomposition into separate helper modules.

---

## Base Abstractions

| Module | Path | LOC | Classes | Functions | Responsibility |
|--------|------|-----|---------|-----------|----------------|
| `base.factory` | `crux_providers/base/factory.py` | 209 | 2 | 3 | Provider factory with lazy instantiation |
| `base.interfaces_parts.llm_provider` | `crux_providers/base/interfaces_parts/llm_provider.py` | 54 | 1 | 0 | Core LLMProvider protocol |
| `base.interfaces_parts.supports_streaming` | `crux_providers/base/interfaces_parts/supports_streaming.py` | 56 | 1 | 0 | Streaming support protocol |
| `base.interfaces_parts.supports_json_output` | `crux_providers/base/interfaces_parts/supports_json_output.py` | 42 | 1 | 0 | JSON output protocol |
| `base.interfaces_parts.supports_tool_use` | `crux_providers/base/interfaces_parts/supports_tool_use.py` | 44 | 1 | 0 | Tool use protocol |
| `base.models_parts.chat_request` | `crux_providers/base/models_parts/chat_request.py` | 91 | 1 | 0 | Chat request DTO with Pydantic validation |
| `base.models_parts.chat_response` | `crux_providers/base/models_parts/chat_response.py` | 68 | 1 | 0 | Chat response DTO |
| `base.models_parts.message` | `crux_providers/base/models_parts/message.py` | 51 | 2 | 0 | Message DTO (role + content) |
| `base.models_parts.model_info` | `crux_providers/base/models_parts/model_info.py` | 59 | 1 | 0 | Model metadata DTO |
| `base.streaming.adapter` | `crux_providers/base/streaming/adapter.py` | 333 | 1 | 4 | Base streaming adapter with metrics capture |
| `base.streaming.finalize` | `crux_providers/base/streaming/finalize.py` | 133 | 0 | 1 | Streaming finalization with metrics logging |
| `base.streaming.controller` | `crux_providers/base/streaming/controller.py` | 89 | 1 | 0 | Streaming lifecycle controller |
| `base.timeouts` | `crux_providers/base/timeouts.py` | 244 | 1 | 2 | Timeout configuration and enforcement |
| `base.cancellation` | `crux_providers/base/cancellation.py` | 23 | 0 | 0 | Cancellation token exports |
| `base.resilience.retry` | `crux_providers/base/resilience/retry.py` | 158 | 1 | 1 | Retry logic with exponential backoff |
| `base.http.client` | `crux_providers/base/http/client.py` | 153 | 0 | 1 | HTTP client pool with connection reuse |
| `base.logging` | `crux_providers/base/logging.py` | 329 | 4 | 6 | Structured logging with JSON formatter |
| `base.tracing` | `crux_providers/base/tracing.py` | 58 | 0 | 2 | Distributed tracing support |
| `base.errors_parts.provider_error` | `crux_providers/base/errors_parts/provider_error.py` | 40 | 1 | 0 | Provider error exception with error codes |
| `base.errors_parts.error_code` | `crux_providers/base/errors_parts/error_code.py` | 31 | 1 | 0 | Error code enumeration |

---

## Persistence Layer

| Module | Path | LOC | Classes | Functions | Responsibility |
|--------|------|-----|---------|-----------|----------------|
| `persistence.interfaces.repos` | `crux_providers/persistence/interfaces/repos.py` | 396 | 8 | 15 | Repository interface definitions (protocols) |
| `persistence.sqlite.engine` | `crux_providers/sqlite/engine.py` | 200 | 0 | 4 | SQLite connection factory and pooling |
| `persistence.sqlite.db_schema` | `crux_providers/persistence/sqlite/db_schema.py` | 136 | 0 | 1 | SQL schema DDL for all tables |
| `persistence.sqlite.model_registry_store` | `crux_providers/persistence/sqlite/model_registry_store.py` | 383 | 0 | 2 | Model registry repository implementation |
| `persistence.sqlite.keystore_repo` | `crux_providers/persistence/sqlite/keystore_repo.py` | 93 | 1 | 4 | API key vault repository |
| `persistence.sqlite.chatlog_repo` | `crux_providers/persistence/sqlite/chatlog_repo.py` | 70 | 1 | 3 | Chat log repository |
| `persistence.sqlite.metrics_repo` | `crux_providers/persistence/sqlite/metrics_repo.py` | 150 | 1 | 4 | Metrics repository |
| `persistence.sqlite.prefs_repo` | `crux_providers/persistence/sqlite/prefs_repo.py` | 74 | 1 | 2 | User preferences repository |
| `persistence.sqlite.observed_capabilities_store` | `crux_providers/persistence/sqlite/observed_capabilities_store.py` | 107 | 0 | 2 | Capability observation store |
| `persistence.sqlite.unit_of_work` | `crux_providers/persistence/sqlite/unit_of_work.py` | 59 | 1 | 2 | Unit of Work transaction coordinator |
| `persistence.sqlite.migrator` | `crux_providers/persistence/sqlite/migrator.py` | 155 | 0 | 1 | Schema migration runner |
| `persistence.sqlite.sqlite_config` | `crux_providers/persistence/sqlite/sqlite_config.py` | 141 | 0 | 2 | SQLite configuration (WAL, busy_timeout) |

---

## Service Layer

| Module | Path | LOC | Classes | Functions | Responsibility |
|--------|------|-----|---------|-----------|----------------|
| `service.app` | `crux_providers/service/app.py` | 455 | 5 | 11 | FastAPI application with REST endpoints |
| `service.cli.cli_shell` | `crux_providers/service/cli/cli_shell.py` | 576 | 1 | 12 | **[FILE SIZE VIOLATION]** Interactive CLI shell |
| `service.cli.cli_actions` | `crux_providers/service/cli/cli_actions.py` | 407 | 0 | 10 | CLI command implementations |
| `service.helpers` | `crux_providers/service/helpers.py` | 430 | 0 | 5 | Service-layer helper functions |
| `service.db` | `crux_providers/service/db.py` | 414 | 0 | 11 | Database access for service layer |
| `service.benchmark` | `crux_providers/service/benchmark.py` | 366 | 0 | 2 | Benchmarking utilities |
| `service.chat_request_build` | `crux_providers/service/chat_request_build.py` | 162 | 0 | 2 | Request builder from API inputs |
| `service.cli.settings` | `crux_providers/service/cli/settings.py` | 243 | 1 | 4 | CLI settings management |
| `service.model_registry_store` | `crux_providers/service/model_registry_store.py` | 165 | 0 | 2 | Service-layer model registry facade |

**Note:** CLI shell (576 LOC) exceeds the 500 LOC limit and should be decomposed into separate command handlers.

---

## Configuration

| Module | Path | LOC | Classes | Functions | Responsibility |
|--------|------|-----|---------|-----------|----------------|
| `config.defaults` | `crux_providers/config/defaults.py` | 114 | 0 | 0 | Centralized default values (models, timeouts, SQLite) |
| `config.env` | `crux_providers/config/env.py` | 177 | 0 | 5 | Environment variable mapping and API key resolution |

---

## Utilities

| Module | Path | LOC | Classes | Functions | Responsibility |
|--------|------|-----|---------|-----------|----------------|
| `utils.input_size_guard` | `crux_providers/utils/input_size_guard.py` | 352 | 0 | 6 | Input validation and size limits (max 1M chars) |
| `utils.refresh_all_models` | `crux_providers/utils/refresh_all_models.py` | 212 | 1 | 4 | Batch model registry refresh CLI |
| `di.container` | `crux_providers/di/container.py` | 91 | 1 | 4 | Dependency injection container |

---

## Key Entry Points

### SDK Entry Point
- **Path:** `crux_providers/__init__.py`
- **Exports:** `create()`, `ProviderFactory`, interfaces, DTOs
- **Usage:** `from crux_providers import create; provider = create('openai')`

### CLI Entry Point
- **Path:** `crux_providers/service/cli/__main__.py`
- **Command:** `python -m crux_providers.service.cli`
- **Subcommands:** chat, models, benchmark, keys, refresh

### API Entry Point
- **Path:** `crux_providers/service/dev_server.py`
- **Tech:** FastAPI + Uvicorn
- **Endpoint:** `http://localhost:8091/v1/chat`

---

## File Size Violations

The following modules exceed the 500 LOC architectural constraint:

1. **`gemini.client`** - 507 LOC
   - **Reason:** Comprehensive streaming implementation + chat + model listing
   - **Remediation:** Extract to `gemini.chat_helpers`, `gemini.stream_helpers`, `gemini.model_helpers`
   - **Revisit Date:** 2025-10-15

2. **`service.cli.cli_shell`** - 576 LOC
   - **Reason:** Interactive shell with command routing, history, autocomplete
   - **Remediation:** Extract to `cli_shell_commands`, `cli_shell_ui`, `cli_shell_history`
   - **Revisit Date:** 2025-10-15

These violations are tracked in `test_policies_filesize.py` with temporary allowlist.

---

## Module Count Summary

| Layer | Module Count |
|-------|--------------|
| Provider Adapters | 14 modules across 7 providers |
| Base Abstractions | 60+ modules (interfaces, DTOs, utilities) |
| Persistence | 16 modules (repositories + SQLite engine) |
| Service Layer | 14 modules (API, CLI, helpers) |
| Configuration | 2 modules |
| Utilities | 3 modules |
| **TOTAL** | **165 non-test modules** |

---

## Linkback Reference

All file paths in this document are relative to repository root. To view source:

```bash
# View a module
cat crux_providers/openai/client.py

# Search for pattern
grep -r "class.*Provider" crux_providers/*/client.py
```

---

**Document Version:** 1.0  
**Last Updated:** 2025-12-05
