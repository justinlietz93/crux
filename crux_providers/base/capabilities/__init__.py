"""Capabilities package.

Exports capability detection/merge helpers and observed capability persistence.
"""

from .core import (
    CAP_STREAMING,
    CAP_JSON,
    CAP_RESPONSES_API,
    CAP_MODEL_LISTING,
    CAP_DEFAULT_MODEL,
    detect_capabilities,
    normalize_modalities,
    merge_capabilities,
    should_attempt,
)
from .observed import load_observed, record_observation

__all__ = [
    # constants
    "CAP_STREAMING",
    "CAP_JSON",
    "CAP_RESPONSES_API",
    "CAP_MODEL_LISTING",
    "CAP_DEFAULT_MODEL",
    # helpers
    "detect_capabilities",
    "normalize_modalities",
    "merge_capabilities",
    "should_attempt",
    # observed persistence
    "load_observed",
    "record_observation",
]
