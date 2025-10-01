# Rules for Ollama Provider

Folder boundaries

- Files allowed: `client.py` (≤500 LOC). Optional: `helpers.py` (≤250 LOC) only if provider-specific.
- Prohibited: `_*.py` files. No bespoke streaming loops.

Client/HTTP

- Use `get_httpx_client` with base URL from config (typically `http://127.0.0.1:11434`).
- Never log full URLs containing secrets; redact tokens if any custom headers are used.

Chat & streaming

- Non-stream: map `ChatRequest` to Ollama chat API; normalize to `ChatResponse`.
- Streaming: must use `BaseStreamingAdapter`; no custom SSE loops.
- Structured streaming: no strict schema enforcement by Ollama; if requested, only apply soft JSON framing and surface terminal error on invalid JSON.

Harmony support

- Harmony prompt format is supported. Use the base Harmony translator; do not add provider-specific formatting logic.
- Gate Harmony via an explicit flag/config; default to standard message translation.

Timeouts & retries

- Use `get_timeout_config()` + `operation_timeout`; use centralized `retry()`; no hard-coded numeric timeouts.

Logging & errors

- Use `normalized_log_event`; classify exceptions with `classify_exception`.

Persistence

- Observed capabilities are DB-only; no JSON snapshots.
