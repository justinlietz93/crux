"""SQLite store for observed provider capabilities.

This module centralizes persistence of runtime-observed capability flags
per provider/model. It replaces the prior file-based persistence and ensures
observations are durable and queryable via the existing providers DB.

Schema
------
Table: observed_capabilities
    provider TEXT NOT NULL
    model_id TEXT NOT NULL
    feature  TEXT NOT NULL
    value    INTEGER NOT NULL  -- 0/1 bool
    updated_at TEXT NOT NULL   -- ISO 8601 UTC

Primary Key: (provider, model_id, feature)

Public API
---------
- upsert_observation(provider, model_id, feature, value, updated_at)
- load_observed_mapping(provider) -> { model_id: { feature: bool, ... }, ... }

Notes
-----
- Callers are expected to pass ISO 8601 UTC timestamps for updated_at.
- This module depends on the providers service DB connection accessor to
  reuse connection lifecycle and configuration (WAL, busy_timeout).
"""

from __future__ import annotations

from typing import Dict

from ...service.db import _get_conn  # type: ignore  # internal, scoped usage

__all__ = ["upsert_observation", "load_observed_mapping"]


def upsert_observation(
    provider: str,
    model_id: str,
    feature: str,
    value: bool,
    updated_at: str,
) -> None:
    """Insert or update a single observed capability flag.

    Parameters
    ----------
    provider : str
        Provider identifier (e.g., "openai").
    model_id : str
        Model identifier for the observation.
    feature : str
        Capability name (e.g., "vision", "streaming").
    value : bool
        True if supported (observed success), False if explicitly unsupported.
    updated_at : str
        ISO 8601 UTC timestamp string for when the observation was recorded.

    Side Effects
    ------------
    Performs an UPSERT into the observed_capabilities table and commits.
    """
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO observed_capabilities(provider, model_id, feature, value, updated_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(provider, model_id, feature)
        DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at
        """,
        (provider, model_id, feature, 1 if value else 0, updated_at),
    )
    conn.commit()


def load_observed_mapping(provider: str) -> Dict[str, Dict[str, bool]]:
    """Load observed capability flags for a provider.

    Returns a nested mapping of model_id -> { feature: bool }.

    Parameters
    ----------
    provider : str
        Provider identifier to query.

    Returns
    -------
    Dict[str, Dict[str, bool]]
        Mapping suitable for merging into model capability dicts.
    """
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT model_id, feature, value FROM observed_capabilities WHERE provider = ?",
        (provider,),
    )
    out: Dict[str, Dict[str, bool]] = {}
    for model_id, feature, value in cur.fetchall():
        d = out.get(model_id)
        if d is None:
            d = {}
            out[model_id] = d
        d[str(feature)] = bool(int(value))
    return out
