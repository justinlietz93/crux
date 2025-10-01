"""
Normalized provider error codes (taxonomy).

Defines the `ErrorCode` enumeration used across provider adapters and error
handling utilities. Values are lowercase snake_case and are considered a stable
public contract for logging and analytics.
"""
from __future__ import annotations

from enum import Enum


class ErrorCode(str, Enum):
    """Enumerated normalized error codes representing failure categories."""

    AUTH = "auth"
    RATE_LIMIT = "rate_limit"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"
    TRANSIENT = "transient"
    UNSUPPORTED = "unsupported"
    VALIDATION = "validation"
    NOT_FOUND = "not_found"
    CONFLICT = "conflict"
    SERVER_ERROR = "server_error"
    INTERNAL = "internal"
    UNAVAILABLE = "unavailable"
    UNKNOWN = "unknown"


__all__ = ["ErrorCode"]
