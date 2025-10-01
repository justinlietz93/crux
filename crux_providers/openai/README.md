# OpenAI Provider Guidelines

Folder boundaries

- Files allowed: `client.py` (≤500 LOC). Optional: `helpers.py` (≤250 LOC) only if provider-specific.
- Prohibited: `_*.py` files. No bespoke streaming loops.

Client/HTTP

- Use SDK or `get_httpx_client` with base_url from config; set `Authorization: Bearer <key>`.

Chat & streaming

- Non-stream: map `ChatRequest` to OpenAI Chat Completions; normalize to `ChatResponse`.
- Streaming: must use `BaseStreamingAdapter` with OpenAI SSE translator.
- Structured streaming: ALLOWED per OpenAI capability; ensure translator composes JSON safely or surface terminal error if invalid.

Timeouts & retries

- Use `get_timeout_config()` + `operation_timeout`; use centralized `retry()`; no hard-coded numeric timeouts.

Logging & errors

- Use `normalized_log_event`; classify exceptions with `classify_exception`.

Persistence

- Observed capabilities are stored in SQLite via the model registry; do not write JSON snapshots.
