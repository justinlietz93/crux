"""
Observed capabilities persistence (SQLite-backed).

Purpose
- Provide a single, DB-backed store for recording observed provider
    capabilities per model (e.g., whether a feature is supported or explicitly
    unsupported). This enables a data-first approach without guessing and
    removes file-based duplication.

Storage
- SQLite table ``observed_capabilities(provider, model_id, feature, value, updated_at)``.

Functions
- ``load_observed(provider, providers_root=None)`` → mapping by model id
- ``record_observation(provider, model_id, feature, value, providers_root=None)``

Notes
- The ``providers_root`` parameter is accepted for signature compatibility but
    is ignored in the SQLite implementation.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from ...service import db as _db


def _now_iso() -> str:
    """Return the current UTC time as an ISO 8601 formatted string.

    This helper is used for timestamping observed capability updates.
    """
    return datetime.now(timezone.utc).isoformat()

# TODO: This is unused, do something about it
def _atomic_write(_: object, __: Dict[str, Any]) -> None:
    """Legacy no-op to preserve import compatibility with older modules."""
    return




def load_observed(provider: str, providers_root: Optional[object] = None) -> Dict[str, Dict[str, Any]]:
    """Load observed capability mapping for a provider.

    Returns a mapping: {model_id: {feature: bool, ...}, ...}. On any error, an
    empty mapping is returned.

    Parameters:
        provider: Provider name (e.g., "openai").
        providers_root: Ignored; present for backward compatibility.
    """
    try:
        _db.ensure_initialized()
        return _db.load_observed_capabilities(provider)
    except Exception:
        return {}


def record_observation(
    provider: str,
    model_id: str,
    feature: str,
    value: bool,
    providers_root: Optional[object] = None,
) -> None:
    """Record an observed capability for a model.

    This function is idempotent and merges with existing observations.

    Parameters:
        provider: Provider name.
        model_id: Model identifier.
        feature: Capability name (e.g., "vision").
        value: True if supported (observed success), False if explicitly unsupported.
        providers_root: Ignored; present for backward compatibility.
    """
    try:
        _db.ensure_initialized()
        _db.record_observed_capability(
            provider, model_id, feature, value, updated_at=_now_iso()
        )
    except Exception:
        # Best-effort persistence; do not raise
        return


__all__ = ["load_observed", "record_observation"]
