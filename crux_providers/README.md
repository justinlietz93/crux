<!-- markdownlint-disable MD001 MD003 MD005 MD007 MD022 MD032 -->
#

![alt text](assets/crux_banner.jpg)

***A reliable provider-agnostic LLM abstraction layer. Crux offers a turn-key provider client solution using Hybrid Clean Architecture patterns.***

Overview

- Goal: Normalize provider interactions behind small, typed contracts while keeping all provider-specific logic contained under crux_providers/.
- Key benefits:
  - Provider-agnostic DTOs and interfaces
  - Central factory for adapter creation
  - Model registry repository to read/write per-provider model listings (JSON)
  - Pluggable “get models” fetchers per provider
  - Non-invasive: adapters wrap existing clients where possible

## Installation

Install the library from a source distribution or PyPI (planned name: `crux-providers`). The canonical import path is `crux_providers` (package root: `crux_providers`).

```bash
pip install crux-providers
# or with common extras (installs provider SDKs):
pip install "crux-providers[all]"
```

Provider-specific extras:

- OpenAI: `pip install "crux-providers[openai]"`
- Anthropic: `pip install "crux-providers[anthropic]"`
- Gemini: `pip install "crux-providers[gemini]"`
- Ollama: `pip install "crux-providers[ollama]"`
- OpenRouter: `pip install "crux-providers[openrouter]"`
- Deepseek: `pip install "crux-providers[deepseek]"`
- xAI: `pip install "crux-providers[xai]"`

After installing, use the `providers` import path:

```python
from crux_providers.base import ProviderFactory, ChatRequest, Message
```

## Quick Start (Contributors)
## Centralized Configuration

Defaults and environment mappings are centralized to reduce drift and improve maintainability:

- `crux_providers/config/defaults.py`
  - CLI defaults (e.g., default provider, benchmark runs/warmups)
  - OpenRouter defaults (model and base URL)
  - SQLite defaults (journal mode, synchronous, busy timeout)
- `crux_providers/config/env.py`
  - Canonical env var names per provider via `ENV_MAP`
  - Aliases per provider via `ENV_ALIASES` (e.g., Gemini supports `GEMINI_API_KEY` and `GOOGLE_API_KEY`)
  - Helpers: `is_placeholder`, `get_env_var_name`, `get_env_var_candidates`, `resolve_provider_key`, `set_canonical_env_if_missing`

Usage guidelines:
- Do not hardcode defaults in adapters, CLI, or persistence; import from `crux_providers.config.defaults`.
- Resolve provider API keys via `crux_providers.config.env` and promote alias → canonical using `set_canonical_env_if_missing`.

## Architecture Standards Enforcement

We enforce key architecture rules via tests:

- File size limit: no source file should exceed 500 lines.
  - Policy test: `crux_providers/tests/test_policies_filesize.py` scans provider modules and fails if over budget.
  - Temporary allowlist: select oversized modules are allow-listed with a `# deviation:` note and a revisit date.
  - Current revisit target: 2025-10-15. Oversized modules will be decomposed into focused submodules without changing public APIs.
- Streaming must use `BaseStreamingAdapter`; bespoke loops are prohibited.
- Use `get_timeout_config()` and guard start phases with `operation_timeout`. Do not hardcode numeric timeouts.
- Structured logging: include `provider`, `operation`, `stage`, `failure_class`, `fallback_used`.

## Testing

- Streaming contract tests live under `crux_providers/tests/streaming`.
- Edge cases for env config: `crux_providers/tests/test_env_config_edge_cases.py`.
- Run targeted tests:

```bash
/mnt/samsung_ssd/notes/.venv/bin/python -m pytest -q crux_providers/tests/test_env_config_edge_cases.py crux_providers/tests/test_policies_filesize.py crux_providers/tests/streaming
```

  1. Implementing a new provider:
    - Create `crux_providers/<provider>/client.py` implementing the core `LLMProvider` interface.
    - Add an optional `get_<provider>_models.py` with a `run()` entrypoint returning list[dict].
    - Register the adapter in `ProviderFactory`.
  1. Streaming:
    - All new streaming implementations MUST use `BaseStreamingAdapter`; do not write custom loops.
  1. Timestamps:
    - Metrics & chat log `created_at` are stored as ISO8601 UTC strings; naive datetimes are coerced to UTC. See policy section below.
  1. Tests:
    - Place all tests under `crux_providers/tests/`; do not place test code outside the package.
  1. Token usage:
    - Placeholder `{"prompt": null, "completion": null, "total": null}` must always be present until real counts are wired.
  1. Logging & metrics:
    - Streaming finalize path emits exactly one structured log with latency metrics; never suppress errors silently.
    - External metrics emission (feature-flagged): when `PROVIDERS_METRICS_EXPORT` is set to `1` or `true`, the streaming finalize path emits a summarized metrics payload via the default exporter. By default, a no-op exporter is used, so enabling the flag has no effect unless a concrete exporter is wired. Emission failures never raise and are logged once as `metrics.export.error`.
  1. Security:
    - Never use `shell=True`; resolve executables via `shutil.which` in any future subprocess integrations.
  1. Docstrings:
    - Provide full professional docstrings for every public class/function (purpose, params, returns, failure modes).
  1. CI & Enforcement:
    - CI: Providers fast tests run on pushes/PRs that touch providers code.
    - Manual: Workflow can be run on demand from Actions (workflow_dispatch enabled).
    - Enforcement: Protect `main` and require the "Providers Fast Tests" check to pass before merging; optionally disallow direct pushes.
    - Local gate (optional): Use pre-commit pre-push hook to run providers tests before `git push`.

  Minimal Example (Factory Usage):

  ```python
  from crux_providers.base import ProviderFactory, ChatRequest, Message

  provider = ProviderFactory.create("openai")
  resp = provider.chat(
     ChatRequest(
        model=provider.default_model() or "o3-mini",
        messages=[
          Message(role="system", content="You are concise."),
          Message(role="user", content="Ping")
        ],
        max_tokens=32,
        response_format="text",
     )
  )
  print(resp.text)
  ```

  > For streaming, wrap provider call with the standardized `BaseStreamingAdapter`; see Streaming section below.

