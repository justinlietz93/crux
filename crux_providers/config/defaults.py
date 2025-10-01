"""crux_providers.config.defaults
=============================

Central place for small, stable default values used across the crux_providers
package and the lightweight service layer. These defaults can be overridden
via environment variables or external configuration, but provide sensible
fallbacks for local development and tests.

Module Purpose
--------------
- Provide a single import location for conservative default constants (no I/O).
- Keep presentation/infra layers free of magic literals, improving readability
    and testability while honoring the project's layered architecture rules.

This module intentionally avoids importing from other provider packages to
prevent circular dependencies. Only plain constants and lightweight helpers
should live here.
"""

from __future__ import annotations

# ---- Service / HTTP layer ----

# Default CORS origins for the FastAPI dev server (comma-separated string)
# Comma-separated list of allowed origins for the dev server.
PROVIDER_SERVICE_CORS_DEFAULT_ORIGINS = "http://localhost:5173,http://127.0.0.1:5173"


# ---- CLI Defaults ----
# Default provider selected by the debugging CLI when none is specified.
PROVIDER_CLI_DEFAULT_PROVIDER = "openrouter"
# Default measured runs and warmups for the benchmark subcommand.
PROVIDER_CLI_BENCH_DEFAULT_RUNS = 10
PROVIDER_CLI_BENCH_DEFAULT_WARMUPS = 2

# Batch refresh utility defaults
# Default provider set for the model registry batch refresher CLI.
PROVIDER_REFRESH_DEFAULT_PROVIDERS = [
    "openai",
    "anthropic",
    "gemini",
    "deepseek",
    "openrouter",
    "ollama",
    "xai",
]
# Default parallelism for the batch refresher CLI.
PROVIDER_REFRESH_DEFAULT_PARALLEL = 1


# ---- Provider-specific sane defaults ----
# OpenRouter defaults used when config does not explicitly set them.
OPENROUTER_DEFAULT_MODEL = "openrouter/auto"
OPENROUTER_DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"

# OpenAI defaults (SDK uses api.openai.com when base_url omitted).
# Centralize model selection for parity across helpers/tests.
OPENAI_DEFAULT_MODEL = "gpt-5"
OPENAI_DEFAULT_BASE_URL = "https://api.openai.com/v1"

# Gemini defaults
GEMINI_DEFAULT_MODEL = "gemini-2.5-pro"

# Anthropic defaults
ANTHROPIC_DEFAULT_MODEL = "claude-4.1-sonnet"

# Deepseek defaults
DEEPSEEK_DEFAULT_MODEL = "deepseek-chat"
DEEPSEEK_DEFAULT_BASE_URL = "https://api.deepseek.com/v1"

# xAI (Grok) defaults
XAI_DEFAULT_MODEL = "grok-4"
XAI_DEFAULT_BASE_URL = "https://api.x.ai/v1"

# Ollama (local daemon) defaults
OLLAMA_DEFAULT_MODEL = "gpt-oss:20b"
OLLAMA_DEFAULT_HOST = "http://localhost:11434"


# ---- SQLite config (infrastructure) ----
# Standard busy timeout to mitigate lock contention (milliseconds).
SQLITE_BUSY_TIMEOUT_MS = 5000
# Journal and sync mode optimized for local development and light concurrency.
SQLITE_JOURNAL_MODE = "WAL"
SQLITE_SYNCHRONOUS = "NORMAL"


__all__ = [
    # Service
    "PROVIDER_SERVICE_CORS_DEFAULT_ORIGINS",
    # CLI
    "PROVIDER_CLI_DEFAULT_PROVIDER",
    "PROVIDER_CLI_BENCH_DEFAULT_RUNS",
    "PROVIDER_CLI_BENCH_DEFAULT_WARMUPS",
    "PROVIDER_REFRESH_DEFAULT_PROVIDERS",
    "PROVIDER_REFRESH_DEFAULT_PARALLEL",
    # Provider defaults
    "OPENROUTER_DEFAULT_MODEL",
    "OPENROUTER_DEFAULT_BASE_URL",
    "OPENAI_DEFAULT_MODEL",
    "OPENAI_DEFAULT_BASE_URL",
    "GEMINI_DEFAULT_MODEL",
    "ANTHROPIC_DEFAULT_MODEL",
    "DEEPSEEK_DEFAULT_MODEL",
    "DEEPSEEK_DEFAULT_BASE_URL",
    "XAI_DEFAULT_MODEL",
    "XAI_DEFAULT_BASE_URL",
    "OLLAMA_DEFAULT_MODEL",
    "OLLAMA_DEFAULT_HOST",
    # SQLite
    "SQLITE_BUSY_TIMEOUT_MS",
    "SQLITE_JOURNAL_MODE",
    "SQLITE_SYNCHRONOUS",
]
