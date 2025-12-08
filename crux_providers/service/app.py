from __future__ import annotations

import json
import os
from contextlib import suppress
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware

from crux_providers.persistence.sqlite.engine import create_connection, init_schema
from crux_providers.persistence.interfaces.repos import IUnitOfWork
from crux_providers.config.defaults import PROVIDER_SERVICE_CORS_DEFAULT_ORIGINS

from .app_parts.app_core import (
    ChatBody,
    KeysBody,
    PrefsBody,
    ModelsQuery,
    get_uow_dep,
    _build_env_to_provider_map,
    _build_models_response,
    _build_providers_response,
    _handle_chat,
)


VAULT_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "key_vault"))
DB_PATH = os.path.join(VAULT_DIR, "providers.db")
os.makedirs(VAULT_DIR, exist_ok=True)
# Initialize SQLite schema using the centralized engine helpers. We avoid the
# legacy service/db initializer to keep persistence concerns within the
# persistence layer.
with suppress(Exception):
    conn = create_connection(DB_PATH)
    try:
        init_schema(conn)
    finally:
        conn.close()


app = FastAPI(title="Provider Service", version="0.1.0")


@app.on_event("startup")
def _seed_model_registry_from_catalog() -> None:
    """Seed the SQLite-backed model registry from YAML catalogs when available.

    This runs once at service startup and is best-effort: failures are
    suppressed so that the service can still start even if the catalog or
    PyYAML are misconfigured. Providers can still populate the registry via
    refresh mechanisms when needed.
    """
    try:
        from . import model_catalog_loader
        from crux_providers.base.repositories.model_registry.repository import (
            ModelRegistryRepository,
        )
    except Exception:
        # If the catalog loader or its dependencies are unavailable, skip seeding.
        return
    with suppress(Exception):  # pragma: no cover - best-effort
        repo = ModelRegistryRepository()
        model_catalog_loader.load_model_catalog(repository=repo)


# ---------------------------------------------------------------------------
# CORS configuration
# ---------------------------------------------------------------------------