## Cross-Provider Guarantees Matrix

The providers layer enforces a consistent set of behavioral and data-shape guarantees across all adapters. These are contract-level promises intended to simplify integrations and testing.

- Requests and DTOs
  - Always use provider-agnostic DTOs: `Message`, `ChatRequest`, `ChatResponse`, `ProviderMetadata`.
  - Token usage placeholders are present on `ChatResponse.metadata.tokens` (prompt, completion, total may be `null`).
  - System/user message extraction trims whitespace-only lines before joining user segments.

- Streaming lifecycle (BaseStreamingAdapter)
  - Exactly one terminal event is emitted per stream (success or error).
  - Metrics captured internally and surfaced via finalize event:
    - `emitted_count`: number of deltas (finish event excluded)
    - `time_to_first_token_ms`: set only if at least one delta was emitted
    - `total_duration_ms`: set on every terminal event
  - Invariants:
    - If `emitted_count` == 0 ⇒ `time_to_first_token_ms` is `null`
    - When present, `time_to_first_token_ms` ≤ `total_duration_ms`
  - Start phase only is covered by timeout + retry; mid-stream flow is cooperative via cancellation token.
  - Cancellation maps to a normalized `cancelled` error code and still emits a terminal event with metrics.

- Capability gating
  - `streaming_supported()` centralizes checks; adapters short-circuit when unsupported.

- Error handling & logging
  - Unexpected exceptions are classified into a normalized error code and emitted on the terminal event; no silent suppression.
  - Structured logging fields are normalized (phase, attempt, error_code, emitted, tokens) in finalize logs.

- Tracing (optional)
  - Streaming start and run phases are instrumented with lightweight spans when OpenTelemetry is present; otherwise a no-op.
  - Span attributes include `provider`, `model`, and terminal metrics (`emitted_count`, `time_to_first_token_ms`, `total_duration_ms`).

- Security & subprocess policy
  - No `shell=True`; executables resolved via `shutil.which` and validated when subprocess is used.

- Architectural standards
  - All new streaming implementations must use `BaseStreamingAdapter` (no bespoke loops).
  - Public functions/classes include full docstrings (purpose, params, returns, failure modes).
  - Adhere to file-size and complexity targets documented at the repo root; prefer small, focused modules.

These guarantees are validated by the streaming contract tests under `crux_providers/tests/streaming/` and conventional unit tests under `crux_providers/tests/`.

Core contracts and types

- Interfaces:
  - LLMProvider (core provider contract)
  - SupportsJSONOutput, SupportsResponsesAPI (capability flags)
  - ModelListingProvider (expose list_models)
  - HasDefaultModel (optional default model)
  See [interfaces.py](crux_providers/base/interfaces.py).

- DTOs (Provider-agnostic models):
  - Message, ChatRequest, ChatResponse, ProviderMetadata
  - ModelInfo, ModelRegistrySnapshot
  - References:
    - [Message](crux_providers/base/models.py)
    - [ChatRequest](crux_providers/base/models.py)
    - [ChatResponse](crux_providers/base/models.py)
    - [ProviderMetadata](crux_providers/base/models.py)
    - [ModelInfo](crux_providers/base/models.py)
    - [ModelRegistrySnapshot](crux_providers/base/models.py)
      See [models.py](crux_providers/base/models.py).

- Repositories:
  - Model registry I/O and refresh orchestration:
    - [ModelRegistryRepository](crux_providers/base/repositories/model_registry/repository.py)
      - Key method: list_models(provider, refresh=False)
  - DB-first: reads snapshots from SQLite (JSON cache files removed)
      - Optional refresh invokes provider “get models” script
      - The model registry no longer reads or writes provider JSON files.
  - Keys (API key resolution):
    - [KeysRepository.get_api_key()](crux_providers/base/repositories/keys.py)
    - Resolution order: env (OPENAI_API_KEY, etc.) → config.yaml → None

- Factory:
  - [ProviderFactory.create()](crux_providers/base/factory.py)
    - Maps canonical provider name (e.g., "openai") to adapter class by lazy import
Operational Use:

Provider adapters

### Token Accounting (Legacy Placeholder Notes)
  - Adapter: [OpenAIProvider](crux_providers/openai/client.py)
    - Exposes:
      - provider_name: "openai"
Extraction Logic:

      - supports_json_output(): bool
      - uses_responses_api(model: str): bool (o3/o1 families)
Fallback Semantics:

      - chat(request: ChatRequest): ChatResponse
    - Internals:
Validation:

      - model default derived from get_openai_config() with fallback (o3-mini)
      - Structured outputs: request.response_format == "json_object"
