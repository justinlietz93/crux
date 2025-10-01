"""Model registry persistence helpers (extracted from db.py).

Separating these routines from the main db module reduces its size and
cyclomatic complexity while keeping a stable public API via re-export in
`db.py`.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
import sqlite3
import contextlib

from .db import _get_conn  # type: ignore  # internal usage acceptable


# ------------------------ Normalization helpers -------------------------

def _normalize_model_entry(
    m: Any,
) -> Tuple[str, str, Optional[str], Optional[int], Dict[str, Any], Optional[str]]:
    if isinstance(m, dict):
        return _normalize_model_entry_from_dict(m)
    s = str(m)
    return s, s, None, None, {}, None


def _normalize_model_entry_from_dict(
    m: Dict[str, Any],
) -> Tuple[str, str, Optional[str], Optional[int], Dict[str, Any], Optional[str]]:
    mid = str(m.get("id") or m.get("model") or m.get("name") or "unknown")
    name = str(m.get("name") or m.get("id") or mid)
    family = m.get("family") if isinstance(m.get("family"), str) else None
    ctx_int = _parse_context_length(m.get("context_length"))
    caps = _normalize_capabilities(m.get("capabilities"))
    updated = m.get("updated_at") if isinstance(m.get("updated_at"), str) else None
    return mid, name, family, ctx_int, caps, updated


def _parse_context_length(val: Any) -> Optional[int]:
    try:
        return int(val) if val is not None else None
    except (TypeError, ValueError):  # pragma: no cover - defensive
        return None


def _normalize_capabilities(caps: Any) -> Dict[str, Any]:
    if isinstance(caps, dict):
        return caps
    return {} if caps is None else {"raw_capabilities": caps}


def _json_dump(obj: Any) -> str:
    with contextlib.suppress(Exception):  # pragma: no cover - defensive
        return json.dumps(obj)
    return json.dumps({"raw": str(obj)})


# --------------------------- DB write helpers ---------------------------

def _clear_provider_models(cur: sqlite3.Cursor, provider: str) -> None:
    cur.execute("DELETE FROM model_registry WHERE provider = ?", (provider,))


def _insert_model_rows(cur: sqlite3.Cursor, provider: str, models: Any) -> None:
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
    """Load provider model registry snapshot from SQLite. Returns empty if none."""
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


__all__ = ["save_models_snapshot", "load_models_snapshot"]
