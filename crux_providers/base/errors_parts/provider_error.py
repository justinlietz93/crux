"""
Structured provider error exception type.

Wraps provider-specific exceptions with a normalized `ErrorCode` for consistent
handling, retry logic, and structured logging.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .error_code import ErrorCode


@dataclass
class ProviderError(Exception):
    """Represents a structured provider error with a normalized error code.

    Attributes:
        code: Normalized :class:`ErrorCode` classification for the failure.
        message: Human-readable error message suitable for logging.
        provider: Provider key where the error originated (e.g., ``"openai"``).
        model: Optional model name associated with the failure.
        retryable: Hint for upstream retry logic (not authoritative).
        raw: Optional original exception for diagnostics.
    """

    code: ErrorCode
    message: str
    provider: str
    model: Optional[str] = None
    retryable: bool = False
    raw: Optional[Exception] = None

    def __str__(self) -> str:  # pragma: no cover - trivial
        """Return a compact string combining provider, model, code, and message."""
        return f"{self.provider}:{self.model or '-'} {self.code.value}: {self.message}"


__all__ = ["ProviderError"]
