"""
Provider call metadata model.

Encapsulates diagnostic metadata for provider operations (HTTP codes, request
identifiers, latency, configuration notes). This object is attached to
responses to support observability, audits, and analytics.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, Optional


@dataclass
class ProviderMetadata:
    """Execution metadata for a provider call.

    Attributes:
        provider_name: Canonical provider key (e.g., ``"openai"``).
        model_name: Resolved model name used for the call.
        token_param_used: Which token parameter key was applied by the adapter
            (e.g., ``"max_tokens"``, ``"max_completion_tokens"``).
        temperature_included: Whether a temperature parameter was sent.
        http_status: HTTP status code if available from the SDK or client.
        request_id: Provider-specific request identifier when available.
        response_id: Provider-specific response identifier when available.
        latency_ms: End-to-end latency for the operation, in milliseconds.
        extra: Opaque, JSON-serializable map for adapter-specific diagnostics.

    Methods:
        to_dict: Return a JSON-serializable dictionary representation suitable
            for logging and storage.
    """

    provider_name: str
    model_name: str
    token_param_used: Optional[str] = None
    temperature_included: Optional[bool] = None
    http_status: Optional[int] = None
    request_id: Optional[str] = None
    response_id: Optional[str] = None
    latency_ms: Optional[float] = None
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Return a JSON-serializable dictionary of the metadata fields."""
        return asdict(self)


__all__ = [
    "ProviderMetadata",
]
