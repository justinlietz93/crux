"""Convenience helpers for simple provider interactions.

This module provides a small utility to send a plain text prompt through a
provider without manually constructing a full ``ChatRequest``.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..interfaces import HasDefaultModel, LLMProvider
from ..models import ChatRequest, ChatResponse, Message


def simple(
    provider: LLMProvider,
    text: str,
    *,
    model: Optional[str] = None,
    max_tokens: Optional[int] = None,
    temperature: Optional[float] = None,
    response_format: Optional[str] = None,
    json_schema: Optional[Dict[str, Any]] = None,
    tools: Optional[List[Dict[str, Any]]] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> ChatResponse:
    """Send a plain text prompt to a provider with minimal ceremony.

    This helper builds a ``ChatRequest`` containing a single ``user`` message
    with ``text`` and invokes ``provider.chat``. If ``model`` is not provided
    and the provider implements :class:`HasDefaultModel`, the provider's
    ``default_model()`` will be used. If neither is available, a
    ``ValueError`` is raised to prevent accidental usage with an undefined
    model.

    Parameters
    - provider: Instance implementing :class:`LLMProvider`.
    - text: Prompt text to send as a single user message.
    - model: Optional model identifier. Falls back to provider's default model
      when available.
    - max_tokens: Optional maximum tokens for the completion.
    - temperature: Optional temperature value.
    - response_format: Optional response format hint (e.g., 'text', 'json_object').
    - json_schema: Optional JSON schema for structured output requests.
    - tools: Optional provider-agnostic tool specs.
    - extra: Optional free-form extras passed into the request.

    Returns
    - ChatResponse: Normalized provider response.

    Raises
    - ValueError: If no ``model`` is provided and the provider has no default model.
    """
    # Resolve model preference: explicit arg, else provider default if available.
    chosen_model = (model or "").strip() or (
        provider.default_model() if isinstance(provider, HasDefaultModel) else None  # type: ignore[attr-defined]
    )
    if not chosen_model:
        raise ValueError("Model is required: provide 'model' or use a provider with default_model().")

    req = ChatRequest(
        model=chosen_model,
        messages=[Message(role="user", content=text)],
        max_tokens=max_tokens,
        temperature=temperature,
        response_format=response_format,
        json_schema=json_schema,
        tools=tools,
        extra=extra or {},
    )
    return provider.chat(req)


__all__ = ["simple"]
