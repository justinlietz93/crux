"""
ChatResponse DTO representing normalized provider responses.

At least one of ``text`` or ``parts`` should be present. The ``raw`` field can
be used for debugging but is intentionally excluded from default serialization
to prevent large object graphs from being logged or persisted unintentionally.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from .content_part import ContentPart
from .provider_metadata import ProviderMetadata


@dataclass
class ChatResponse:
    """Provider-agnostic response from an LLM chat invocation.

    Attributes:
        text: Optional plain text completion.
        parts: Optional structured content parts when available.
        raw: Optional provider SDK/native object for diagnostics only.
        meta: Execution `ProviderMetadata` for observability.

    Methods:
        to_dict: Return a sanitized JSON-serializable dictionary representation
            that excludes heavy ``raw`` payloads by default.
    """

    text: Optional[str]
    parts: Optional[List[ContentPart]]
    raw: Optional[Any]
    meta: ProviderMetadata

    def to_dict(self) -> Dict[str, Any]:
        """Return a JSON-serializable dictionary excluding raw provider objects."""
        return {
            "text": self.text,
            "parts": [p.to_dict() for p in self.parts] if self.parts else None,
            "raw": None,
            "meta": self.meta.to_dict(),
        }


__all__ = [
    "ChatResponse",
]
