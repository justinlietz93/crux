# Anthropic Provider Guidelines

Folder boundaries

- Files allowed: `client.py` (≤500 LOC). Optional: a small `helpers.py` (≤250 LOC) if absolutely provider-specific.
- Prohibited: Any `_*.py` files. No bespoke streaming loops.

Client/SDK

- Use `anthropic.Anthropic` with API key precedence (env/config → argument). Keep client creation centralized in `_create_client()`.

Chat & streaming

- Non-stream: map `ChatRequest` to `client.messages.create`; normalize to `ChatResponse`.
- Streaming: use `BaseStreamingAdapter`; implement an event translator that yields text deltas only.

Timeouts & retries

- Use `get_timeout_config()` + `operation_timeout` for start phases. Use centralized retry via `RetryConfig`/`retry()`.

Logging & errors

- Use `normalized_log_event`; classify exceptions with `classify_exception`. One log per fallback trigger.

Token usage

- Until the SDK exposes counts, attach a placeholder token_usage dict in `ProviderMetadata.extra` with `prompt`, `completion`, `total` set to `None`.

Persistence

- Observed capabilities are stored in SQLite via the model registry; never write JSON snapshots.

Security & quality

- No `shell=True`; validate paths if subprocess ever used (avoid here). Full docstrings required on public classes/functions. Providers-only Codacy clean.
