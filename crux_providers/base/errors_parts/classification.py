"""
Error classification helpers mapping exceptions to normalized ErrorCode values.

Implements HTTP status extraction, status-to-code mapping, and legacy
message-based heuristics as a fallback to maintain compatibility with various
provider SDKs.
"""
from __future__ import annotations

import asyncio
from typing import Optional, Dict

from .error_code import ErrorCode
from .provider_error import ProviderError


def _extract_status(exc: Exception) -> Optional[int]:
    """Attempt to extract an HTTP status code from a provider exception.

    Supported attribute shapes (checked in order):
    - ``exc.status_code``
    - ``exc.status``
    - ``exc.response.status_code``
    Returns ``None`` if no valid status can be found.
    """
    for attr in ("status_code", "status"):
        val = getattr(exc, attr, None)
        if isinstance(val, int) and 100 <= val < 600:
            return val
    resp = getattr(exc, "response", None)
    if resp is not None:
        sc = getattr(resp, "status_code", None)
        if isinstance(sc, int) and 100 <= sc < 600:
            return sc
    return None


_HTTP_STATUS_MAP: Dict[int, ErrorCode] = {
    400: ErrorCode.VALIDATION,
    401: ErrorCode.AUTH,
    403: ErrorCode.AUTH,
    404: ErrorCode.NOT_FOUND,
    408: ErrorCode.TIMEOUT,
    409: ErrorCode.CONFLICT,
    422: ErrorCode.VALIDATION,
    429: ErrorCode.RATE_LIMIT,
    500: ErrorCode.SERVER_ERROR,
    502: ErrorCode.TRANSIENT,
    503: ErrorCode.UNAVAILABLE,
    504: ErrorCode.TIMEOUT,
}


def _heuristic_from_message(msg: str) -> Optional[ErrorCode]:  # pragma: no cover - simple mapping
    """Legacy substring heuristic mapping for non-HTTP exceptions."""
    PATTERN_GROUPS = (
        (ErrorCode.RATE_LIMIT, ("rate", "limit")),
        (ErrorCode.TIMEOUT, ("timeout",)),
        (ErrorCode.TIMEOUT, ("timed out",)),
        (ErrorCode.AUTH, ("auth",)),
        (ErrorCode.AUTH, ("api key",)),
        (ErrorCode.AUTH, ("unauthorized",)),
        (ErrorCode.AUTH, ("forbidden",)),
        (ErrorCode.UNSUPPORTED, ("unsupported",)),
        (ErrorCode.UNSUPPORTED, ("not supported",)),
        (ErrorCode.NOT_FOUND, ("not found",)),
        (ErrorCode.NOT_FOUND, ("does not exist",)),
        (ErrorCode.CONFLICT, ("conflict",)),
        (ErrorCode.CONFLICT, ("already exists",)),
        (ErrorCode.UNAVAILABLE, ("unavailable",)),
        (ErrorCode.UNAVAILABLE, ("temporarily down",)),
        (ErrorCode.VALIDATION, ("validation",)),
        (ErrorCode.VALIDATION, ("invalid",)),
        (ErrorCode.VALIDATION, ("malformed",)),
        (ErrorCode.SERVER_ERROR, ("server error",)),
        (ErrorCode.SERVER_ERROR, ("internal error",)),
    )
    for code, patterns in PATTERN_GROUPS:
        if code is ErrorCode.RATE_LIMIT and patterns == ("rate", "limit"):
            if all(p in msg for p in patterns):
                return code
            continue
        if any(p in msg for p in patterns):
            return code
    return None


def classify_exception(exc: Exception) -> ErrorCode:
    """Classify an exception into a normalized :class:`ErrorCode`.

    Precedence:
        1. ProviderError passthrough.
        2. Timeout exceptions (sync/async).
        3. HTTP status mapping.
        4. Legacy substring heuristics.
        5. ``UNKNOWN`` fallback.
    """
    if isinstance(exc, ProviderError):
        return exc.code
    if isinstance(exc, (TimeoutError, asyncio.TimeoutError)):
        return ErrorCode.TIMEOUT
    status = _extract_status(exc)
    if status is not None and status in _HTTP_STATUS_MAP:
        return _HTTP_STATUS_MAP[status]
    code = _heuristic_from_message(str(exc).lower())
    return code if code is not None else ErrorCode.UNKNOWN


__all__ = [
    "classify_exception",
    "_extract_status",
    "_HTTP_STATUS_MAP",
]
