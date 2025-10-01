"""
Helper utilities for OpenAI-style Chat Completions providers.

Purpose:
- Centralize small, reusable helper functions used by OpenAI-compatible
  providers to keep the main base class concise and under the 500 LOC policy.
- Provide safe translations between our DTOs and OpenAI-style SDK params.
- Encapsulate response extraction and error classification for SDK invocations.

External dependencies:
- Relies on provider DTOs (``ChatRequest``) and utilities (``extract_system_and_user``).
- Uses provider error taxonomy (``ProviderError``, ``ErrorCode``, ``classify_exception``).
- No direct network I/O; functions only prepare inputs or interpret outputs.

Fallback semantics:
- ``invoke_create`` re-raises timeout exceptions to allow upstream timeout guards
  to handle them. Non-timeout exceptions are classified and wrapped in
  ``ProviderError`` with retryability encoded by ``ErrorCode``.

Timeout strategy:
- This module does not set timeouts. Callers must wrap start phases using
  ``operation_timeout`` from the timeouts module.
"""

from __future__ import annotations

import asyncio
import typing as _t

from ..models import ChatRequest
from ..utils.messages import extract_system_and_user
from ..errors import ProviderError, ErrorCode, classify_exception


def extract_openai_text(resp: _t.Any) -> str:
    """Extract assistant text from an OpenAI-style non-streaming response.

    The function uses a narrow attribute access pattern to avoid brittle
    introspection. If the expected attributes are missing, an empty string is
    returned.

    Parameters:
        resp: The raw SDK response object returned by the chat completions API.

    Returns:
        The assistant message content as a string, or an empty string if not found.
    """
    try:
        return resp.choices[0].message.content  # type: ignore[attr-defined,index]
    except Exception:
        return ""


def prepare_response_format(request: ChatRequest) -> tuple[dict | None, bool]:
    """Translate our DTO fields into the OpenAI ``response_format`` parameter.

    If ``json_schema`` is provided, returns the structured schema form.
    Otherwise, when ``response_format == 'json_object'``, returns the shorthand
    JSON object spec. The second tuple element indicates if a structured
    response was requested.

    Parameters:
        request: The high-level chat request DTO.

    Returns:
        A tuple ``(response_format_param, is_structured)`` where
        ``response_format_param`` is either a dict or ``None``.
    """
    if request.json_schema:
        return {"type": "json_schema", "json_schema": request.json_schema}, True
    if request.response_format == "json_object":
        return {"type": "json_object"}, True
    return None, False


def extract_messages_and_format(request: ChatRequest) -> tuple[list[dict], dict | None, bool]:
    """Build OpenAI-style messages and compute response format flags.

    Parameters:
        request: The chat request containing our normalized message list and
            optional structured output directives.

    Returns:
        A tuple of ``(messages, response_format, is_structured)`` where
        ``messages`` is a list of dicts suitable for OpenAI-style SDKs,
        ``response_format`` is the translated parameter (or ``None``), and
        ``is_structured`` indicates a structured response was requested.
    """
    system_message, user_content = extract_system_and_user(request.messages)
    messages: list[dict] = []
    if system_message:
        messages.append({"role": "system", "content": system_message})
    if user_content:
        messages.append({"role": "user", "content": user_content})
    is_structured = request.response_format == "json_object"
    if request.json_schema:
        response_format: dict | None = {
            "type": "json_schema",
            "json_schema": request.json_schema,
        }
    elif is_structured:
        response_format = {"type": "json_object"}
    else:
        response_format = None
    return messages, response_format, is_structured


def build_chat_params(
    model: str,
    messages: list[dict],
    request: ChatRequest,
    response_format: dict | None,
) -> dict:
    """Assemble parameters for an OpenAI-style chat completion call.

    Parameters:
        model: The model identifier string.
        messages: The messages payload for the API.
        request: The original request with optional generation parameters.
        response_format: Optional ``response_format`` parameter.

    Returns:
        A dict suitable for ``client.chat.completions.create(**params)``.
    """
    params: dict = {"model": model, "messages": messages}
    if request.max_tokens is not None:
        params["max_tokens"] = int(request.max_tokens)
    if request.temperature is not None:
        params["temperature"] = float(request.temperature)
    if response_format:
        params["response_format"] = response_format
    if request.tools:
        params["tools"] = request.tools
    return params


def build_stream_params(
    model: str,
    messages: list[dict],
    request: ChatRequest,
    response_format: dict | None,
) -> dict:
    """Assemble parameters for an OpenAI-style streaming chat call.

    This mirrors :func:`build_chat_params` but ensures ``stream=True`` is set
    and keeps the parameter construction centralized for both streaming and
    non-streaming paths.

    Parameters:
        model: The model identifier string.
        messages: The messages payload for the API.
        request: The original request with optional generation parameters.
        response_format: Optional ``response_format`` parameter.

    Returns:
        A dict suitable for ``client.chat.completions.create(**params)`` with
        streaming enabled.
    """
    params = build_chat_params(model, messages, request, response_format)
    params["stream"] = True
    return params


def invoke_create(client: _t.Any, params: dict, model: str, provider_name: str) -> _t.Any:
    """Invoke ``chat.completions.create`` with robust error classification.

    The function calls the SDK without altering timeout behavior; callers are
    expected to guard the start phase as needed. Timeout exceptions are
    propagated as-is. Other exceptions are classified and wrapped in
    ``ProviderError`` carrying retryability metadata.

    Parameters:
        client: The OpenAI-style SDK client exposing ``chat.completions.create``.
        params: The parameters dict for the API call.
        model: The target model name (used for error context).
        provider_name: The canonical provider identifier for error context.

    Returns:
        The raw SDK response.

    Raises:
        TimeoutError: Re-raised to be handled by upstream timeout guards.
        ProviderError: For non-timeout failures, with ``retryable`` set based on
            the classified ``ErrorCode``.
    """
    try:
        return client.chat.completions.create(**params)
    except Exception as e:  # noqa: BLE001
        # Allow timeout exceptions to bubble up to the outer timeout guard
        if isinstance(e, (TimeoutError, asyncio.TimeoutError)):
            raise
        code = classify_exception(e)
        raise ProviderError(
            code=code,
            message=str(e),
            provider=provider_name,
            model=model,
            retryable=code
            in (ErrorCode.TRANSIENT, ErrorCode.RATE_LIMIT, ErrorCode.TIMEOUT),
            raw=e,
        ) from e
