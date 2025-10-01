"""
ModelInfo DTO for provider model listings.

Represents a single model entry as returned by provider model listing APIs or
local caches. Capabilities and metadata are preserved in generic fields to keep
adapters decoupled from provider specifics.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict, field
from typing import Any, Dict, Optional


@dataclass
class ModelInfo:
    """A single model listing entry.

    Attributes:
        id: Stable model identifier.
        name: Human-friendly display name.
        provider: Provider key owning this model.
        family: Optional family/category (e.g., ``"gpt-4o"``).
        context_length: Optional maximum context window size.
        capabilities: Opaque map of provider-specific capability flags/details.
        updated_at: Optional ISO-8601 timestamp when fetched from remote.

    Methods:
        to_dict: Return a JSON-serializable dictionary of the entry.
    """

    id: str
    name: str
    provider: str
    family: Optional[str] = None
    context_length: Optional[int] = None
    capabilities: Dict[str, Any] = field(default_factory=dict)
    updated_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Return a JSON-serializable dictionary representation of the entry."""
        return asdict(self)


__all__ = [
    "ModelInfo",
]
