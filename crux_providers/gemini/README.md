# Gemini Provider Guidelines

Folder boundaries

- Files allowed: `client.py` (≤500 LOC). Optional: `helpers.py` (≤250 LOC) only if provider-specific.
- Prohibited: `_*.py` files. No bespoke streaming loops.

Client/HTTP/SDK

- Prefer official SDK when stable; otherwise use `get_httpx_client` with API key header.

Chat & streaming

- Non-stream: map `ChatRequest` to Gemini responses; normalize to `ChatResponse`.
- Streaming: must use `BaseStreamingAdapter` with a Gemini translator; no custom loops.
- Structured streaming: ALLOWED only if Gemini returns well-formed JSON chunks. Validate and surface terminal error if invalid.

Timeouts & retries

- Use `get_timeout_config()` + `operation_timeout`; use centralized `retry()`; no hard-coded numeric timeouts.

Logging & errors

- Use `normalized_log_event`; classify exceptions with `classify_exception`.

Persistence

- Observed capabilities are stored in SQLite via the model registry; do not write JSON snapshots.
