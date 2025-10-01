"""Cancellation error type.

Defines the public ``CancelledError`` used to signal cooperative cancellation
in provider operations. Kept isolated to satisfy one-class-per-file policy.
"""

from __future__ import annotations


class CancelledError(RuntimeError):
    """Raised when an operation is cancelled cooperatively.

    This specialized error distinguishes cooperative cancellation from other
    runtime failures, enabling targeted handling (e.g., suppress log noise,
    map to a structured status, or avoid retry logic).
    """

__all__ = ["CancelledError"]
