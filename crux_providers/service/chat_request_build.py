"""Chat request construction and input-size guard helpers.

This module contains utilities for building ``ChatRequest`` objects from
incoming DTO-like bodies, converting message formats, and applying a
deterministic input-size guard when enabled. Kept separate to enforce the
500-LOC/file limit and improve cohesion in ``service.helpers``.
"""

from __future__ import annotations

from typing import Any, List, Optional

from crux_providers.base.models import ChatRequest, ContentPart, Message
from crux_providers.utils.input_size_guard import (
    is_guard_enabled,
    get_max_input_chars,
    condense_text_to_limit,
)


def to_messages(dtos: List[Any]) -> List[Message]:
    """Convert a list of DTOs to a list of ``Message`` objects.

    Each DTO is transformed into a ``Message``, handling both single and
    multipart content. Multipart content items may include optional ``data``.

    Parameters
    ----------
    dtos: List[Any]
        Items with ``role`` and ``content`` attributes (e.g., pydantic models).

    Returns
    -------
    List[Message]
        Messages suitable for provider adapters.
    """
    msgs: List[Message] = []
    for m in dtos:
        content = m.content
        if isinstance(content, list):
            parts: List[ContentPart] = []
            for p in content:
                ptype = p.get("type", "text") if isinstance(p, dict) else "text"
                ptext = p.get("text") if isinstance(p, dict) else str(p)
                pdata = p.get("data") if isinstance(p, dict) else None
                parts.append(ContentPart(type=ptype, text=ptext, data=pdata))
            msgs.append(Message(role=m.role, content=parts))
        else:
            msgs.append(Message(role=m.role, content=str(content)))
    return msgs


def build_chat_request(body) -> ChatRequest:  # body is pydantic ChatBody
    """Construct a ``ChatRequest`` from a request body.

    Converts the provided body into a ``ChatRequest``, transforming messages
    and copying relevant fields. Applies an input-size guard when enabled via
    configuration to keep UX friendly for oversized inputs.

    Parameters
    ----------
    body: Any
        Pydantic-like object with fields: model, messages, max_tokens,
        temperature, response_format, json_schema, tools, extra.

    Returns
    -------
    ChatRequest
        A request populated from the body with optional input guard applied.
    """
    req = ChatRequest(
        model=body.model,
        messages=to_messages(body.messages),
        max_tokens=body.max_tokens,
        temperature=body.temperature,
        response_format=body.response_format,
        json_schema=body.json_schema,
        tools=body.tools,
        extra=body.extra or {},
    )
    eff_max = _compute_effective_input_limit()
    if eff_max > 0:
        req = _apply_input_size_guard(req, eff_max)
    return req


def _compute_effective_input_limit() -> int:
    """Compute the active input-size character limit for guard logic.

    The limit is sourced from the input size guard configuration. If the guard
    is disabled, the function returns 0 to indicate no bound enforcement.

    Returns
    -------
    int
        A positive integer limit when enabled, otherwise 0.
    """
    return get_max_input_chars() if is_guard_enabled() else 0


def _apply_input_size_guard(req: ChatRequest, eff_max: int) -> ChatRequest:
    """Condense a request's messages to fit within the configured limit.

    Keeps the first system message (if present), condenses all user segments
    into one user message via ``condense_text_to_limit``, then appends any
    remaining non-user roles afterwards.

    Parameters
    ----------
    req: ChatRequest
        The original request.
    eff_max: int
        The effective input-size limit in characters. Must be > 0.

    Returns
    -------
    ChatRequest
        Possibly transformed request with messages condensed to respect the
        input-size bound. Returns the original when already within bounds.
    """
    if eff_max <= 0:
        return req

    total_len = len("".join(m.text_or_joined() for m in req.messages))
    if total_len <= eff_max:
        return req

    system_text: Optional[str] = None
    user_texts: list[str] = []
    others: list[Message] = []

    for m in req.messages:
        txt = m.text_or_joined()
        if m.role == "system" and system_text is None:
            system_text = txt
        elif m.role == "user":
            user_texts.append(txt)
        else:
            others.append(Message(role=m.role, content=txt))

    combined_user = "\n".join(seg for seg in user_texts if seg)
    condensed_user = condense_text_to_limit(combined_user, eff_max)

    new_messages: list[Message] = []
    if system_text:
        new_messages.append(Message(role="system", content=system_text))
    new_messages.append(Message(role="user", content=condensed_user))
    new_messages.extend(others)

    return ChatRequest(
        model=req.model,
        messages=new_messages,
        max_tokens=req.max_tokens,
        temperature=req.temperature,
        response_format=req.response_format,
        json_schema=req.json_schema,
        tools=req.tools,
        extra=req.extra,
    )


__all__ = ["to_messages", "build_chat_request"]
