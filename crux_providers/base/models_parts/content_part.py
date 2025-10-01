"""
Structured content part model for assistant messages.

This module defines the `ContentPart` dataclass and its associated
`ContentPartType` literal. Providers may emit structured assistant content as
multiple parts (text, JSON, images, tool-call metadata). This object captures a
normalized, provider-agnostic shape for downstream handling, logging, and
serialization.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, Literal, Optional


# Known content part types seen across providers' structured messages.
ContentPartType = Literal[
    "text",          # Plain text content
    "json",          # JSON content as string
    "tool_call",     # Tool call metadata
    "image",         # Image content (path/URL/base64) - adapter-defined semantics
    "refusal",       # Refusal reason text
    "other",         # Catch-all (adapter may attach provider-specific type info)
]


@dataclass
class ContentPart:
    """A single piece of structured assistant content.

    Summary:
        Encapsulates an assistant message "part" that may contain plain text or
        additional structured metadata. Providers that support multi-part
        content can be normalized into this DTO for portability.

    Attributes:
        type: The semantic kind of the content part, e.g., ``"text"`` or
            ``"tool_call"``.
        text: Optional textual content for human-readable parts.
        data: Optional provider- or adapter-specific payload for non-text parts
            (e.g., tool call arguments, image descriptors).

    Methods:
        to_dict: Return a JSON-serializable dictionary representation of the
            content part.
    """

    type: ContentPartType
    text: Optional[str] = None
    data: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Return a JSON-serializable dictionary representation of the object."""
        return asdict(self)


__all__ = [
    "ContentPart",
    "ContentPartType",
]
