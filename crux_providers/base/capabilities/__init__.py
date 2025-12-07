"""Capabilities package.

Exports capability detection/merge helpers and observed capability persistence.
"""

from .core import (
    CAP_STREAMING,
    CAP_JSON,
    CAP_RESPONSES_API,
    CAP_MODEL_LISTING,
    CAP_DEFAULT_MODEL,
    CAP_TOOL_USE,
    CAP_CONTEXT_MANAGEMENT,
    CAP_AGENT_RUNTIME,
    detect_capabilities,
    normalize_modalities,
    merge_capabilities,
    should_attempt,
)
from .observed import load_observed, record_observation
from .void_profile import apply_void_enrichment

__all__ = [
    # constants
    "CAP_STREAMING",
    "CAP_JSON",
    "CAP_RESPONSES_API",
    "CAP_MODEL_LISTING",
    "CAP_DEFAULT_MODEL",
    "CAP_TOOL_USE",
    "CAP_CONTEXT_MANAGEMENT",
    "CAP_AGENT_RUNTIME",
    # helpers
    "detect_capabilities",
    "normalize_modalities",
    "merge_capabilities",
    "should_attempt",
    # observed persistence
    "load_observed",
    "record_observation",
    # Void-oriented enrichment
    "apply_void_enrichment",
]
