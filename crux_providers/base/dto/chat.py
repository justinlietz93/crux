"""
Pydantic DTOs and validators for inbound chat requests in the providers layer.

Purpose
-------
This module defines strict, provider-agnostic request DTOs using Pydantic to
validate inbound chat payloads before they enter provider adapters. It enforces
roles, content constraints, and numeric parameter bounds to catch issues early.

External dependencies: Pydantic only (no network/CLI calls). No timeouts.

Fallback semantics: Not applicable. Validation either succeeds or raises a
`pydantic.ValidationError`. Callers should handle this at the controller edge
and return an appropriate 4xx response when used in an HTTP server context.

Design
------
- Keep DTOs minimal and framework-agnostic.
- Align with existing dataclasses in `crux_providers.base.models` but add validation.
- Avoid provider SDK imports or behavior here; adapters map from these DTOs to
  provider-specific parameters.

"""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field, model_validator


Role = Literal["system", "user", "assistant", "tool"]


class ContentPartDTO(BaseModel):
    """A structured content part within a message.

    Attributes:
        type: The content type identifier (e.g., "text", "json", "image").
        text: Optional human-readable text segment.
        data: Optional structured payload for non-text parts.

    Notes:
    This mirrors `ContentPart` in `crux_providers.base.models` but with validation.
    """

    type: Literal["text", "json", "tool_call", "image", "refusal", "other"]
    text: Optional[str] = None
    data: Optional[Dict[str, Any]] = None


class MessageDTO(BaseModel):
    """Represents a chat message with either a text string or structured parts.

    Rules:
        - `role` must be one of Role.
        - `content` must be either a non-empty string OR a non-empty list of ContentPartDTO.
        - For `user` role, enforce at least some visible content (non-empty text
          or at least one part with text or data).

    Failure Modes:
        Raises `ValidationError` when constraints are not met.
    """

    role: Role
    content: Union[str, List[ContentPartDTO]]

    @model_validator(mode="after")
    def _validate_content(self) -> "MessageDTO":
        """Validate the content of a chat message.

        Ensures that content is non-empty and, for user messages, contains at least one part with text or data.

        Returns:
            MessageDTO: The validated message DTO.

        Raises:
            ValueError: If content is empty or does not meet requirements.
        """
        content = self.content
        if isinstance(content, str):
            if content.strip() == "":
                raise ValueError("content string must be non-empty")
            return self
        # content is a list
        if not content:
            raise ValueError("content parts must be a non-empty list")
        # for user role, at least one part should have text or data
        if self.role == "user" and not any((p.text and p.text.strip()) or (p.data is not None) for p in content):
            raise ValueError("user message must include text or data in at least one part")
        return self


class ToolSpecDTO(BaseModel):
    """Provider-agnostic tool specification placeholder.

    This intentionally stays loose; adapters can validate deeper per provider.
    """

    name: str = Field(..., min_length=1)
    description: Optional[str] = None
    parameters: Optional[Dict[str, Any]] = None


class ChatRequestDTO(BaseModel):
    """Normalized request DTO with validation for provider adapters.

    Parameters:
        model: Target model identifier (non-empty).
        messages: Ordered list of MessageDTO (non-empty; first message usually system/user).
        max_tokens: If provided, must be positive.
        temperature: If provided, must be within [0.0, 2.0].
        response_format: Optional hint (e.g., "text" or "json_object").
        json_schema: Optional JSON schema for structured output modes.
        tools: Optional tool specifications (loose validation).
        extra: Free-form escape hatch for rare needs (must be a dict).

    Raises:
        ValidationError: On invalid roles, empty content, or out-of-range params.
    """

    model: str = Field(..., min_length=1)
    messages: List[MessageDTO] = Field(..., min_length=1)
    max_tokens: Optional[int] = Field(default=None, gt=0)
    temperature: Optional[float] = Field(default=None, ge=0.0, le=2.0)
    response_format: Optional[str] = None
    json_schema: Optional[Dict[str, Any]] = None
    tools: Optional[List[ToolSpecDTO]] = None
    extra: Dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_sequence(self) -> "ChatRequestDTO":
        """Validate the message sequence for a chat request.

        Ensures the first message is from 'system' or 'user', raising a ValueError otherwise.

        Returns:
            ChatRequestDTO: The validated chat request DTO.

        Raises:
            ValueError: If the first message is not from 'system' or 'user'.
        """
        # Basic sanity: first message cannot be from assistant/tool.
        if self.messages and self.messages[0].role not in ("system", "user"):
            raise ValueError("first message must be from 'system' or 'user'")
        return self


__all__ = [
    "Role",
    "ContentPartDTO",
    "MessageDTO",
    "ToolSpecDTO",
    "ChatRequestDTO",
]
