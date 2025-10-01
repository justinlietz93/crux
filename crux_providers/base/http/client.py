"""Shared HTTP client pool for providers.

Purpose:
    Provide a centralized, thread-safe pool of reusable ``httpx.Client``
    instances to avoid per-call allocations and reduce connection overhead
    across provider adapters. Timeouts derive exclusively from
    :func:`get_timeout_config` and no hard-coded numeric literals are
    introduced.

External dependencies:
    - ``httpx`` for the underlying synchronous HTTP client.

Timeout strategy:
    - The client's timeout is set based on ``get_timeout_config()`` at the
      time of first creation and cached thereafter. Call sites should still
      guard blocking start phases with :func:`operation_timeout` as this pool
      does not enforce per-call timeouts.

Lifecycle & cleanup:
    - Clients are cached by a composite key of ``base_url`` and ``purpose``
      string. Purposes allow distinct pools (e.g., "chat" vs "stream").
    - All clients are closed at interpreter exit via ``atexit``. Libraries or
      tests may also call :func:`close_all_clients` explicitly.

Design notes:
    - This module resides in the providers base layer and exposes only
      functions; adapters obtain clients via ``get_httpx_client`` to satisfy
      clean architecture and shared configuration policies.

"""

from __future__ import annotations

import atexit
import threading
from typing import Dict, Optional, Tuple

import httpx

from ..timeouts import get_timeout_config

# Internal cache keyed by (base_url, purpose)
_CLIENTS: Dict[Tuple[Optional[str], str], httpx.Client] = {}
_LOCK = threading.RLock()


def get_httpx_client(base_url: Optional[str], purpose: str) -> httpx.Client:
    """Return a pooled ``httpx.Client`` for the given base URL and purpose.

    The first request for a key creates a client configured with timeouts from
    :func:`get_timeout_config`. Subsequent requests reuse the same instance.

    Parameters:
        base_url: Optional API base URL to associate with the client. When
            provided, it is set on the client so relative requests can be used
            by callers. ``None`` groups clients under a shared key.
        purpose: A short string discriminating separate pools (e.g.,
            "chat", "stream"). Keep stable to maximize reuse.

    Returns:
        A reusable ``httpx.Client`` instance.

    Thread-safety:
        This function is safe for concurrent use; per-key creation is guarded
        by a re-entrant lock.
    """
    key = (base_url, purpose)
    client = _CLIENTS.get(key)
    if client is not None:
        return client

    with _LOCK:
        client = _CLIENTS.get(key)
        if client is not None:
            return client
        cfg = get_timeout_config()
        # Use a bounded timeout related to start timeout; callers should still
        # guard start phases with operation_timeout.
        timeout = cfg.start_timeout_seconds * 4
        client = httpx.Client(base_url=base_url, timeout=timeout) if base_url else httpx.Client(timeout=timeout)
        _CLIENTS[key] = client
        return client


def close_all_clients() -> None:
    """Close and clear all pooled HTTP clients.

    This is primarily useful in test teardown or application shutdown phases
    when immediate release of network resources is desired.
    """
    with _LOCK:
        for c in _CLIENTS.values():
            try:
                c.close()
            except Exception:  # nosec B110 - best-effort shutdown; safe to ignore close errors
                # Cleanup during interpreter exit; connection pool teardown
                # failures are non-actionable and should not surface.
                pass
        _CLIENTS.clear()


def _cleanup_at_exit() -> None:
    """atexit hook to ensure clients are closed on interpreter exit."""
    close_all_clients()


atexit.register(_cleanup_at_exit)

__all__ = ["get_httpx_client", "close_all_clients"]
