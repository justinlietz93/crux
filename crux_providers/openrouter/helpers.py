"""Common helpers for the OpenRouter provider.

Purpose:
    Provide small, focused helpers shared by chat and streaming paths to keep
    the main provider module compact and compliant with the repository file
    size policy (<= 500 LOC per file).

External dependencies:
    - None directly; utilities from the providers base packages are imported
      by callers as needed.

Notes:
    These helpers assume the consumer is an instance that provides attributes:
    ``_api_key`` (str|None), ``_system_message`` (str|None).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..base.utils.messages import extract_system_and_user
from ..base.models import ChatRequest
from ..base.openai_style_parts.style_helpers import prepare_response_format


class OpenRouterCommonMixin:
    """Mixin offering shared payload/header builders for OpenRouter.

    Consumers must define ``_api_key`` and ``_system_message`` attributes.
    """

    def _build_response_format(self, request: ChatRequest, is_structured: bool) -> Dict[str, Any] | None:
        """Construct the provider ``response_format`` segment using shared helper.

        Delegates to ``prepare_response_format`` to ensure consistency with
        OpenAI-style providers and reduce duplication across adapters.
        """
        rf, _ = prepare_response_format(request)
        return rf

    def _build_messages(self, request: ChatRequest) -> List[Dict[str, Any]]:
        """Translate ``ChatRequest.messages`` to OpenAI-style message dicts.

        Parameters:
            request: The chat request including message parts.

        Returns:
            List of role-content dicts including optional system prompt and a
            user message built via ``extract_system_and_user``.
        """
        system_message, user_content = extract_system_and_user(request.messages)
        messages: List[Dict[str, Any]] = []
        sys_msg = system_message or getattr(self, "_system_message", None)
        if sys_msg:
            messages.append({"role": "system", "content": sys_msg})
        messages.append({"role": "user", "content": user_content})
        return messages

    def _build_payload(
        self,
        model: str,
        messages: List[Dict[str, Any]],
        request: ChatRequest,
        response_format: Dict[str, Any] | None,
        stream: bool = False,
    ) -> Dict[str, Any]:
        """Assemble the JSON payload for chat/completions.

        Parameters:
            model: Target model identifier.
            messages: OpenAI-compatible messages list.
            request: Original request with generation parameters.
            response_format: Optional structured output spec.
            stream: Whether server-sent streaming responses are requested.

        Returns:
            A mapping suitable for POST body serialization.
        """
        payload: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            **({"max_tokens": request.max_tokens} if request.max_tokens is not None else {}),
            **({"temperature": request.temperature} if request.temperature is not None else {}),
        }
        if stream:
            payload["stream"] = True
        if response_format:
            payload["response_format"] = response_format
        if request.tools:
            payload["tools"] = request.tools
        return payload

    def _build_headers(self) -> Dict[str, str]:
        """Build HTTP headers including authorization when available.

        Returns:
            Mapping of headers; includes ``Authorization`` if API key present.
        """
        headers: Dict[str, str] = {}
        api_key: Optional[str] = getattr(self, "_api_key", None)
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        return headers

__all__ = ["OpenRouterCommonMixin"]
