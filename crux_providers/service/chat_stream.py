from __future__ import annotations

"""
FastAPI streaming chat route for Crux provider service.

Purpose
-------
Expose `/api/chat/stream` as an NDJSON streaming endpoint that reuses the
existing chat DTOs, request builders, and provider adapters without
introducing duplicate DTOs or logic in the service layer.

External dependencies
---------------------
- FastAPI (routing, dependency injection, StreamingResponse).
- Existing Crux providers primitives:
  - DTO validation: ChatRequestDTO / MessageDTO via `_validate_body_as_dto`.
  - Request construction: `build_chat_request`.
  - Provider resolution: `_create_adapter_or_raise` (ProviderFactory).
  - Key resolution: `set_env_for_provider`.
  - Streaming contract: `SupportsStreaming`, `ChatStreamEvent`.

Fallback semantics
------------------
- If the provider does not support streaming, return HTTP 400 with a clear
  error message—no silent fallback to non-streaming.
- If the streaming loop raises, emit a final NDJSON event with `type="error"`
  and `finish=True` so the client can terminate cleanly.

Timeout strategy
----------------
- This module does not enforce timeouts directly. Provider adapters are
  expected to use the shared timeout configuration and streaming helpers.
  HTTP-level timeouts are the responsibility of the hosting server (uvicorn)
  and upstream clients.
"""

import json
from typing import Iterator

from fastapi import Depends, HTTPException
from fastapi.responses import StreamingResponse

from crux_providers.base.interfaces_parts.supports_streaming import SupportsStreaming
from crux_providers.base.streaming import ChatStreamEvent
from crux_providers.persistence.interfaces.repos import IUnitOfWork
from crux_providers.service.app import app
from crux_providers.service.app_parts.app_core import (
    ChatBody,
    _create_adapter_or_raise,
    _validate_body_as_dto,
    get_uow_dep,
)
from crux_providers.service.helpers import build_chat_request, set_env_for_provider
from pydantic import ValidationError


@app.post("/api/chat/stream")
def post_chat_stream(
    body: ChatBody,
    uow: IUnitOfWork = Depends(get_uow_dep),
) -> StreamingResponse:
    """Stream chat responses as NDJSON events.

    This controller mirrors the validation and adapter resolution flow of the
    existing `/api/chat` endpoint but exposes an NDJSON streaming interface
    backed by provider `stream_chat` implementations.

    Request body:
        Reuses `ChatBody` from `service.app`, which is validated into a
        `ChatRequestDTO` via `_validate_body_as_dto` before building a
        domain `ChatRequest` using `build_chat_request`.

    Behavior:
        - Ensures provider API keys are surfaced to SDKs via
          `set_env_for_provider`.
        - Resolves the adapter using `_create_adapter_or_raise`.
        - Validates the incoming body strictly via `_validate_body_as_dto`
          (400 on validation error).
        - Requires the adapter to implement `SupportsStreaming` and have
          `supports_streaming() == True` (400 otherwise).
        - Streams `adapter.stream_chat(request)` into NDJSON events with
          `{type, delta, structured, finish, error}` fields.

    Error handling:
        - Validation failures → HTTP 400 with Pydantic error details.
        - Non-stream-capable providers → HTTP 400 with a clear message.
        - Unexpected exceptions during the streaming loop → a final NDJSON
          event with `type="error"` and `finish=True`.
    """
    # Ensure provider SDKs receive keys from the Crux key vault.
    set_env_for_provider(body.provider, uow=uow)

    # Resolve adapter and strictly validate request body via DTOs.
    adapter = _create_adapter_or_raise(body.provider)
    try:
        _ = _validate_body_as_dto(body)
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=e.errors()) from e

    # Enforce streaming capability at the HTTP boundary.
    if not isinstance(adapter, SupportsStreaming) or not adapter.supports_streaming():
        raise HTTPException(
            status_code=400,
            detail=f"Provider '{body.provider}' does not support streaming chat responses",
        )

    # Build the domain ChatRequest using the shared helper.
    req = build_chat_request(body)

    def iter_ndjson() -> Iterator[bytes]:
        """Yield NDJSON-encoded stream events with clear termination semantics.

        For each `ChatStreamEvent` from the provider adapter, emit a single
        JSON line with shape:

            {
              "type": "delta" | "final" | "error",
              "delta": <text or null>,
              "structured": <dict or null>,
              "finish": <bool>,
              "error": <str or null>
            }

        Invariants:
            - At most one `"final"` or `"error"` event with `finish=True`.
            - If an exception escapes the adapter loop, emit a single terminal
              `"error"` event and stop iteration.
        """
        try:
            for ev in adapter.stream_chat(req):
                error = getattr(ev, "error", None)
                finish = bool(getattr(ev, "finish", False))

                if error is not None:
                    event_type = "error"
                elif finish:
                    event_type = "final"
                else:
                    event_type = "delta"

                structured = getattr(ev, "structured", None)
                if structured is not None and hasattr(structured, "to_dict"):
                    structured = structured.to_dict()

                chunk = {
                    "type": event_type,
                    "delta": getattr(ev, "delta", None),
                    "structured": structured,
                    "finish": finish,
                    "error": error,
                }
                yield (json.dumps(chunk) + "\n").encode("utf-8")
        except Exception as exc:  # pragma: no cover - defensive
            fallback = {
                "type": "error",
                "delta": None,
                "structured": None,
                "finish": True,
                "error": str(exc),
            }
            yield (json.dumps(fallback) + "\n").encode("utf-8")

    return StreamingResponse(iter_ndjson(), media_type="application/x-ndjson")