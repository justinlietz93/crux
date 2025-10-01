"""
ModelRegistrySnapshot DTO representing a provider's model listing snapshot.

Captures the set of models fetched for a provider along with provenance and
timestamp metadata. Useful for caching and offline fallback behaviors.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .model_info import ModelInfo


@dataclass
class ModelRegistrySnapshot:
    """Snapshot of available models for a specific provider.

    Attributes:
        provider: Provider key for which the snapshot was taken.
        models: List of `ModelInfo` entries.
        fetched_via: Optional retrieval mechanism identifier (e.g., ``"api"``).
        fetched_at: Optional ISO-8601 timestamp of when the snapshot was fetched.
        metadata: Opaque, JSON-serializable map for additional retrieval details.

    Methods:
        to_dict: Return a JSON-serializable dictionary of the snapshot.
    """

    provider: str
    models: List[ModelInfo]
    fetched_via: Optional[str] = None
    fetched_at: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Return a JSON-serializable dictionary representation of the snapshot."""
        return {
            "provider": self.provider,
            "models": [m.to_dict() for m in self.models],
            "fetched_via": self.fetched_via,
            "fetched_at": self.fetched_at,
            "metadata": self.metadata,
        }


__all__ = [
    "ModelRegistrySnapshot",
]
