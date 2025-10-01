"""Parsing and normalization helpers for model registry results.

These utilities convert flexible provider model listings (often loosely
typed API payloads) into normalized `ModelInfo` objects and structured
metadata that the repository can persist and serve.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from ...models import ModelInfo


def now_iso() -> str:
    """Return the current UTC timestamp in ISO 8601 format."""
    return datetime.now(timezone.utc).isoformat()


def extract_meta_and_raw(data: Any) -> Tuple[Dict[str, Any], List[Any]]:
    """Split a flexible payload into metadata and raw model entries.

    Accepts either a mapping with a `models` (or `data`) list or a plain list.

    Args:
        data: Arbitrary payload (dict or list) returned by a provider.

    Returns:
        A pair of (metadata, raw_entries).
    """
    meta: Dict[str, Any] = {}
    raw: List[Any] = []
    if isinstance(data, dict):
        for k in ("provider", "source", "fetched_via", "fetched_at", "metadata"):
            if k in data:
                meta[k] = data[k]
        if isinstance(data.get("models"), list):
            raw = data["models"]
        elif isinstance(data.get("data"), list):
            raw = data["data"]
    elif isinstance(data, list):
        raw = data
    return meta, raw


def coerce_to_model(provider: str, item: Any) -> ModelInfo:
    """Convert a flexible item into a `ModelInfo` instance.

    Args:
        provider: Provider name to assign on the resulting model.
        item: Either an existing `ModelInfo`, a dict, or any stringifiable value.

    Returns:
        A normalized `ModelInfo`.
    """
    if isinstance(item, ModelInfo):
        return item
    if isinstance(item, dict):
        return model_from_dict(provider, item)
    sid = str(item)
    return ModelInfo(id=sid, name=sid, provider=provider)


def model_from_dict(provider: str, d: Dict[str, Any]) -> ModelInfo:
    """Create a `ModelInfo` from a provider-sourced mapping.

    Normalizes common fields like id/name/family/context_length and preserves
    capabilities where available.

    Args:
        provider: Provider name to assign.
        d: Mapping describing the model (id/name/etc.).

    Returns:
        A normalized `ModelInfo` instance.
    """
    mid, name = _norm_id_name(d)
    fam = _extract_family(d)
    ctx = _extract_context(d)
    caps = _normalize_caps(d.get("capabilities"))
    updated_at = _extract_updated(d)
    return ModelInfo(
        id=mid,
        name=name,
        provider=provider,
        family=fam,
        context_length=ctx,
        capabilities=caps,
        updated_at=updated_at,
    )


def normalize_result(
    provider: str, result: Any
) -> Tuple[List[ModelInfo], Dict[str, Any]]:
    """Normalize a provider refresh result into models and metadata.

    Supports list, dict-with-models, or single object payloads.

    Args:
        provider: Provider name.
        result: Arbitrary refresh payload.

    Returns:
        (models, metadata) where models is a list of `ModelInfo`.
    """
    if result is None:
        return [], {}
    meta: Dict[str, Any] = {"fetched_via": "api", "fetched_at": now_iso()}
    try:
        if isinstance(result, list):
            models = _models_from_list(provider, result)
        elif isinstance(result, dict):
            models, extra = _models_from_dict(provider, result)
            meta |= extra
        else:
            models = [coerce_to_model(provider, result)]
    except Exception:
        return [], {}
    return [m for m in models if isinstance(m, ModelInfo)], meta


def _models_from_list(provider: str, items: List[Any]) -> List[ModelInfo]:
    """
    Converts a list of items into a list of ModelInfo objects for the given provider.

    Each item is normalized using coerce_to_model to ensure consistent ModelInfo output.

    Args:
        provider (str): The provider name.
        items (List[Any]): The list of items to convert.

    Returns:
        List[ModelInfo]: The list of normalized ModelInfo objects.
    """
    return [coerce_to_model(provider, it) for it in items]


def _models_from_dict(
    provider: str, d: Dict[str, Any]
) -> Tuple[List[ModelInfo], Dict[str, Any]]:
    """
    Converts a dictionary containing model data into a list of ModelInfo objects and extracts extra metadata.

    Extracts the 'models' list and known metadata fields such as 'fetched_via', 'source', and 'fetched_at'.

    Args:
        provider (str): The provider name.
        d (Dict[str, Any]): The dictionary containing model data and metadata.

    Returns:
        Tuple[List[ModelInfo], Dict[str, Any]]: The list of ModelInfo objects and a dictionary of extra metadata.
    """
    items = d.get("models") if isinstance(d.get("models"), list) else []
    models = _models_from_list(provider, items)
    extra: Dict[str, Any] = {}
    for k in ("fetched_via", "source", "fetched_at"):
        v = d.get(k)
        if isinstance(v, str):
            extra[k] = v
    return models, extra


def _norm_id_name(d: Dict[str, Any]) -> Tuple[str, str]:
    """Return (model_id, name) using ordered candidate lists (low CCN)."""
    def first_match(keys: List[str]) -> Optional[str]:
        for k in keys:
            v = d.get(k)
            if isinstance(v, (str, int)):
                return str(v)
        return None

    mid = first_match(["id", "model_id", "modelId", "model", "slug", "name"]) or "unknown"
    name_val = first_match(["name", "model_name", "modelName", "id", "model", "slug"]) or mid
    return mid, name_val


def _extract_family(d: Dict[str, Any]) -> Optional[str]:
    """
    Extracts the model family from a dictionary.

    Returns the value of the 'family' or 'series' field if present and a string, otherwise returns None.

    Args:
        d (Dict[str, Any]): The dictionary representing the model.

    Returns:
        Optional[str]: The model family, or None if not found.
    """
    fam = d.get("family") or d.get("series")
    return fam if isinstance(fam, str) else None


def _extract_context(d: Dict[str, Any]) -> Optional[int]:
    """
    Extracts the context length from a dictionary.

    Handles multiple possible field names and converts the value to an integer if possible. Returns None if not found or invalid.

    Args:
        d (Dict[str, Any]): The dictionary representing the model.

    Returns:
        Optional[int]: The context length, or None if not found or invalid.
    """
    ctx = d.get("context_length") or d.get("max_context") or d.get("ctx")
    try:
        return int(ctx) if ctx is not None else None
    except Exception:
        return None


def _normalize_caps(caps: Any) -> Dict[str, Any]:
    """
    Normalizes the capabilities field to a dictionary.

    If the input is not a dictionary, wraps it in a dictionary under the 'raw_capabilities' key.

    Args:
        caps (Any): The capabilities value.

    Returns:
        Dict[str, Any]: The normalized capabilities dictionary.
    """
    if caps is None:
        return {}
    return caps if isinstance(caps, dict) else {"raw_capabilities": caps}


def _extract_updated(d: Dict[str, Any]) -> Optional[str]:
    """
    Extracts the updated_at timestamp from a dictionary.

    Returns the value of the 'updated_at' or 'fetched_at' field if present and a string, otherwise returns None.

    Args:
        d (Dict[str, Any]): The dictionary representing the model.

    Returns:
        Optional[str]: The updated_at timestamp, or None if not found.
    """
    updated_at = d.get("updated_at") or d.get("fetched_at")
    return updated_at if isinstance(updated_at, str) else None


__all__ = [
    "now_iso",
    "extract_meta_and_raw",
    "coerce_to_model",
    "model_from_dict",
    "normalize_result",
]
