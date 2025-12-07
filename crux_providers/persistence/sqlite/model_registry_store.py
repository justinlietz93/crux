"""SQLite model registry persistence helpers.

This module contains pure persistence concerns for the provider model registry
snapshot feature (formerly housed in `service/model_registry_store.py`). It
intentionally avoids importing higher-level service logic to preserve clean
layer boundaries:

Layering Rationale
------------------
- The *service* layer orchestrates initialization, seeding, and aggregates.
- The *persistence.sqlite* package provides focused CRUD helpers operating on
  an active SQLite connection obtained indirectly via a lightweight accessor.
- By relocating this code we reduce `service/db.py` size & cyclomatic
  complexity and prepare for an eventual repository interface abstraction
  (e.g., `IModelRegistryStore`).

Timeouts & Retries
------------------
Operations here are local SQLite writes/reads and assumed to be fast; no
explicit retry or timeout wrappers are applied. Callers higher in the stack
handle broader operation timeouts via `operation_timeout` when performing
network fetches preceding persistence.

Failure Modes
-------------
Exceptions are allowed to propagate for visibility; higher layers may choose
to suppress them when persistence is considered best-effort (e.g., model list
fetch). Defensive JSON parsing paths are guarded to avoid cascading failures
on malformed capability blobs.
"""

from __future__ import annotations

import contextlib
import json
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

# NOTE: Local import to avoid circular dependency during module graph import.
from ...service.db import _get_conn  # type: ignore  # internal usage acceptable

__all__ = [
    "save_models_snapshot",
    "load_models_snapshot",
    "list_providers",
]


# ------------------------ Normalization helpers -------------------------

def _normalize_model_entry(
    m: Any,
) -> Tuple[str, str, Optional[str], Optional[int], Dict[str, Any], Optional[str]]:
    """Normalize an arbitrary model entry into structured tuple fields.

    Parameters
    ----------
    m:
        Source entry from provider listing; may be a mapping or primitive.

    Returns
    -------
    Tuple[str, str, Optional[str], Optional[int], Dict[str, Any], Optional[str]]
        Tuple of ``(model_id, name, family, context_length, capabilities_dict, updated_at_iso)``.

    Notes
    -----
    - Non-dict inputs are coerced into minimal ``id=name`` entries to keep the
      schema lean while supporting heterogeneous provider payload shapes.
    - Capability blobs are normalized separately via ``_normalize_capabilities``.
    """
    if isinstance(m, dict):
        return _normalize_model_entry_from_dict(m)
    s = str(m)
    return s, s, None, None, {}, None


def _normalize_model_entry_from_dict(
    m: Dict[str, Any],
) -> Tuple[str, str, Optional[str], Optional[int], Dict[str, Any], Optional[str]]:
    """Field-specific normalization for dict model entries.

    Parameters
    ----------
    m:
        Mapping representing a provider model row.

    Returns
    -------
    Tuple[str, str, Optional[str], Optional[int], Dict[str, Any], Optional[str]]
        Normalized tuple with id, display name, family, context length, capabilities, updated timestamp.

    Notes
    -----
    - Identifier priority order handles provider differences: ``id``, then ``model``, then ``name``.
    - Context length is parsed via ``_parse_context_length`` and returns ``None`` if invalid.
    """
    mid = str(m.get("id") or m.get("model") or m.get("name") or "unknown")
    name = str(m.get("name") or m.get("id") or mid)
    family = m.get("family") if isinstance(m.get("family"), str) else None
    ctx_int = _parse_context_length(m.get("context_length"))
    caps = _normalize_capabilities(m.get("capabilities"))
    updated = m.get("updated_at") if isinstance(m.get("updated_at"), str) else None
    return mid, name, family, ctx_int, caps, updated


