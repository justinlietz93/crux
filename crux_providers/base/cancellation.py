"""Cooperative cancellation primitives (public API facade).

Purpose
-------
Expose stable, provider-agnostic cancellation constructs via the canonical
``crux_providers.base.cancellation`` import path while the concrete
implementations live under ``cancellation_parts`` for organization.

Notes
-----
- This module is the public surface; implementations are factored for clarity,
	not as temporary shims.
- ``CancellationToken`` enables cooperative cancellation signalling across
	streaming and long-running operations.
- ``CancelledError`` is raised by operations that observe a cancellation request.
"""

from .cancellation_parts.cancelled_error import CancelledError
from .cancellation_parts.cancellation_token import CancellationToken

__all__ = ["CancellationToken", "CancelledError"]
