"""
Utilities for provider model registry fetchers.

This module provides helpers shared by provider-specific "get models" scripts:
- Normalization of raw API results into ModelInfo DTOs
- Saving snapshots to the authoritative SQLite database (DB-first policy)
- Loading cached snapshots from the database when online refresh fails

Intended usage (inside provider script):
    from src.infrastructure.providers.base.get_models_base import save_provider_models, load_cached_models
    items = fetch_from_api()  # list of dicts/SDK objects
    save_provider_models("openai", items, fetched_via="api", metadata={"source": "openai_api"})
"""

from __future__ import annotations

import contextlib
import re
from datetime import datetime, timezone
# pathlib.Path no longer needed; snapshots persist to DB only
from typing import Any, Dict, Iterable, List, Optional

from .models import ModelInfo, ModelRegistrySnapshot
from .repositories.model_registry.repository import ModelRegistryRepository


def _now_iso() -> str:
    """Return the current UTC time as an ISO 8601 formatted string.

    Used for timestamping model registry snapshots and updates.
    """
    return datetime.now(timezone.utc).isoformat()


def _as_dict(obj: Any) -> Dict[str, Any]:
    """
    Best-effort conversion of SDK objects to dicts by probing common attributes.
    """
    if isinstance(obj, dict):
        return obj
    d: Dict[str, Any] = {}
    # Probe common attributes found on SDK objects; tolerate absence.
    for attr in (
        "id",
        "name",
        "slug",
        "model",
        "display_name",
        "family",
        "series",
        "context_length",
        "max_context",
        # Additional candidates that may exist on some SDK objects
        "created",  # epoch seconds
        "modalities",  # e.g., ["text","vision","audio"]
        "input_token_limit",  # sometimes exposed as per-model token limit
        "max_output_tokens",  # optional output cap (not mapped directly)
        "capabilities",  # provider-defined capabilities if present
    ):
        v = getattr(obj, attr, None)
        if v is not None:
            d[attr] = v
    # OpenAI often nests under .data; ignore here
    return d


def _best_id(d: Dict[str, Any]) -> str:
    """Pick the most appropriate model identifier from a flexible mapping."""
    return str(
        d.get("id") or d.get("model") or d.get("name") or d.get("slug") or "unknown"
    )


def _best_name(d: Dict[str, Any], fallback_id: str) -> str:
    """Pick the most display-friendly model name from a flexible mapping."""
    return str(
        d.get("name")
        or d.get("display_name")
        or d.get("id")
        or d.get("model")
        or fallback_id
    )


def _norm_name_id(d: Dict[str, Any]) -> tuple[str, str]:
    """Determine (id, name) from a flexible dict using best-effort rules."""
    sid = _best_id(d)
    name = _best_name(d, sid)
    return sid, name


def _infer_updated_at_from_id(model_id: str) -> Optional[str]:
    """
    Infer an ISO-like YYYY-MM-DD date from the model id when present, e.g.:
    'gpt-4o-mini-search-preview-2025-03-11' -> '2025-03-11'
    """
    m = re.search(r"\b(20\d{2}-\d{2}-\d{2})\b", model_id)
    # Use group(1) explicitly (Match objects are not safely subscriptable in all linters)
    return m[1] if m else None


def _openai_family_from_lower(lower: str) -> Optional[str]:
    """Infer OpenAI family from a lowercase model id string."""
    if "gpt-4o-mini" in lower:
        return "gpt-4o-mini"
    if "gpt-4o" in lower:
        return "gpt-4o"
    if lower.startswith("o3"):
        return "o3"
    if lower.startswith("o1"):
        return "o1"
    return "gpt-4" if lower.startswith("gpt-4") else None


def _infer_family_from_id(model_id: str, provider: str) -> Optional[str]:
    """Infer a reasonable 'family' string from the model id for known providers."""
    lower = (model_id or "").lower()
    if provider == "openai":
        if fam := _openai_family_from_lower(lower):
            return fam
    # generic fallback: first token by dash/colon
    first = re.split(r"[-:]", lower)[0]
    return first or None


