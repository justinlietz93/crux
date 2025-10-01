"""
Gemini: get models

Behavior
- Attempts to fetch model listings via Google Generative AI SDK (google-generativeai).
- Persists the normalized snapshot to SQLite via ``save_provider_models``
    (DB-first; no JSON cache file is written).
- If API key or SDK is unavailable, falls back to the cached snapshot from
    SQLite (no network).

Entry points recognized by the ModelRegistryRepository:
- run()  (preferred)
- get_models()/fetch_models()/update_models()/refresh_models() also provided for convenience
"""


from __future__ import annotations

import contextlib
from typing import Any, Dict, List, Optional

try:
    import google.generativeai as genai  # pip install google-generativeai
except Exception:
    genai = None  # type: ignore

from ..base.get_models_base import save_provider_models, load_cached_models
from ..base.interfaces_parts.has_name_and_limits import HasName, HasNameAndLimits
from ..base.repositories.keys import KeysRepository


PROVIDER = "gemini"


def _fetch_via_sdk(api_key: str) -> List[Any]:
    """Fetch model listings using the Google Generative AI SDK.

    Parameters
    ----------
    api_key: str
        The API key used to authenticate with the Google Generative AI SDK.

    Returns
    -------
    List[Any]
        A list of SDK model objects (opaque types) or dictionaries representing
        models. The exact shape depends on the installed SDK version.

    Raises
    ------
    RuntimeError
        If the ``google-generativeai`` SDK is not available.
    """
    if genai is None:
        raise RuntimeError("google-generativeai SDK not available")

    # Configure API key
    genai.configure(api_key=api_key)

    return list(genai.list_models())


def _resolve_key() -> Optional[str]:
    # GEMINI_API_KEY via KeysRepository
    return KeysRepository().get_api_key(PROVIDER)


def run() -> List[Dict[str, Any]]:
    """Preferred entrypoint for Gemini model listing.

    Behavior
    --------
    - Attempts an online refresh using the SDK when a key is available.
    - Persists the raw items to the provider models cache.
    - Returns a normalized list of dictionaries for repository consumers.

    Fallback: If the SDK call fails or no key is configured, returns the cached
    snapshot models.
    """
    if key := _resolve_key():
        with contextlib.suppress(Exception):
            items = _fetch_via_sdk(key)
            # Persist normalized snapshot
            save_provider_models(PROVIDER, items, fetched_via="api", metadata={"source": "google_generativeai"})
            # Return lightweight list of dicts
            out: List[Dict[str, Any]] = []
            for it in items:
                # Prefer structural typing over getattr chains
                if isinstance(it, HasNameAndLimits):
                    name = it.name
                    input_limit = it.input_token_limit
                    output_limit = it.output_token_limit
                elif isinstance(it, HasName):
                    name = it.name
                    # Limits may be absent in older SDKs; avoid dynamic lookup
                    input_limit = None
                    output_limit = None
                else:
                    # Best-effort fallback without dynamic attribute access
                    name = str(it)
                    input_limit = None
                    output_limit = None

                out.append(
                    {
                        "id": name,
                        "name": name,
                        "input_token_limit": input_limit,
                        "output_token_limit": output_limit,
                    }
                )
            return out
    snap = load_cached_models(PROVIDER)
    return [m.to_dict() for m in snap.models]


# Aliases for repository compatibility
def get_models() -> List[Dict[str, Any]]:
    """Return the list of Gemini models, preferring an online refresh.

    This is an alias for run() to support repository compatibility.
    """
    return run()


def fetch_models() -> List[Dict[str, Any]]:
    return run()


def update_models() -> List[Dict[str, Any]]:
    return run()


def refresh_models() -> List[Dict[str, Any]]:
    return run()


if __name__ == "__main__":
    models = run()
    print(f"[gemini] loaded {len(models)} models")
