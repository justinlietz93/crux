"""SQLite backing store helpers for model registry snapshots.

These functions act as a thin boundary to the provider service's SQLite
layer, providing best-effort load/save of model registry snapshots. All
exceptions are suppressed to keep model listing non-fatal when the DB is
unavailable (e.g., first-run or read-only environments).
"""

from __future__ import annotations

import contextlib
from typing import Any, Dict, List, Optional

try:
    from crux_providers.service import db as svcdb  # type: ignore
except Exception:  # pragma: no cover
    svcdb = None  # type: ignore


def load_snapshot_from_db(provider: str) -> Optional[Dict[str, Any]]:
    """Load a snapshot from SQLite if available.

    Args:
        provider: Provider name.

    Returns:
        Snapshot mapping with at least a "models" list, or None on failure.
    """
    if svcdb is None:
        return None
    with contextlib.suppress(Exception):
        svcdb.ensure_initialized()
        snap = svcdb.load_models_snapshot(provider)
        if snap and isinstance(snap.get("models"), list):
            return snap
    return None


def save_snapshot_to_db(
    provider: str,
    models: List[Dict[str, Any]],
    fetched_at: str,
    fetched_via: str,
    metadata: Dict[str, Any],
) -> None:
    """Persist a snapshot into SQLite, ignoring failures.

    Args:
        provider: Provider name.
        models: List of model dicts (as serialized from ModelInfo).
        fetched_at: ISO 8601 timestamp for when the snapshot was fetched.
        fetched_via: Descriptor for the mechanism used (e.g., "api", "local").
        metadata: Additional metadata to store alongside the snapshot.
    """
    if svcdb is None:
        return
    with contextlib.suppress(Exception):
        svcdb.ensure_initialized()
        svcdb.save_models_snapshot(
            provider,
            models,
            fetched_at=fetched_at,
            fetched_via=fetched_via,
            metadata=metadata,
        )


__all__ = ["load_snapshot_from_db", "save_snapshot_to_db"]