def _extract_family(provider: str, sid: str, d: Dict[str, Any]) -> Optional[str]:
    """Return explicit family/series field if present; else infer from id."""
    fam = d.get("family") or d.get("series")
    if not isinstance(fam, str) or not fam:
        return _infer_family_from_id(sid, provider)
    return fam


def _ctx_candidate(d: Dict[str, Any]) -> Any:
    """Return the most likely context length value from a model data dictionary.

    Scans for common keys that may represent context length in provider payloads.
    """
    return (
        d.get("context_length")
        or d.get("max_context")
        or d.get("ctx")
        or d.get("input_token_limit")
        or d.get("context_window")
    )


_CTX_SUFFIX_MULTIPLIERS = {"k": 1_000, "m": 1_000_000}
_CTX_TRAILING_TOKENS = ("tokens", "token", "ctx", "context", "window")


def _parse_ctx_string(raw: str) -> Optional[int]:
    """Parse a context length string and return its integer value if possible.

    Handles common suffixes (k, m) and strips known trailing tokens for normalization.

    Args:
        raw: The raw string representing context length.

    Returns:
        Optional[int]: The parsed context length as an integer, or None if parsing fails.
    """
    s = raw.strip().lower()
    for token in _CTX_TRAILING_TOKENS:
        if s.endswith(token):
            s = s[: -len(token)].strip()
    plain = s.replace(",", "").replace("_", "")
    if m := re.match(r"^(\d+(?:\.\d+)?)\s*([km])?$", plain):
        num_s, suf = m.groups()
        with contextlib.suppress(Exception):
            val = float(num_s)
            if suf:
                val *= _CTX_SUFFIX_MULTIPLIERS[suf]
            return int(val)
        return None
    if m2 := re.search(r"(\d{2,7})", plain):
        with contextlib.suppress(Exception):
            return int(m2[1])
    return None


def _extract_context_length(d: Dict[str, Any]) -> Optional[int]:
    """Return normalized context length (int) or None (low CCN).

    Strategy:
    1. Scan candidate keys.
    2. Fast-path numeric types.
    3. Parse string with single regex + fallback digits.
    """
    val = _ctx_candidate(d)
    if not val or isinstance(val, bool):
        return None
    if isinstance(val, (int, float)):
        return int(val) if val >= 0 else None
    return _parse_ctx_string(val) if isinstance(val, str) else None


def _apply_modalities_to_caps(mods: Any, caps: Dict[str, Any]) -> None:
    """Enrich capabilities dict using a 'modalities' list from provider payloads."""
    if isinstance(mods, (list, tuple)):
        for m in mods:
            mstr = str(m).lower()
            caps[mstr] = True
            # Normalize common synonyms
            if mstr in {"image", "vision"}:
                caps["vision"] = True


_OPENAI_CAP_RULES = [
    ("reasoning", lambda lbda: lbda.startswith("o1") or lbda.startswith("o3")),
    ("responses_api", lambda lbda: lbda.startswith("o1") or lbda.startswith("o3")),
    ("vision", lambda lbda: any(x in lbda for x in ("gpt-4o", "omni", "vision"))),
    ("embedding", lambda lbda: "embedding" in lbda or lbda.startswith("text-embedding")),
    ("search", lambda lbda: "search" in lbda),
]


def _infer_caps(provider: str, model_id: str) -> Dict[str, Any]:
    """Infer a set of capabilities for a model based on provider and model id.

    Returns a dictionary of capability flags inferred from provider-specific rules.

    Args:
        provider: The provider name.
        model_id: The model identifier.

    Returns:
        A dictionary of inferred capabilities for the model.
    """
    if provider != "openai":
        return {}
    model_lower = (model_id or "").lower()
    caps = {name: True for name, pred in _OPENAI_CAP_RULES if pred(model_lower)}
    caps.setdefault("json_output", True)
    return caps


