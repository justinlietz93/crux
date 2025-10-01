"""
DeepSeek: get models

Behavior
- Attempts to fetch model listings from DeepSeek's OpenAI-compatible HTTP endpoint:
    GET {DEEPSEEK_BASE_URL or https://api.deepseek.com/v1}/models
- Persists the normalized snapshot to SQLite via ``save_provider_models``
    (DB-first; no JSON cache file is written).
- If API key or HTTP client is unavailable or fails, falls back to the cached
    snapshot from SQLite (no network).

Entry points recognized by the ModelRegistryRepository:
- run()  (preferred)
- get_models()/fetch_models()/update_models()/refresh_models() also provided for convenience
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

try:
    import requests  # type: ignore
except Exception:
    requests = None  # type: ignore

from ..base.get_models_base import save_provider_models, load_cached_models
from ..base.timeouts import get_timeout_config
from contextlib import suppress
from ..base.repositories.keys import KeysRepository
from ..config.defaults import DEEPSEEK_DEFAULT_BASE_URL

PROVIDER = "deepseek"


def _resolve_key() -> Optional[str]:
    return KeysRepository().get_api_key(PROVIDER)


def _resolve_base_url() -> str:
    # Default to the documented base; allow override via env
    return os.getenv("DEEPSEEK_BASE_URL", DEEPSEEK_DEFAULT_BASE_URL)


def _fetch_via_http(api_key: str, base_url: str) -> List[Dict[str, Any]]:
    """
    Fetch model listings using OpenAI-compatible HTTP endpoint.

    Returns a list of dicts with at least {'id', 'name'} keys.
    """
    if requests is None:
        raise RuntimeError("requests library not available")

    url = base_url.rstrip("/") + "/models"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
    }
    # Use unified provider start timeout; DeepSeek models fetch is a simple GET.
    timeout_cfg = get_timeout_config()
    resp = requests.get(url, headers=headers, timeout=timeout_cfg.start_timeout_seconds)
    resp.raise_for_status()
    data = resp.json()

    # Accept either a plain list or {"data": [...]}
    raw = data.get("data", data) if isinstance(data, dict) else data
    items: List[Dict[str, Any]] = []
    for it in raw or []:
        if isinstance(it, dict):
            # Normalize id/name
            mid = it.get("id") or it.get("model") or it.get("name") or str(it)
            name = it.get("name") or it.get("id") or str(it)
            row = {"id": str(mid), "name": str(name)}
            # Passthrough useful fields when present
            for k in ("created", "modalities", "context_length", "max_context", "capabilities"):
                if k in it:
                    row[k] = it[k]
            items.append(row)
        else:
            items.append({"id": str(it), "name": str(it)})
    return items


def run() -> List[Dict[str, Any]]:
    """Fetch models, preferring live HTTP then falling back to cached snapshot.

    Returns list of model dictionaries compatible with ModelRegistryRepository.
    Network errors are suppressed (we fall back to cache). Uses unified timeout
    via :func:`get_timeout_config` in `_fetch_via_http` invocation.
    """
    if key := _resolve_key():  # noqa: SIM115 (clarity)  # type: ignore[assignment]
        with suppress(Exception):  # network failure, auth, JSON, etc.
            base = _resolve_base_url()
            if items := _fetch_via_http(key, base):  # noqa: SIM901 explicit for readability
                save_provider_models(
                    PROVIDER,
                    items,
                    fetched_via="api",
                    metadata={"source": "deepseek_http_models"},
                )
                return items
    snap = load_cached_models(PROVIDER)
    return [m.to_dict() for m in snap.models]


# Aliases for repository compatibility
def get_models() -> List[Dict[str, Any]]:
    return run()


def fetch_models() -> List[Dict[str, Any]]:
    return run()


def update_models() -> List[Dict[str, Any]]:
    return run()


def refresh_models() -> List[Dict[str, Any]]:
    return run()


if __name__ == "__main__":
    models = run()
    print(f"[deepseek] loaded {len(models)} models")
