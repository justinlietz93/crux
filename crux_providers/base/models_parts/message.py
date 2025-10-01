"""
Message DTO used across providers.

Defines the `Message` dataclass and the `Role` literal representing the sender
role. Content may be either plain text or a list of `ContentPart` objects for
providers that support structured messages. Helpers are provided for common
inspection and text-flattening needs.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Literal, Union

from .content_part import ContentPart


# Message roles used across providers.
Role = Literal["system", "user", "assistant", "tool"]


@dataclass
class Message:
    """A chat message used by provider-agnostic DTOs.

    Summary:
        Represents a normalized chat message where ``content`` can be a raw
        string or a list of structured content parts. Provider adapters should
        map SDK-specific message shapes into this DTO.

    Attributes:
        role: The role of the message author (``"system"``, ``"user"``,
            ``"assistant"``, or ``"tool"``).
        content: Either a plain text string or a list of `ContentPart` items
            when structured content is available.

    Methods:
        is_structured: Returns True when content is a list of parts.
        text_or_joined: Produces a best-effort plain text view for logging or
            providers that require flattened content.
    """

    role: Role
    content: Union[str, List[ContentPart]]

    def is_structured(self) -> bool:
        """Return True if the message content is a structured list of parts."""
        return isinstance(self.content, list)

    def text_or_joined(self) -> str:
        """Return a flattened string representation of the message content.

        If the content is already a string, it is returned as-is. For
        structured content, text values are concatenated with newlines and
        non-text parts are represented by bracketed type tokens for compact
        logging.
        """
        if isinstance(self.content, str):
            return self.content
        parts: List[str] = []
        for p in self.content:
            if p.text:
                parts.append(p.text)
            else:
                parts.append(f"[{p.type}]")
        return "\n".join(parts)


__all__ = [
    "Message",
    "Role",
]
