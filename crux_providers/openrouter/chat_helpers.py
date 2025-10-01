"""Chat helpers for the OpenRouter provider.

Encapsulates non-streaming chat orchestration and error handling so that the
main provider module remains focused and within file size limits.
"""

from __future__ import annotations

import json
import time
from typing import Any, Dict, Optional

from ..base.errors import ErrorCode, ProviderError, classify_exception
from ..base.logging import LogContext, normalized_log_event
from ..base.models import ChatRequest, ChatResponse, ContentPart, ProviderMetadata
from ..base.resilience.retry import retry
from ..base.http import get_httpx_client


class OpenRouterChatMixin:
    """Mixin providing chat execution and response building."""

    def _prepare_chat_http(self, model: str, request: ChatRequest, is_structured: bool):
        """Create ``(payload, headers)`` tuple for a chat request."""
        response_format = self._build_response_format(request, is_structured)
        messages = self._build_messages(request)
        payload = self._build_payload(model, messages, request, response_format)
        headers = self._build_headers()
        return payload, headers

    def _execute_chat(self, payload: Dict[str, Any], headers: Dict[str, str], model: str, ctx: LogContext):
        """Execute the chat POST with retry and return decoded text + latency."""
        t0 = time.perf_counter()
        resp = retry()(self._make_chat_call(payload, headers, model))()
        latency_ms = (time.perf_counter() - t0) * 1000.0
        resp.raise_for_status()
        data = resp.json()
        text = data.get("choices", [{}])[0].get("message", {}).get("content")
        normalized_log_event(
            self._logger,
            "chat.end",
            ctx,
            phase="finalize",
            attempt=None,
            emitted=True,
            tokens=None,
            latency_ms=latency_ms,
        )
        return text, latency_ms

    def _build_chat_response(self, model: str, text: Optional[str], is_structured: bool, ctx: LogContext, latency_ms: float) -> ChatResponse:
        """Construct ``ChatResponse``; parse JSON when structured was requested."""
        meta = ProviderMetadata(
            provider_name=self.provider_name,
            model_name=model,
            latency_ms=latency_ms,
            token_param_used="max_tokens",  # nosec B106 - static string, not a secret
            extra={"is_structured": is_structured},
        )
        if is_structured and text:
            parsed = self._maybe_parse_structured(text, ctx)
            if parsed is not None:
                dumped = json.dumps(parsed)
                return ChatResponse(text=dumped, parts=[ContentPart(type="json", text=dumped)], raw=None, meta=meta)
        parts = [ContentPart(type="text", text=text)] if text else None
        return ChatResponse(text=text or None, parts=parts, raw=None, meta=meta)

    def _make_chat_call(self, payload: Dict[str, Any], headers: Dict[str, str], model: str):
        """Return a callable performing the chat HTTP POST."""

        def _invoke():
            try:
                client = get_httpx_client(self._base_url, purpose="openrouter.chat")
                return client.post(
                    "/chat/completions",
                    json=payload,
                    headers=headers,
                )
            except Exception as e:
                code = classify_exception(e)
                raise ProviderError(
                    code=code,
                    message=str(e),
                    provider=self.provider_name,
                    model=model,
                    retryable=code in (ErrorCode.TRANSIENT, ErrorCode.RATE_LIMIT, ErrorCode.TIMEOUT),
                    raw=e,
                ) from e

        return _invoke

    def _maybe_parse_structured(self, text: str, ctx: LogContext):
        """Attempt to parse structured output; log decode error on failure."""
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            normalized_log_event(
                self._logger,
                "chat.decode_error",
                ctx,
                phase="finalize",
                attempt=None,
                emitted=None,
                tokens=None,
            )
            return None

__all__ = ["OpenRouterChatMixin"]
