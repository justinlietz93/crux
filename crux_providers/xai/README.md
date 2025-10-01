# Rules for xAI Provider

Folder boundaries

- Files allowed: `client.py` (≤500 LOC). Optional: `helpers.py` (≤250 LOC) only if provider-specific.
- Prohibited: `_*.py` files. No bespoke streaming loops.

Client/HTTP

- Use `get_httpx_client` with base URL from config; set `Authorization` header.

Chat & streaming

- Non-stream: map `ChatRequest` to xAI chat API; normalize to `ChatResponse`.
- Streaming: must use `BaseStreamingAdapter`; if xAI uses OpenAI-compatible SSE, reuse translator; otherwise add a minimal translator.
- Structured streaming: ALLOWED only if API supports JSON deltas; otherwise, reject early.

Timeouts & retries

- Use `get_timeout_config()` + `operation_timeout`; use centralized `retry()`; no hard-coded numeric timeouts.

Logging & errors

- Use `normalized_log_event`; classify exceptions with `classify_exception`.

Persistence

- Observed capabilities are DB-only; no JSON snapshots.