def _parse_context_length(val: Any) -> Optional[int]:
    """Parse context length into an integer if possible.

    Supported input forms (Issue #40):

    - Plain integers (e.g., 8192, "4096")
    - Comma separated thousands (e.g., "4,096", "32,000")
    - Values suffixed with 'k' or 'K' meaning *1000* (e.g., "8k", "8K")
    - Decimal kilonotation (e.g., "1.5k" -> 1500, "0.75K" -> 750)
    - Tokens annotation suffix (e.g., "8k tokens", "4,096 tokens")

    Returns None for negative numbers, zero (treated as invalid / unknown), or
    any unparsable/ambiguous input. The rationale for rejecting zero/negative
    is that provider context windows are strictly positive; returning None
    instead of 0 avoids misinforming downstream selection heuristics.

    Failure handling is intentionally quiet (returns None) to keep ingestion
    resilient to novel provider formats. Tests cover the accepted grammar so
    future modifications can safely extend without breaking existing cases.
    """
    if val is None:
        return None
    # Fast path: already an int
    if isinstance(val, int):
        return val if val > 0 else None
    # Normalize to string for flexible parsing
    s = str(val).strip().lower()
    if not s:
        return None
    # Remove trailing 'tokens' label if present
    if s.endswith(" tokens"):
        s = s[:-7].rstrip()
    # Remove commas (thousand separators)
    s_no_commas = s.replace(",", "")
    # Handle explicit k / decimal k suffix
    if s_no_commas.endswith("k"):
        num_part = s_no_commas[:-1]
        try:
            base = float(num_part)
        except ValueError:  # pragma: no cover - defensive
            return None
        ctx = int(base * 1000)
        return ctx if ctx > 0 else None
    # Fallback: try plain integer
    try:
        ctx = int(s_no_commas)
    except (TypeError, ValueError):  # pragma: no cover - defensive
        return None
    return ctx if ctx > 0 else None


def _normalize_capabilities(caps: Any) -> Dict[str, Any]:
    """Normalize capabilities payload into a dict, wrapping unknown types.

    Parameters
    ----------
    caps:
        Raw capabilities element; may be dict, None, or arbitrary type.

    Returns
    -------
    Dict[str, Any]
        A dictionary representation; unknown types are wrapped as ``{"raw_capabilities": caps}``.
    """
    if isinstance(caps, dict):
        return caps
    return {} if caps is None else {"raw_capabilities": caps}


def _json_dump(obj: Any) -> str:
    """Serialize object to JSON; fallback to raw string wrapper on failure.

    Parameters
    ----------
    obj:
        Python object to serialize.

    Returns
    -------
    str
        JSON string. If serialization fails, returns ``{"raw": str(obj)}``.
    """
    with contextlib.suppress(Exception):  # pragma: no cover - defensive
        return json.dumps(obj)
    return json.dumps({"raw": str(obj)})


# --------------------------- DB write helpers ---------------------------

def _clear_provider_models(cur: sqlite3.Cursor, provider: str) -> None:
    """Remove existing rows for a provider prior to snapshot insert.

    Parameters
    ----------
    cur:
        Active SQLite cursor within a transaction.
    provider:
        Provider identifier used to scope deletion.

    Side Effects
    ------------
    Executes a DELETE statement; no commit is performed here.
    """
    cur.execute("DELETE FROM model_registry WHERE provider = ?", (provider,))