cors_origins_env = os.getenv(
    "PROVIDER_SERVICE_CORS_ORIGINS", PROVIDER_SERVICE_CORS_DEFAULT_ORIGINS
)
allow_origins = [o.strip() for o in cors_origins_env.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Metrics and health endpoints
# ---------------------------------------------------------------------------


@app.get("/api/metrics/summary")
def get_metrics_summary(uow: IUnitOfWork = Depends(get_uow_dep)) -> Dict[str, Any]:
    """Return metrics summary via DI repository layer.

    Uses `IUnitOfWork.metrics.summary()` which mirrors legacy helper
    contract. This completes migration away from direct `svcdb.metrics_summary`.
    """
    try:
        return {"ok": True, "summary": uow.metrics.summary()}
    except Exception as e:  # pragma: no cover - defensive
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get("/api/health")
def health() -> Dict[str, Any]:
    """Check the health status of the service.

    Returns a simple response indicating the service is running and healthy.
    """
    return {"ok": True}


# ---------------------------------------------------------------------------
# Providers and models endpoints
# ---------------------------------------------------------------------------


@app.get("/api/providers")
def get_providers() -> Dict[str, Any]:
    """List providers present in the model registry.

    This is the canonical source for the IDE's provider list.
    """
    return _build_providers_response()


@app.get("/api/models")
def get_models(provider: str, refresh: bool = False) -> Dict[str, Any]:
    """Retrieve a list of available models for a given provider.

    Returns a snapshot of models if the provider supports model listing,
    otherwise returns an error.
    """
    return _build_models_response(provider, refresh)


# ---------------------------------------------------------------------------
# Key management endpoints
# ---------------------------------------------------------------------------


@app.post("/api/keys")
def post_keys(body: KeysBody, uow: IUnitOfWork = Depends(get_uow_dep)) -> Dict[str, Any]:
    """Store API keys for various providers from the request body.

    Accepts a mapping of environment variable names to API keys and persists
    them for each provider.
    """
    # Accept env-var-style mapping for compatibility; store as provider->key
    stored: List[str] = []
    to_save: Dict[str, str] = {}
    # Build inverse map at runtime to accept canonical and alias names.
    env_to_provider = _build_env_to_provider_map()
    for env_name, key in (body.keys or {}).items():
        provider = env_to_provider.get(env_name)
        if not (provider and isinstance(key, str)):
            continue
        candidate = key.strip()
        # Only persist reasonable, ASCII keys; drop masked/placeholder garbage
        if not candidate:
            continue
        if not candidate.isascii():
            continue
        if set(candidate) == {"*"}:
            continue
        if "placeholder" in candidate.lower():
            continue
        to_save[provider] = candidate
        stored.append(env_name)
    if to_save:
        # Persist via repository abstraction (DI path)
        for provider, key in to_save.items():
            uow.keys.set_api_key(provider, key)
        uow.commit()
    return {"ok": True, "stored": stored}


@app.get("/api/keys")
def get_keys(uow: IUnitOfWork = Depends(get_uow_dep)) -> Dict[str, Any]:
    """Retrieve a masked mapping of API keys for all providers.

    Returns a dictionary indicating which provider keys are set without
    exposing the actual key values.
    """
    from crux_providers.service.helpers import mask_keys_env

    # Return env-var-style masked mapping (DI path)
    providers = uow.keys.list_providers()
    raw: Dict[str, str] = {}
    for p in providers:
        key = uow.keys.get_api_key(p) or ""
        raw[p] = key
    return {"ok": True, "keys": mask_keys_env(raw)}


@app.delete("/api/keys")
def delete_key(provider: str, uow: IUnitOfWork = Depends(get_uow_dep)) -> Dict[str, Any]:
    """Delete a stored key for the given provider (case-insensitive).

    The `provider` identifier must match the canonical provider key used in the
    key vault (for example, ``"openai"``, ``"anthropic"``, etc.).

    TODO future: extend to multi-key per provider with labels for UI dropdowns.
    """
    if not provider:
        raise HTTPException(status_code=400, detail="provider is required")
    try:
        uow.keys.delete_api_key(provider.lower())
        uow.commit()
    except Exception as e:  # pragma: no cover - defensive
        raise HTTPException(status_code=500, detail=str(e)) from e
    return {"ok": True, "deleted": provider.lower()}


# ---------------------------------------------------------------------------
# Preferences endpoints
# ---------------------------------------------------------------------------


@app.post("/api/prefs")
def post_prefs(body: PrefsBody, uow: IUnitOfWork = Depends(get_uow_dep)) -> Dict[str, Any]:
    """Update and store user or system preferences.

    Merges the provided preferences with existing ones and persists the
    updated preferences.
    """
    existing = uow.prefs.get_prefs().values
    existing.update(body.prefs or {})
    updated = uow.prefs.set_prefs(existing).values
    uow.commit()
    return {"ok": True, "prefs": updated}


@app.get("/api/prefs")
def get_prefs(uow: IUnitOfWork = Depends(get_uow_dep)) -> Dict[str, Any]:
    """Retrieve the current user or system preferences."""
    return {"ok": True, "prefs": uow.prefs.get_prefs().values}


# ---------------------------------------------------------------------------
# Chat endpoint
# ---------------------------------------------------------------------------


@app.post("/api/chat")
def post_chat(body: ChatBody, uow: IUnitOfWork = Depends(get_uow_dep)) -> Dict[str, Any]:
    """Process a chat request and return the model's response.

    Validates the request, sets up the provider environment, and returns the
    chat response or an error.
    """
    return _handle_chat(body, uow)


# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------


def get_app() -> FastAPI:
    """Return the FastAPI application instance.

    Provides access to the configured FastAPI app for use in deployment or
    testing.
    """
    return app
