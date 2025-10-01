# OpenRouter Provider Guidelines

Folder boundaries

- Files allowed: `client.py` (≤500 LOC). Optional: `helpers.py`, `chat_helpers.py`, `stream_helpers.py` (each ≤250 LOC).
- Prohibited: Any files starting with `_` (e.g., `_chat.py`, `_common.py`). No bespoke streaming loops.

Streaming

- Must use `BaseStreamingAdapter`; provide a translator that decodes OpenAI-style SSE deltas.
- Structured streaming: DISALLOWED for OpenRouter. If `json_object`/`json_schema`/tools are requested on stream, short-circuit with a terminal error.

Timeouts & retries

- Use `get_timeout_config()` + `operation_timeout` for start phases. Use centralized `retry()`; no hard-coded numeric timeouts.

HTTP

- Use `get_httpx_client` with OpenRouter base_url and `Authorization: Bearer <key>` headers.

Logging & errors

- Use `normalized_log_event`; classify exceptions with `classify_exception`. One log per fallback trigger.

Persistence

- Observed capabilities are stored in SQLite via the model registry; never write JSON snapshots.

Security & quality

- No `shell=True`; validate paths if subprocess is ever used (avoid here). Full docstrings required on public classes/functions. Keep providers-only Codacy clean.