Streaming vs Non-Streaming:

Model registry

Consumer Guidance:

  - SQLite is the authoritative store for model snapshots (no JSON cache files)
  - Repository: [ModelRegistryRepository](crux_providers/base/repositories/model_registry/repository.py)
    - refresh=True will attempt a provider get-models runner:
      ``crux_providers.{provider}.get_{provider}_models``
    - Accepts multiple entrypoint names: ``run()``, ``get_models()``, ``fetch_models()``,
      ``update_models()``, ``refresh_models()``, ``main()``
    - Reads exclusively from SQLite; if no snapshot exists for a provider, an empty
      snapshot is returned unless a refresh is requested.

Provider “get models” fetchers (API-backed)

- OpenAI:
  - Module: [get_openai_models.py](crux_providers/openai/get_openai_models.py)
    - Entry point: [run()](crux_providers/openai/get_openai_models.py)
    - Behavior:
      - If OPENAI_API_KEY is present, fetch via OpenAI SDK:
        client = OpenAI(api_key=key)
        items = client.models.list()
  - Normalize and persist via save_provider_models()
      - Return list[dict] for ModelRegistryRepository convenience
    - Offline mode:
      - Falls back to load_cached_models(provider) and returns cached entries
      - Does not write empty registries (no false positives)
  - Key resolution:
    - [KeysRepository.get_api_key("openai")](crux_providers/base/repositories/keys.py)
    - Uses env (OPENAI_API_KEY) or config.yaml api.openai.api_key

Usage

**1.** Installing dependencies

- Base:
  - pip install -r requirements.txt
- Dev (pytest, etc.):
  - pip install -r requirements-dev.txt

**2.** API keys

- Preferred: .env at project root (project-local .env)
  - Example:
  OPENAI_API_KEY=sk-...  # pragma: allowlist secret (example prefix only)
- Alternative: config.yaml
  - api:
    openai:
  api_key: "sk-..."  # pragma: allowlist secret (example prefix only)
- Key resolution order:
  - Env → config.yaml → None. See [KeysRepository](crux_providers/base/repositories/keys.py).

**3.** Populate model registries (OpenAI example)

- Ensure key is loaded into the process environment (source .env).
- Run fetcher (no code changes required):
  - python -m crux_providers.openai.get_openai_models
  - Expected: "[openai] loaded **\<N>** models" and JSON persisted at:
  Stored in the SQLite model registry (DB-first)

**4.** Instantiate providers via factory

- Example:
  - from crux_providers.base import ProviderFactory, ChatRequest, Message
  - provider = [ProviderFactory.create()](crux_providers/base/factory.py)("openai")
  - req = ChatRequest(
    model=provider.default_model() or "o3-mini",
    messages=[
    Message(role="system", content="You are a concise assistant."),
    Message(role="user", content="Say 'ok' once.")
    ],
    max_tokens=32,
    response_format="text",
    )
  - resp = provider.chat(req)
  - print(resp.text)

**5.** Listing models

- Example (OpenAI):
  - provider = ProviderFactory.create("openai")
  - snap = [OpenAIProvider.list_models()](crux_providers/openai/client.py)(refresh=False)
  - print(len(snap.models))
- To refresh from API:
  - snap = provider.list_models(refresh=True) # requires OPENAI_API_KEY

**6.** Providers CLI (Benchmark harness)

The providers layer ships with a small CLI to assist local diagnostics and performance checks. After installing this project in editable mode, a console entry `providers-cli` is available.

- Benchmark latency for a provider/model with warmups and multiple measured runs:

```bash
providers-cli benchmark \
  --provider openai \
  --model o3-mini \
  --prompt "Say 'ok' once." \
  --runs 5 \
  --warmups 2 \
  --stream false
```

Flags

