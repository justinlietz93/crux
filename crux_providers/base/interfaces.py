"""
Provider-agnostic interfaces (ABCs/Protocols) for the providers layer.

This module now re-exports Protocols split into single-class modules under
``crux_providers.base.interfaces_parts`` to satisfy one-class-per-file governance
while keeping imports stable for upstream code.
"""

from __future__ import annotations

from .interfaces_parts import (
    HasDefaultModel,
    LLMProvider,
    ModelListingProvider,
    SupportsJSONOutput,
    SupportsResponsesAPI,
    SupportsStreaming,
)

__all__ = [
    "LLMProvider",
    "SupportsStreaming",
    "SupportsJSONOutput",
    "SupportsResponsesAPI",
    "ModelListingProvider",
    "HasDefaultModel",
]