def _normalize_capabilities(
    d: Dict[str, Any], provider: str, sid: str
) -> Dict[str, Any]:
    """Normalize and enrich the capabilities dictionary for a model.

    Merges provider-inferred capabilities with those found in the model's data, including modalities.

    Args:
        d: The dictionary containing model data.
        provider: The provider name.
        sid: The model identifier.

    Returns:
        A dictionary of normalized capabilities for the model.
    """
    caps = d.get("capabilities")
    if caps is None:
        caps = {}
    elif not isinstance(caps, dict):
        caps = {"raw_capabilities": caps}
    _apply_modalities_to_caps(d.get("modalities"), caps)
    if not caps:
        return _infer_caps(provider, sid)
    # Non-destructive merge
    return {**_infer_caps(provider, sid), **caps}


def _updated_at_from_fields(d: Dict[str, Any], sid: str) -> Optional[str]:
    """
    Determine the most accurate updated date for a model from available fields.

    Attempts to use 'updated_at', infer from the model id, or convert a 'created' timestamp.
    """
    updated = d.get("updated_at") if isinstance(d.get("updated_at"), str) else None
    if updated:
        return updated
    if inferred_date := _infer_updated_at_from_id(sid):
        return inferred_date
    if isinstance(d.get("created"), (int, float)):
        with contextlib.suppress(Exception):
            return (
                datetime.fromtimestamp(d["created"], tz=timezone.utc).date().isoformat()
            )
    return None


def _modelinfo_from_item(provider: str, it: Any) -> Optional[ModelInfo]:
    """Coerce a single item (dict/SDK object/ModelInfo) into a ModelInfo or None."""
    if isinstance(it, ModelInfo):
        return it
    d = _as_dict(it)
    sid, name = _norm_name_id(d)
    fam = _extract_family(provider, sid, d)
    ctx_int = _extract_context_length(d)
    caps = _normalize_capabilities(d, provider, sid)
    updated = _updated_at_from_fields(d, sid)
    return ModelInfo(
        id=sid,
        name=name,
        provider=provider,
        family=fam if isinstance(fam, str) and fam else None,
        context_length=ctx_int,
        capabilities=caps,
        updated_at=updated,
    )


def normalize_items(provider: str, items: Iterable[Any]) -> List[ModelInfo]:
    """Convert arbitrary items (dicts/SDK objects/ModelInfo) into ModelInfo list."""
    out: List[ModelInfo] = []
    for it in items or []:
        mi = _modelinfo_from_item(provider, it)
        if mi is not None:
            out.append(mi)
    return out


def save_provider_models(
    provider: str,
    items: Iterable[Any],
    fetched_via: str = "api",
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Normalize and persist a provider model registry snapshot to SQLite.

    Summary:
        Converts arbitrary provider items into :class:`ModelInfo` instances,
        constructs a :class:`ModelRegistrySnapshot`, and persists it to the
        database via :class:`ModelRegistryRepository`. JSON cache files are no
        longer produced; SQLite is the single source of truth.

    Parameters:
        provider: Provider name (e.g., "openai").
        items: Iterable of raw items (dicts/SDK objects/ModelInfo) to normalize.
        fetched_via: Descriptor for how the snapshot was fetched (e.g., "api").
        metadata: Optional metadata mapping to store alongside the snapshot.

    Returns:
        None. Callers can access the latest snapshot via ``load_cached_models``
        or ``ModelRegistryRepository.list_models(provider, refresh=False)``.
    """
    models = normalize_items(provider, items)
    snapshot = ModelRegistrySnapshot(
        provider=provider,
        models=models,
        fetched_via=fetched_via,
        fetched_at=_now_iso(),
        metadata=metadata or {},
    )
    repo = ModelRegistryRepository()
    repo.save_snapshot(snapshot)


def load_cached_models(provider: str) -> ModelRegistrySnapshot:
    """Load the last-saved snapshot from the database without refreshing."""
    repo = ModelRegistryRepository()
    return repo.list_models(provider, refresh=False)