- `--provider` (required): Canonical provider id (e.g., `openai`, `anthropic`, `deepseek`, `xai`, `gemini`, `ollama`).
- `--model` (required): Model name to exercise.
- `--prompt` (required when `--execute`-style actions are used; for benchmark it's required): Prompt text to send.
- `--runs` (default 5): Number of measured runs; statistics are computed over these durations.
- `--warmups` (default 0): Non-measured warmup iterations executed before timing begins.
- `--stream` (default false): When true, uses streaming path; otherwise non-streaming chat.

Output

The command prints a small JSON object with latency statistics:

```json
{
  "count": 5,
  "total_ms": 1234.5,
  "min_ms": 200.1,
  "max_ms": 260.3,
  "mean_ms": 246.9,
  "median_ms": 248.0,
  "p50_ms": 248.0,
  "p90_ms": 258.4,
  "p95_ms": 259.7,
  "p99_ms": 260.2
}
```

Notes

- Timeouts follow the centralized strategy and guard only the start/blocking phase; mid-stream cancellation is cooperative.
- Structured logs include `provider`, `operation`, and `metrics` fields to aid local inspection.
- External metrics emission (optional): set env `PROVIDERS_METRICS_EXPORT=1` to enable best-effort emission. The default exporter is a no-op. Integrators can substitute an exporter by overriding `crux_providers.base.metrics.get_default_exporter()` to return a concrete implementation that implements `emit_stream_metrics(StreamMetricsPayload)`.

### External Metrics Emission

Overview

- Purpose: allow best-effort emission of streaming metrics to external systems without coupling core code to a specific backend.
- Toggle: controlled by env var `PROVIDERS_METRICS_EXPORT` (`1`/`true` to enable). Default is disabled.

Behavior

- On stream finalize, we emit a single metrics payload through the default exporter if the flag is enabled. Failures are swallowed and logged as a single normalized event with key `metrics.export.error` to avoid breaking application flow.

Default Exporter

- Path: `crux_providers/base/metrics/exporter.py`.
- `get_default_exporter()` returns a process-wide `NoOpMetricsExporter` by default.
- To integrate with Prometheus, OTEL, or another system, provide a concrete `MetricsExporter` and return it from `get_default_exporter()` (or monkeypatch in tests).

Payload Shape (`StreamMetricsPayload`)

- Fields:
  - `provider: str`
  - `model: str`
  - `emitted_count: int`
  - `time_to_first_token_ms: Optional[float]`
  - `total_duration_ms: Optional[float]`
  - `tokens: Optional[Mapping[str, Any]]` with keys `prompt`, `completion`, `total` when known
  - `error: Optional[str]`
  - `extra: Optional[Mapping[str, Any]]` (reserved for future use)

Failure Semantics

- Exporters must not raise; they should catch and swallow exceptions.
- The finalize helper also wraps emission in a `try/except` and logs a single `metrics.export.error` event containing `failure_class` when an exception occurs.

Testing

- Unit tests exist under `crux_providers/tests/test_metrics_emission.py` validating both the happy-path emission and failure logging behavior.
- For reproducible results, ensure a stable network and consider pinning the model version when the provider supports it.

Testing

Location and policy

- All providers tests live under crux_providers/tests/... (no test scripts in other folders by architecture rules).

Unit smoke test (factory + OpenAI adapter)

- File: crux_providers/tests/test_provider_factory_smoke.py
- What it covers:
  - ProviderFactory creates OpenAI adapter
  - Adapter exposes provider_name and default_model
  - list_models(refresh=True) populates registry when OPENAI_API_KEY is set; otherwise the test is skipped (no-network)
- Run:
  - python -m pytest -q crux_providers/tests/test_provider_factory_smoke.py

Enforcement (CI + Local Pre-Push)
---------------------------------

Server-side (recommended)
- In GitHub → Settings → Branches → Branch protection rules (for `main`):
  - Require a pull request before merging
  - Require status checks to pass before merging
  - Select the "Providers Fast Tests" check (job: "Run providers tests")
  - Optionally: restrict who can push (disallow direct pushes)

Local (optional, developer convenience)
- Pre-push gate using pre-commit to block pushes when providers tests fail:

```bash
pip install pre-commit
pre-commit install --hook-type pre-push
```

The repository includes `.pre-commit-config.yaml` with a hook that runs:

```bash
pytest -q crux_providers/tests
```

Bypass temporarily with `git push --no-verify` if necessary.

Design notes and guardrails

- Non-invasive adapter design:
  - OpenAIProvider chat() wraps existing call_openai_with_retry()
  - No changes to legacy OpenAI client semantics
- Offline/dev behavior:
  - The model registry reads and writes exclusively to SQLite. When a live fetch
    fails, fetchers fall back to the cached snapshot from the database. No JSON
    cache files are used.
- Extensibility:
  - Register new providers by adding entries to ProviderFactory._PROVIDERS and implementing a client.py adapter plus get*{provider}_models.py
  - Keep provider-specific SDK imports in provider modules only
- Observability:
  - ProviderMetadata attached to ChatResponse supports audits and test logging
  - `request_id` and `response_id` fields (when available) now propagated into `ProviderMetadata` and streaming `LogContext` for correlation.

Metadata completeness and limitations

- context_length
  - Policy: Keep null when not provided by the API. Do not fabricate limits.
  - Enrichment flow: [get_openai_models.run()](crux_providers/openai/get_openai_models.py) fetches list and best-effort details (client.models.retrieve) and passes through numeric fields (e.g., input_token_limit/context_window) when present. Normalization in [normalize_items()](crux_providers/base/get_models_base.py) maps these into context_length if and only if explicitly available.
- capabilities
  - Derived from SDK “modalities” when present and from conservative id heuristics in [normalize_items()](crux_providers/base/get_models_base.py) (e.g., mark reasoning/responses_api for o1/o3 families; vision for gpt-4o/omni; embeddings for text-embedding ids; JSON structured output flagged by default).
- updated_at
  - Prefer explicit updated_at from the SDK. If absent, infer ISO date from the model id via [\_infer_updated_at_from_id()](crux_providers/base/get_models_base.py). As a last resort, convert a numeric “created” epoch (UTC) to YYYY-MM-DD.
- provenance
  - The snapshot writer [save_provider_models()](crux_providers/base/get_models_base.py) persists fetched_via and metadata.source. The OpenAI fetcher records “api” and “openai_sdk_enriched” to indicate SDK-originated, enriched listings.

Note: If future endpoints expose explicit token limits per model id, the normalization path will automatically populate context_length without policy changes.

Extending to new providers (checklist)

- Create crux_providers/{provider}/client.py implementing LLMProvider (+ capabilities)
- Add get\_{provider}\_models.py fetcher module with run() entrypoint
- Add factory mapping in [ProviderFactory](crux_providers/base/factory.py)
- Seed via DB helpers or let the fetcher persist snapshots to SQLite
- Add unit tests under crux_providers/tests/

## FAQ

### What is an "adapter" here?

An adapter is the thin implementation class that maps the generic interfaces
(`LLMProvider`, optional capability protocols) onto a specific provider SDK or
HTTP API. Each provider has its own `client.py` containing an adapter class
(`OpenAIProvider`, `AnthropicProvider`, etc.). They:

- Accept a normalized `ChatRequest`
- Translate to provider-specific SDK/HTTP params
- Execute the call (streaming or non-streaming)
- Normalize back into `ChatResponse` / stream events

They intentionally avoid embedding higher-level business logic, formatting, or
retry policy (those will be layered via decorators / resilience modules). This
keeps the providers layer self-contained and clean.

Q: How do I run a minimal end-to-end provider call without wiring the orchestrator?

- Use ProviderFactory + ChatRequest in a small script or a unit test as shown above. No orchestrator changes are required.

Q: What if my JSON registry file is empty and I get errors?

- The repository now tolerates empty/whitespace files and returns an empty snapshot with a warning, but live API refresh is recommended to populate real models:
  python -m crux_providers.openai.get_openai_models

Q: Where should tests go?

- Only under crux_providers/tests/. Test-like scripts in other folders are not allowed by architecture rules.

References

- Factory: [ProviderFactory.create()](crux_providers/base/factory.py)
- OpenAI Adapter: [OpenAIProvider](crux_providers/openai/client.py)
- DTOs: [ChatRequest](crux_providers/base/models.py), [ChatResponse](crux_providers/base/models.py), [Message](crux_providers/base/models.py)
- Registry: [ModelRegistryRepository](crux_providers/base/repositories/model_registry.py)
- Key resolution: [KeysRepository.get_api_key()](crux_providers/base/repositories/keys.py)
- OpenAI fetcher: [get_openai_models.run()](crux_providers/openai/get_openai_models.py)
- Batch refresh utility: `python -m crux_providers.utils.refresh_all_models` (aggregates all provider fetchers; no backward compatibility shim retained)

## Observed Capability Caching (Authoritative)

Purpose
-------
Persist runtime-observed provider capabilities and merge them into the model registry at read time. This removes guesswork and ensures behavior reflects real SDK/HTTP responses.

Data-first Policy
-----------------
- Never infer by model name or regex.
- Persist `true` only on a confirmed success path; persist `false` only on explicit, authoritative rejection by the provider.
- Otherwise, leave capability unspecified (no override), allowing future observations to set it.

What we record (current)
------------------------
- `json_output`: `true` when a structured (JSON) non-stream chat succeeds.
- `structured_streaming`: `false` when the provider explicitly does not support structured streaming for the attempted mode.
- `streaming`: `true` on the first emitted token during a streaming chat.

Persistence and Merge
---------------------
- SQLite-backed storage (authoritative):
  - Table: `observed_capabilities(provider, model_id, feature, value INTEGER, updated_at)`
  - Initialized via `crux_providers.service.db.init_db()`; reused across providers layer.
  - Observations are upserted; writes are best-effort and never block core chat paths.
- Registry merge:
  - `ModelRegistryRepository.list_models()` loads the base snapshot JSON for the provider and overlays observed flags queried via `load_observed()` using `merge_capabilities()`.
  - Observed `true` overrides unknown/absent. Observed `false` only set when explicitly unsupported.
  - No speculative inference is applied during merge.

Edge Cases
----------
- Lack of prior observation leaves capability as-is in the registry snapshot.
- Mid-stream errors after at least one delta still count as `streaming=true` (we observed a token).
- Start-phase timeouts do not produce observations.

Minimal Example (shape only)
----------------------------

```json
{
  "gpt-4o-mini": {
    "json_output": true,
    "structured_streaming": false,
    "streaming": true
  }
}
```

Related Tests
-------------
- Helpers and persistence: `crux_providers/base/tests/test_capabilities_helpers.py`
- Registry merge correctness: `crux_providers/base/tests/test_model_registry_observed_merge.py`

Provider Wiring Notes
---------------------
- OpenAI/Ollama: prior implementations already record observations.
- Anthropic/Gemini: parity added; structured streaming guards set `structured_streaming=false` on explicit rejection.
- Deepseek/XAI: covered via `BaseOpenAIStyleProvider` implementation.

Operational Guidance
--------------------
- Observed data lives in SQLite; to reset, delete the providers DB or use a fresh temp DB in tests. The cache will repopulate as features are exercised.
- Do not hand-edit database rows in normal workflows; use provider calls that record observations.

### Logging levels (providers layer)

The providers logging utility (`crux_providers.base.logging.get_logger`) honors the environment variable `PROVIDERS_LOG_LEVEL` to control verbosity without code changes.

- Accepted values (case-insensitive): `DEBUG`, `INFO` (default), `WARNING`, `ERROR`, `CRITICAL`.
- At `DEBUG`, the streaming adapter emits per-delta normalized log events in addition to the final summary event.
- At `INFO` and above, only the final "finalize" summary record is emitted by the adapter to avoid noise.

Example (temporary verbose logs):

```bash
export PROVIDERS_LOG_LEVEL=DEBUG
python -m pytest -q crux_providers/tests
# reset
unset PROVIDERS_LOG_LEVEL
```

### Streaming (experimental)

Added a minimal streaming contract and OpenAI implementation.

Usage:

```python
from crux_providers.base.models import ChatRequest, Message
from crux_providers.base.streaming_adapter import StreamController, BaseStreamingAdapter

# Example pseudo-code integrating streaming with cancellation & IDs
adapter = BaseStreamingAdapter(
  ctx=LogContext(provider="openai", model="gpt-4o"),
  provider_name="openai",
  model="gpt-4o",
  starter=lambda: openai_stream_start(...),  # may return (stream, {"request_id": rid, "response_id": sid})
  translator=translate_openai_chunk,
  retry_config_factory=lambda phase: build_retry_config(phase=phase),
  logger=get_logger(),
)
controller = StreamController(adapter)
for evt in controller:
  if evt.finish:
    print("done", evt.error)
  elif evt.delta:
    print(evt.delta, end="")

# Cooperative cancellation from another thread / signal handler:
controller.cancel("user aborted")

```

#### Streaming Adapter Starter Return Shapes (Authoritative)

The `BaseStreamingAdapter` starter callable (`starter`) may return one of the following shapes:

1. `stream` iterable/generator yielding native SDK chunks.
2. `(stream, meta_dict)` tuple where `meta_dict` is a mapping that may include:
   - `request_id`: Upstream correlation id (only set on context if absent)
   - `response_id`: Provider response id (propagated similarly)
3. Mapping with mandatory key `"stream"` plus optional `request_id` / `response_id` keys:
   `{"stream": stream, "request_id": "req-123", "response_id": "resp-456"}`

Anything else (e.g., mapping missing `stream`, tuple second element not a mapping) triggers a `ProviderError` with code `internal` which is surfaced as a single terminal stream event whose `error` field begins with `"internal:"`.

#### INTERNAL Guard Semantics

`internal` denotes invariant / contract violations that are not user-actionable (adapter misuse or unexpected starter shape). Tests covering this path:

- `test_stream_internal_error.py` (starter mapping missing `stream`) ensures we do not silently accept malformed returns.

#### Finalize / Terminal Event Behavior

Exactly one terminal `ChatStreamEvent` is emitted per stream (success or error). Success terminal events have:

- `finish=True`
- `error=None`

Error terminal events have:

- `finish=True`
- `error` string formatted as `"<error_code>:<truncated_message>"`

Metrics captured (internal, serialized in finalize path):

- `emitted_count` (# deltas)
- `emitted` (bool convenience flag: emitted_count > 0)
- `time_to_first_token_ms`
- `total_duration_ms`

#### Translator Isolation

Exceptions raised inside the translator are suppressed (delta skipped) to avoid destabilizing the stream. Mid-stream error tests inject exceptions via the underlying iterator instead of translator exceptions.

#### Cancellation

Cooperative cancellation uses a `CancellationToken` checkpoint before processing each native chunk and once after normal iteration. Cancelled streams emit a terminal error with `error` beginning `"cancelled:"` (distinct from `timeout`).

#### Troubleshooting Starter Issues

| Symptom | Likely Cause | Resolution |
|---------|--------------|-----------|
| Immediate terminal event `internal:starter() mapping missing 'stream' key` | Starter returned mapping without `stream` | Return one of the accepted shapes with a `stream` key |
| `internal:starter() second element must be mapping...` | Tuple second element not a mapping | Provide a dict for meta or switch to mapping form |
| No deltas, success terminal only | Translator returned `None` for every chunk or source produced no chunks | Verify native stream yields chunks and translator logic |
| Missing `request_id` in logs | Starter did not supply meta or value already set on context | Provide meta dict with `request_id` if correlation needed |

#### Logging Normalization

Finalize helper emits structured JSON log containing (subset): `event`, `provider`, `model`, `phase=finalize`, `error_code`, `emitted`, `emitted_count`, `time_to_first_token_ms`, `total_duration_ms`. Internal tests (`test_stream_contract_logging*.py`) assert these invariants.

##### Finalize Log Examples

Success (tokens emitted):

```json
{
  "event": "stream.adapter.end",
  "provider": "openai",
  "model": "gpt-4o",
  "phase": "finalize",
  "error_code": null,
  "emitted": true,
  "emitted_count": 27,
  "time_to_first_token_ms": 142,
  "total_duration_ms": 1280,
  "request_id": "req_abc123",
  "response_id": "resp_def456"
}
```

Internal error (starter shape violation — no deltas):

```json
{
  "event": "stream.adapter.error",
  "provider": "openai",
  "model": "gpt-4o",
  "phase": "finalize",
  "error_code": "internal",
  "emitted": false,
  "emitted_count": 0,
  "time_to_first_token_ms": null,
  "total_duration_ms": 3,
  "error": "internal:starter() mapping missing 'stream' key"
}
```

##### Metrics Interpretation

- `emitted_count`: Number of deltas produced (proxy for token / chunk count; exact token count intentionally not inferred).
- `emitted`: Convenience boolean (`emitted_count > 0`).
- `time_to_first_token_ms`: Latency from adapter start until first successful delta emission. `null` when no deltas.
- `total_duration_ms`: Wall-clock duration from start until finalize (success or error). Always non-null.
- `error_code`: Canonical classification (`internal`, `cancelled`, `timeout`, provider-specific, or null on success).

Invariant checks (enforced in tests / recommended for monitors):
- If `emitted` is false then `emitted_count == 0` and `time_to_first_token_ms` is null.
- If `emitted` is true then `time_to_first_token_ms` is a positive integer less than or equal to `total_duration_ms`.
- Exactly one finalize log per stream (idempotent terminal emission).

Operational Use:
- Alert if `internal` appears (indicates contract misuse) more than a minimal threshold.
- Track P95 `time_to_first_token_ms` to spot upstream latency regressions.
- Compare `total_duration_ms - time_to_first_token_ms` distribution to understand steady-state streaming throughput.

---

### Token Accounting (Issue #59)

Current State
-------------
Providers (OpenAI, Anthropic) now attach a stable placeholder mapping under
`ProviderMetadata.extra['token_usage']` for every non-stream chat response:

```json
{"prompt": null, "completion": null, "total": null}
```

Rationale:
- Downstream logging/metrics pipelines and forthcoming analytics dashboards
  require a consistent key even before real token counts are available.
- Avoids conditional logic sprinkled across callers; presence is guaranteed,
  values may be `null` until SDK surfaces counts.

Future Plan:
1. Upgrade OpenAI and Anthropic client integrations to capture real usage
   fields once the unified response objects are adopted (prompt/completion/total).
2. Populate `StreamMetrics` token fields during streaming finalization when
   providers emit usage post-hoc.
3. Remove placeholder comment blocks and update this section with examples
   of real token accounting output.

Contract Invariants:
- Keys `prompt`, `completion`, `total` always present.
- Values may be `null` but never omitted.
- Additional provider-specific usage metrics (e.g., cached / reasoning tokens)
  will be introduced under a sibling mapping (`token_usage_details`) rather
  than mutating the base keys.

Testing / Diagnostics:
- TODO markers in `openai/client.py` and `anthropic/client.py` note where a
  future test harness should assert presence & shape.
- Placeholder presence verified implicitly by integration paths relying on
  `meta.extra['token_usage']` existence.

Security & Privacy:
- No sensitive values inserted; numbers only once implemented.
- Placeholder introduces zero PII risk.

This scaffolding completes Issue #59 for multi-provider parity; future work
will replace `null` values without changing the external contract.

### Datetime Storage & Normalization Policy (SQLite Repos)

Rationale
---------
Python 3.12+ deprecates (and in future versions may remove) implicit reliance on
`sqlite3`'s legacy datetime adapter/converter pair. Implicit conversion created
latent ambiguity (naive vs. timezone-aware) and produced warnings when upgrading
interpreters. To enforce explicit, portable semantics the persistence layer now
stores all repository timestamps that originate from runtime events (metrics
and chat logs) as ISO8601 strings with a timezone designator.

Authoritative Rules
-------------------
1. Creation Timestamp Storage:
   - `metrics.created_at` & `chat_logs.created_at` are persisted as the result of
     `datetime.isoformat()`.
   - If a supplied `datetime` is naive (`tzinfo is None`), it is treated as UTC
     and a `tzinfo=timezone.utc` is injected before serialization (backward
     compatibility with legacy call sites that constructed naive values).
2. Parsing on Read:
   - Centralized in `_parse_created_at` inside
     `persistence/sqlite/repos.py` which returns an aware `datetime` in UTC.
   - On malformed / unexpected values (e.g., manual DB edits) the parser falls
     back to Unix epoch UTC (`1970-01-01T00:00:00Z`) to keep higher layers
     resilient. This fallback is intentional and test-covered.
3. Engine Configuration:
   - `engine.py` no longer enables `detect_types=sqlite3.PARSE_DECLTYPES` to
     avoid the legacy adapter influencing future reads; rows are consumed as
     raw Python primitives (strings) and parsed explicitly.
4. Scope:
   - Only the *metrics* and *chat log* repositories participate. Other tables
     (e.g., `prefs.updated_at`) that rely on `CURRENT_TIMESTAMP` may still
     return strings; they are parsed locally where needed.
5. Timezone Uniformity:
   - All returned `created_at` values from repository public methods are
     guaranteed to be timezone-aware (UTC). Callers should never receive naive
     datetimes.

Failure Modes & Defensive Posture
---------------------------------

| Scenario | Example Stored Value | Result from `_parse_created_at` | Notes |
|----------|----------------------|---------------------------------|-------|
| Proper aware ISO | `2025-09-16T18:22:04.123456+00:00` | Same object | Round-trip |
| Naive ISO | `2025-09-16T18:22:04.123456` | UTC-aware version | Backfill tz |
| Malformed | `not-a-date` | Epoch UTC | Logged only at higher layers if needed |
| Already `datetime` naive | `datetime(2025,9,16,18,22,4)` | UTC-aware | Defensive |

Testing Guarantees
------------------
Dedicated tests cover:
- Naive -> aware coercion on write & read (metrics repo normalization test)
- Parser handling of: aware ISO, naive ISO, malformed string, existing aware
  `datetime`, naive `datetime` object

Migration / Legacy Considerations
---------------------------------
Existing deployments that previously relied on sqlite's implicit adapter may
contain naive text representations. The current policy already coerces those to
UTC on first read (no destructive migration required). A future optional
backfill script may rewrite legacy rows to explicit `+00:00` suffixed strings;
until then the parser path ensures consistent behavior.

Backfill Utility (Optional)

An idempotent maintenance helper now exists at
`crux_providers/persistence/sqlite/backfill_timestamps.py` to rewrite legacy naive
`created_at` values in-place so external inspection (e.g., manual SQLite shell,
ETL exports) reflects explicit UTC offsets. It supports a dry-run scan and an
`--apply` mode with confirmation. Example:

```bash
python -m crux_providers.persistence.sqlite.backfill_timestamps --db /path/to/providers.db  # dry-run
ython -m crux_providers.persistence.sqlite.backfill_timestamps --apply --yes               # apply changes
```

If no legacy rows are found the script exits success without modifying data.
Re-running after a successful apply reports zero legacy rows.

Exit Codes:
- 0 – Success (no legacy rows found in dry-run OR successful apply)
- 2 – User aborted at confirmation prompt
- 3 – Legacy rows detected during dry-run (no changes performed). This enables CI workflows to gate merges if historical naive timestamps remain.

JSON Output Mode
----------------
For automation or programmatic inspection pass `--json`. The script will emit
one JSON object per invocation (dry-run only, or dry-run + apply combined into
two separate invocations if you call it twice). Example:

```bash
python -m crux_providers.persistence.sqlite.backfill_timestamps --json
```

Sample output:

```json
{
  "phase": "dry_run",
  "tables": [
    {"table": "metrics", "scanned": 2, "legacy_naive": 1, "updated": 0},
    {"table": "chat_logs", "scanned": 2, "legacy_naive": 1, "updated": 0}
  ],
  "totals": {"legacy_naive": 2, "updated": 0}
}
```

Apply with JSON (non-interactive) runs:

```bash
python -m crux_providers.persistence.sqlite.backfill_timestamps --apply --yes --json
```

Which now produces a single JSON document that embeds the original dry-run results:

```json
{
  "phase": "applied",
  "tables": [
    {"table": "metrics", "scanned": 2, "legacy_naive": 1, "updated": 1},
    {"table": "chat_logs", "scanned": 2, "legacy_naive": 1, "updated": 1}
  ],
  "totals": {"legacy_naive": 2, "updated": 2},
  "dry_run": {
    "phase": "dry_run",
    "tables": [
      {"table": "metrics", "scanned": 2, "legacy_naive": 1, "updated": 0},
      {"table": "chat_logs", "scanned": 2, "legacy_naive": 1, "updated": 0}
    ],
    "totals": {"legacy_naive": 2, "updated": 0}
  }
}
```

When there are zero legacy rows, the applied document still includes per-table entries with zero counts for consistent parsing.

Caller Guidance
---------------
- Do not attempt custom parsing of `created_at`; rely on repository return
  objects.
- When constructing new repository entries, prefer creating timezone-aware
  datetimes via `datetime.now(timezone.utc)`.
- Treat any epoch UTC value in telemetry dashboards as a signal of malformed or
  manually edited data.

Future Enhancements
-------------------
Potential future evolution includes surfacing a structured warning counter for
malformed timestamps to aid operational visibility and adding an optional
lightweight migration utility to rewrite legacy naive rows in-place.

JSON Schema Exposure (`--print-schema`)
--------------------------------------
For consumers that wish to lock the JSON contract in CI, the backfill utility
exposes its output schema (Draft 2020-12) via:

```bash
python -m crux_providers.persistence.sqlite.backfill_timestamps --print-schema > backfill_report.schema.json
```

Characteristics:
- Stable top-level keys: `phase`, `tables`, `totals`; applied payloads embed prior dry-run under `dry_run`.
- `phase` is either `dry_run` or `applied`.
- `tables` is an array of per-table objects: `{table, scanned, legacy_naive, updated}`.
- `totals` aggregates `legacy_naive` and `updated` across tables.
- Applied payload adds `dry_run` object capturing the original scan (idempotent audit trail).
- Schema is embedded inline (`_SCHEMA` constant) to avoid drift between code and documentation.

Recommended CI Pattern:
1. Cache schema (commit the artifact) or regenerate each run.
2. Execute dry-run with `--json`; parse and ensure only expected keys are present.
3. Treat unexpected structural changes as a breaking change requiring review/version bump.

Example inspection of per-table item shape with `jq`:

```bash
python -m crux_providers.persistence.sqlite.backfill_timestamps --print-schema | jq '.properties.tables.items.properties'
```

Exit Behavior:
- `--print-schema` always exits 0 (no DB access required).
- All other exit codes (0/2/3) remain unchanged.

##### Error Code Reference (Streaming Finalize)

| error_code | When Emitted | Example Error String Prefix | Remediation / Notes |
|------------|--------------|-----------------------------|---------------------|
| (null) | Successful stream completion | (no error field) | Normal termination. |
| internal | Adapter / contract violation (starter shape, meta misuse) | `internal:starter() mapping missing 'stream' key` | Inspect adapter implementation; should be rare. |
| cancelled | Cooperative cancellation via `CancellationToken` | `cancelled:user aborted` | Expected when user aborts; not a provider fault. |
| timeout | Start-phase timeout (no tokens) | `timeout:operation timed out` | Investigate upstream latency; adjust timeout config if justified. |
| transient | Transient network/IO error surfaced after retries exhausted | `transient:...` | Usually retryable; monitor frequency. |
| rate_limit | Provider rate limiting after retries | `rate_limit:...` | Consider backoff tuning or quota increase. |
| <provider_specific> | Classified provider error code (future / SDK mapped) | `bad_request:...` | Handle per provider semantics. |

Notes:
- `cancelled` is distinct from `timeout`; cancellation is user/system initiated, timeout is passive elapsed start-phase limit.
- Mid-stream failures after at least one delta will still carry the classified error code (`timeout` will not occur mid-stream under current policy—only start phase is timeout guarded).
- Providers may enrich token usage placeholders in future; error code taxonomy remains stable for log aggregation.
