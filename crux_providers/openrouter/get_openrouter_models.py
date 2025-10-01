"""
OpenRouter: get models

Behavior
- Attempts to fetch model listings via OpenRouter HTTP API (OpenAI-compatible style):
    GET https://openrouter.ai/api/v1/models
- Persists the normalized snapshot to SQLite via ``save_provider_models``
    (DB-first; no JSON cache file is written).
- If API key (optional for public listing) or HTTP client is unavailable/fails,
    falls back to the cached snapshot from SQLite.

Entry points recognized by the ModelRegistryRepository:
- run()  (preferred)
- get_models()/fetch_models()/update_models()/refresh_models() also provided for convenience
"""

from __future__ import annotations

import contextlib
import os
from typing import Any, Dict, List, Optional

try:
    import requests  # type: ignore
except Exception:
    requests = None  # type: ignore

from ..base.get_models_base import load_cached_models, save_provider_models
from ..base.timeouts import get_timeout_config
from ..base.repositories.keys import KeysRepository
from ..config.defaults import OPENROUTER_DEFAULT_BASE_URL

PROVIDER = "openrouter"


def _resolve_key() -> Optional[str]:
    """Resolves and returns the API key for the OpenRouter provider.

    Retrieves the API key from the KeysRepository for use in authenticated API requests.

    Returns:
        Optional[str]: The API key if available, otherwise None.
    """
    return KeysRepository().get_api_key(PROVIDER)


def _resolve_base_url() -> str:
    """Resolves and returns the base URL for the OpenRouter API.

    Returns the base URL from the OPENROUTER_BASE_URL environment variable, or a default if not set.

    Returns:
        str: The base URL for the OpenRouter API.
    """
    return os.getenv("OPENROUTER_BASE_URL", OPENROUTER_DEFAULT_BASE_URL)


def _fetch_via_http(api_key: Optional[str], base_url: str) -> List[Dict[str, Any]]:
    """Fetches model data from the OpenRouter HTTP API.

    Retrieves a list of available models using the provided API key and base URL.

    Args:
        api_key (Optional[str]): The API key for authentication.
        base_url (str): The base URL for the OpenRouter API.

    Returns:
        List[Dict[str, Any]]: A list of dictionaries representing available models.

    Raises:
        RuntimeError: If the requests library is not available.
    """
    if requests is None:
        raise RuntimeError("requests library not available")
    url = base_url.rstrip("/") + "/models"
    headers = {"Accept": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    timeout_sec = get_timeout_config().start_timeout_seconds
    resp = requests.get(url, headers=headers, timeout=timeout_sec)
    resp.raise_for_status()
    data = resp.json()
    raw = data.get("data", data) if isinstance(data, dict) else data
    items: List[Dict[str, Any]] = []
    for it in raw or []:
        if isinstance(it, dict):
            mid = it.get("id") or it.get("model") or it.get("name") or str(it)
            name = it.get("name") or it.get("id") or str(it)
            row = {"id": str(mid), "name": str(name)}
            for k in (
                "created",
                "context_length",
                "capabilities",
                "description",
                "pricing",
            ):
                if k in it:
                    row[k] = it[k]
            items.append(row)
        else:
            items.append({"id": str(it), "name": str(it)})
    return items


def run() -> List[Dict[str, Any]]:
    """Fetches the list of available models from OpenRouter.

    Attempts to retrieve model data from the OpenRouter API and saves it to the provider cache. Falls back to cached models if the API is unavailable.

    Returns:
        List[Dict[str, Any]]: A list of dictionaries representing available models.
    """
    key = _resolve_key()
    base = _resolve_base_url()
    with contextlib.suppress(Exception):
        if items := _fetch_via_http(key, base):
            save_provider_models(
                PROVIDER,
                items,
                fetched_via="api",
                metadata={"source": "openrouter_http"},
            )
            return items
    snap = load_cached_models(PROVIDER)
    return [m.to_dict() for m in snap.models]


def get_models() -> List[Dict[str, Any]]:  # alias
    """Returns the list of available models from OpenRouter.

    This is an alias for the run() function and provides the same behavior and output.

    Returns:
        List[Dict[str, Any]]: A list of dictionaries representing available models.
    """
    return run()


def fetch_models() -> List[Dict[str, Any]]:
    """Fetches the list of available models from OpenRouter.

    This is an alias for the run() function and provides the same behavior and output.

    Returns:
        List[Dict[str, Any]]: A list of dictionaries representing available models.
    """
    return run()


def update_models() -> List[Dict[str, Any]]:
    """Updates and returns the list of available models from OpenRouter.

    This is an alias for the run() function and provides the same behavior and output.

    Returns:
        List[Dict[str, Any]]: A list of dictionaries representing available models.
    """
    return run()


def refresh_models() -> List[Dict[str, Any]]:
    """Refreshes and returns the list of available models from OpenRouter.

    This is an alias for the run() function and provides the same behavior and output.

    Returns:
        List[Dict[str, Any]]: A list of dictionaries representing available models.
    """
    return run()


if __name__ == "__main__":
    models = run()
    print(f"[openrouter] loaded {len(models)} models")
