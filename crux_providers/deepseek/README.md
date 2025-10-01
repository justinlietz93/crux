# DeepSeek Provider Guidelines

Folder boundaries

- Files allowed: `client.py` (≤500 LOC). Optional: `helpers.py` (≤250 LOC) only if provider-specific.
- Prohibited: `_*.py` files. No bespoke streaming loops.

Client/HTTP

- Use `get_httpx_client` with base URL from config; set API key header if required.

Chat & streaming

- Non-stream: map `ChatRequest` to DeepSeek chat API; normalize to `ChatResponse`.
- Streaming: must use `BaseStreamingAdapter` with an OpenAI-style translator if API is compatible; otherwise, add a minimal DeepSeek translator.
- Structured streaming: ALLOWED only if API supports structured deltas; otherwise, surface “unsupported” early.

Timeouts & retries

- Use `get_timeout_config()` + `operation_timeout`; use centralized `retry()`; no hard-coded numeric timeouts.

Logging & errors

- Use `normalized_log_event`; classify exceptions with `classify_exception`.

Persistence

- Observed capabilities are stored in SQLite via the model registry; do not write JSON snapshots.
