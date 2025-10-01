"""
OpenAI models fetcher.

Purpose
- List available models via the OpenAI SDK and persist a normalized snapshot to
    the SQLite-backed model registry using ``save_provider_models`` (DB-first; no
    JSON cache files are produced).
- Fall back to the last cached snapshot from SQLite when the SDK or API key is
    unavailable.

Capability policy (data-first; no name heuristics)
- Capabilities are derived from declared ``modalities`` only, then merged with
    any previously cached capabilities for the same model id. We do NOT guess
    capabilities from model names (no regex, no family-based heuristics).
- "json_output" is always set to True because the provider accepts structured
    output requests; adapters will still gate per-call behavior.

Timeouts & retries
- Blocking start phases are guarded by ``operation_timeout`` using durations
    from ``get_timeout_config()``. There are no hardcoded numeric timeouts.
- We log one structured fallback event on failure paths and then return cached
    snapshots as per policy.

Entrypoints recognized by the model registry repository:
- ``run()`` (preferred)
- ``get_models()/fetch_models()/update_models()/refresh_models()`` provided for convenience
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from contextlib import suppress

try:
    from openai import OpenAI  # openai>=1.0.0
except Exception:
    OpenAI = None  # type: ignore

from ..base.get_models_base import save_provider_models, load_cached_models
from ..base.models import ModelInfo
from ..base.capabilities import normalize_modalities, merge_capabilities
from ..base.repositories.keys import KeysRepository
from ..base.interfaces_parts.has_data import HasData
from ..base.logging import get_logger, normalized_log_event, LogContext
from ..base.timeouts import get_timeout_config, operation_timeout


PROVIDER = "openai"
_logger = get_logger("providers.openai.models")


def _fetch_via_sdk(api_key: str) -> List[Any]:
    """Fetch raw model listings using the OpenAI SDK.

    Returns a list of SDK objects or dict-like items. This function performs
    no normalization; downstream helpers coerce items into ``ModelInfo``.
    """
    if not OpenAI:
        raise RuntimeError("openai SDK not available")
    client = OpenAI(api_key=api_key)
    resp = client.models.list()
    # Support both object (with `data`) and dict payloads
    if isinstance(resp, HasData):
        data = resp.data  # type: ignore[assignment]
    elif isinstance(resp, dict):
        data = resp.get("data", [])
    else:
        data = getattr(resp, "data", None)
    return list(data or [])


def _resolve_key() -> Optional[str]:
    """Resolve the API key for the OpenAI provider or return None.

    The key is retrieved from the shared ``KeysRepository``; callers should
    gracefully handle the absence of a key by falling back to cached snapshots.
    """
    return KeysRepository().get_api_key(PROVIDER)


def run() -> List[Dict[str, Any]]:
    """Preferred entrypoint: refresh online if possible, else return cached.

    Returns a minimal list of dicts containing ``id`` and ``name`` for display
    and selection. The full normalized snapshot is written to disk via
    ``save_provider_models``.
    """
    key = _resolve_key()
    if not key:
        # No key available — serve cached snapshot and emit one structured log.
        normalized_log_event(
            _logger,
            "models.list.fallback",
            LogContext(provider=PROVIDER, model="models"),
            phase="start",
            attempt=None,
            error_code=None,
            emitted=False,
            provider=PROVIDER,
            operation="fetch_models",
            stage="start",
            failure_class="MissingAPIKey",
            fallback_used=True,
        )
        return _cached_models()
    enriched = _refresh_online(key)
    return enriched if enriched is not None else _cached_models()


# -------------------- Helper Functions (extracted for testability & low CCN) --------------------

def _cached_models() -> List[Dict[str, Any]]:
    """Return cached models as minimal dictionaries (``id`` and ``name``).

    This avoids network calls and preserves quick listing even when offline.
    """
    snap = load_cached_models(PROVIDER)
    return [{"id": m.id, "name": m.name} for m in snap.models]


def _refresh_online(api_key: str) -> Optional[List[Dict[str, Any]]]:
    """Attempt to fetch and persist the latest models via the SDK.

    Builds ``ModelInfo`` objects with data-first capability inference (modalities
    only) and merges any previously cached capabilities for continuity. On failure,
    returns None so the caller can serve the cached snapshot instead.
    """
    if not OpenAI:
        # SDK not installed — log once and allow caller to fallback to cache
        normalized_log_event(
            _logger,
            "models.list.fallback",
            LogContext(provider=PROVIDER, model="models"),
            phase="start",
            attempt=None,
            error_code=None,
            emitted=False,
            provider=PROVIDER,
            operation="fetch_models",
            stage="start",
            failure_class="SDKUnavailable",
            fallback_used=True,
        )
        return None
    try:
        timeout_cfg = get_timeout_config()
        with operation_timeout(timeout_cfg.start_timeout_seconds):
            items = _fetch_via_sdk(api_key)
    except Exception as e:  # noqa: BLE001 - broad guard with structured fallback log
        normalized_log_event(
            _logger,
            "models.list.error",
            LogContext(provider=PROVIDER, model="models"),
            phase="start",
            attempt=None,
            error_code=None,
            emitted=False,
            provider=PROVIDER,
            operation="fetch_models",
            stage="start",
            failure_class=e.__class__.__name__,
            fallback_used=True,
        )
        return None

    # Map cached capabilities by model id for merge (data-first, no heuristics)
    cached = load_cached_models(PROVIDER)
    cached_caps: Dict[str, Dict[str, Any]] = {m.id: (m.capabilities or {}) for m in cached.models}

    client = OpenAI(api_key=api_key)
    enriched: List[ModelInfo] = []
    for it in items:
        mi = _enrich_item_to_modelinfo(it, client, cached_caps)
        if mi is not None:
            enriched.append(mi)

    # Persist best-effort snapshot (already normalized ModelInfo → no extra inference)
    save_provider_models(
        PROVIDER,
        enriched,
        fetched_via="api",
        metadata={
            "source": "openai_sdk_enriched",
            "capability_policy": "modalities+cached_merge",
        },
    )
    # Emit a single normalized success event with a small summary
    normalized_log_event(
        _logger,
        "models.list.ok",
        LogContext(provider=PROVIDER, model="models"),
        phase="finalize",
        attempt=None,
        error_code=None,
        emitted=True,
        provider=PROVIDER,
        operation="fetch_models",
        stage="finalize",
        count=len(enriched),
    )
    # Return simplified list required by registry usage (id + name)
    return [{"id": it.id, "name": it.name} for it in enriched]


def _enrich_item_to_modelinfo(
    it: Any, client: Any, cached_caps: Dict[str, Dict[str, Any]]
) -> Optional[ModelInfo]:
    """Convert a raw SDK item to ``ModelInfo`` with data-first capabilities.

    - Extracts id/name and a best-effort context length from either the list item
      or a per-model retrieve() call when available.
    - Derives capabilities from declared ``modalities`` only, then merges with
      any cached capabilities for the same id. Always sets ``json_output=True``.

    Returns ``None`` if an id cannot be determined.
    """
    mid = _first_attr(it, ("id", "model", "name"))
    if not mid:
        return None
    name = _first_attr(it, ("name", "id")) or str(mid)

    det = None
    with suppress(Exception):
        det = client.models.retrieve(str(mid))  # type: ignore[assignment]

    modalities = _first_attr(det, ("modalities",)) or _first_attr(it, ("modalities",))
    input_token_limit = (
        _first_attr(det, ("input_token_limit", "context_window"))
        or _first_attr(it, ("input_token_limit",))
    )
    created = _first_attr(det, ("created",)) or _first_attr(it, ("created",))
    context_length = (
        _first_attr(det, ("context_length",))
        or _first_attr(it, ("context_length", "max_context"))
    )

    if context_length is None and input_token_limit is not None:
        context_length = input_token_limit

    # Capabilities: modalities → caps; merge with cached; ensure json_output
    caps = normalize_modalities(modalities)
    prior = cached_caps.get(str(mid)) or {}
    caps = merge_capabilities(prior, caps)
    caps.setdefault("json_output", True)

    ctx_int: Optional[int] = None
    if context_length is not None:
        with suppress(Exception):
            ctx_int = int(context_length)

    mi = ModelInfo(
        id=str(mid),
        name=str(name),
        provider=PROVIDER,
        family=None,
        context_length=ctx_int,
        capabilities=caps,
        updated_at=None,
    )
    # For completeness, set updated_at from created epoch if available
    if isinstance(created, (int, float)):
        with suppress(Exception):
            mi.updated_at = None  # Keep date derivation to base if needed elsewhere
    return mi


def _first_attr(obj: Any, names) -> Any:
    """Return the first non-None attribute or dict key value found.

    Tries attribute access first (for SDK objects), then falls back to dict
    key lookup when ``obj`` is a mapping-like. Narrow guards avoid masking
    unrelated errors.
    """
    if obj is None:
        return None
    for n in names:
        try:
            val = getattr(obj, n, None)
        except Exception:
            val = None
        if val is not None:
            return val
        if isinstance(obj, dict) and n in obj:
            return obj.get(n)
    return None


# Local helpers removed in favor of base.capabilities functions


# Aliases for repository compatibility
def get_models() -> List[Dict[str, Any]]:
    """Return a list of available OpenAI models.

    This function is an alias for the preferred entrypoint ``run()`` and provides
    a minimal list of model dictionaries for compatibility with the model registry.

    Returns:
        List[Dict[str, Any]]: A list of dictionaries, each containing ``id`` and ``name`` keys.
    """
    return run()


def fetch_models() -> List[Dict[str, Any]]:
    """Return a list of available OpenAI models.

    This function is an alias for the preferred entrypoint ``run()`` and provides
    a minimal list of model dictionaries for compatibility with the model registry.

    Returns:
        List[Dict[str, Any]]: A list of dictionaries, each containing ``id`` and ``name`` keys.
    """
    return run()


def update_models() -> List[Dict[str, Any]]:
    """Return a list of available OpenAI models.

    This function is an alias for the preferred entrypoint ``run()`` and provides
    a minimal list of model dictionaries for compatibility with the model registry.

    Returns:
        List[Dict[str, Any]]: A list of dictionaries, each containing ``id`` and ``name`` keys.
    """
    return run()


def refresh_models() -> List[Dict[str, Any]]:
    """Return a list of available OpenAI models.

    This function is an alias for the preferred entrypoint ``run()`` and provides
    a minimal list of model dictionaries for compatibility with the model registry.

    Returns:
        List[Dict[str, Any]]: A list of dictionaries, each containing ``id`` and ``name`` keys.
    """
    return run()


if __name__ == "__main__":
    models = run()
    print(f"[openai] loaded {len(models)} models")