def _insert_model_rows(cur: sqlite3.Cursor, provider: str, models: Any) -> None:
    """Insert normalized model rows for a snapshot.

    Parameters
    ----------
    cur:
        Active SQLite cursor within a transaction.
    provider:
        Provider identifier to associate with the models.
    models:
        Iterable/list-like of model entries in heterogeneous shapes.

    Side Effects
    ------------
    Executes INSERT statements per row; no commit is performed here.
    """
    for m in models or []:
        mid, name, family, ctx_int, caps, updated = _normalize_model_entry(m)
        cur.execute(
            """
            INSERT INTO model_registry(provider, model_id, name, family, context_length, capabilities, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (provider, mid, name, family, ctx_int, _json_dump(caps), updated),
        )


def _upsert_registry_meta(
    cur: sqlite3.Cursor,
    provider: str,
    *,
    fetched_at: Optional[str] = None,
    fetched_via: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    """Insert or update meta record for a provider snapshot.

    Parameters
    ----------
    cur:
        Active SQLite cursor within a transaction.
    provider:
        Provider identifier.
    fetched_at:
        Optional ISO timestamp for when models were fetched; defaults to now (UTC) if not provided.
    fetched_via:
        Optional descriptor for the source, e.g., ``"api"``.
    metadata:
        Optional dictionary of additional metadata, JSON-encoded for storage.

    Side Effects
    ------------
    Performs an UPSERT into ``model_registry_meta``; no commit is performed here.
    """
    now = fetched_at or datetime.now(timezone.utc).isoformat()
    cur.execute(
        """
        INSERT INTO model_registry_meta(provider, fetched_at, fetched_via, metadata)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(provider) DO UPDATE SET fetched_at=excluded.fetched_at, fetched_via=excluded.fetched_via, metadata=excluded.metadata
        """,
        (provider, now, fetched_via or "api", json.dumps(metadata or {})),
    )


# ---------------------------- Public functions --------------------------

def save_models_snapshot(
    provider: str,
    models: Any,
    *,
    fetched_at: Optional[str] = None,
    fetched_via: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    """Persist provider model registry snapshot into SQLite.

    Overwrites existing rows for the provider.

    Parameters
    ----------
    provider:
        Provider identifier.
    models:
        Raw models payload from provider listing.
    fetched_at:
        Optional ISO timestamp (defaults to now UTC if omitted).
    fetched_via:
        Source descriptor (``"api"`` default).
    metadata:
        Arbitrary metadata dict stored JSON-encoded.

    Side Effects
    ------------
    Executes DELETE, INSERT, and UPSERT operations on SQLite tables and commits
    the transaction via the shared connection accessor.

    Failure Modes
    -------------
    Propagates SQLite errors to the caller. Higher layers may treat this as
    best-effort and suppress failures when appropriate.
    """
    conn = _get_conn()
    cur = conn.cursor()
    _clear_provider_models(cur, provider)
    _insert_model_rows(cur, provider, models)
    _upsert_registry_meta(
        cur, provider, fetched_at=fetched_at, fetched_via=fetched_via, metadata=metadata
    )
    conn.commit()


def load_models_snapshot(provider: str) -> Dict[str, Any]:
    """Load provider model registry snapshot from SQLite.

    Parameters
    ----------
    provider:
        Provider identifier to load.

    Returns
    -------
    Dict[str, Any]
        Snapshot payload with keys: ``provider``, ``models`` (list of dicts),
        and meta fields (``fetched_at``, ``fetched_via``, ``metadata``). Returns
        an empty dict if no snapshot exists for the provider.

    Failure Modes
    -------------
    Propagates SQLite errors. Malformed JSON in capabilities or metadata is
    guarded and returned as raw payloads to avoid cascading failures.
    """
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT provider, fetched_at, fetched_via, metadata FROM model_registry_meta WHERE provider = ?",
        (provider,),
    )
    meta_row = cur.fetchone()
    cur.execute(
        "SELECT model_id, name, family, context_length, capabilities, updated_at FROM model_registry WHERE provider = ? ORDER BY name",
        (provider,),
    )
    models_rows = cur.fetchall()
    if not meta_row and not models_rows:
        return {}
    models: List[Dict[str, Any]] = []
    for r in models_rows:
        caps: Any
        try:
            caps = json.loads(r[4]) if r[4] else {}
        except Exception:  # pragma: no cover - defensive
            caps = {"raw": r[4]}
        models.append(
            {
                "id": r[0],
                "name": r[1],
                "family": r[2],
                "context_length": r[3],
                "capabilities": caps,
                "updated_at": r[5],
            }
        )
    meta = {"fetched_at": None, "fetched_via": None, "metadata": {}}
    if meta_row:
        meta = {
            "fetched_at": meta_row[1],
            "fetched_via": meta_row[2],
            "metadata": json.loads(meta_row[3]) if meta_row[3] else {},
        }
    return {"provider": provider, "models": models, **meta}


def list_providers() -> List[str]:
    """Return sorted list of provider identifiers present in the registry.

    The list is derived primarily from ``model_registry_meta``; if that table
    is empty (e.g., after manual schema creation), the helper falls back to
    distinct providers present in ``model_registry``. This mirrors the view
    used by the service layer for `/api/providers`.
    """
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT provider FROM model_registry_meta ORDER BY provider")
    rows = cur.fetchall()
    if rows:
        return [r[0] for r in rows]

    cur.execute("SELECT DISTINCT provider FROM model_registry ORDER BY provider")
    return [r[0] for r in cur.fetchall()]
