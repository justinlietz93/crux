from __future__ import annotations

import json
import os
from contextlib import suppress
from typing import Any, Dict, List, Optional, Iterator

from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ValidationError

from crux_providers.base.factory import (
    ProviderFactory,
    UnknownProviderError,
)
from crux_providers.base.interfaces_parts.supports_streaming import SupportsStreaming
from crux_providers.persistence.sqlite import get_uow
from crux_providers.persistence.sqlite.engine import create_connection, init_schema
from crux_providers.persistence.interfaces.repos import IUnitOfWork
from crux_providers.service.helpers import (
    build_chat_request,
    chat_with_metrics,
    mask_keys_env,
    set_env_for_provider,
)
from crux_providers.base.dto import ChatRequestDTO, MessageDTO
from crux_providers.config.defaults import (
    PROVIDER_SERVICE_CORS_DEFAULT_ORIGINS,
)
from crux_providers.config.env import ENV_ALIASES, ENV_MAP

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


class ChatMessageDTO(BaseModel):
    """Represents a single chat message with a role and content.

    Used to encapsulate the role (e.g., user, assistant) and the message content for chat interactions.
    """
    role: str
    content: Any


class ChatBody(BaseModel):
    """Represents the body of a chat request containing provider, model, and message details.

    Encapsulates all parameters required to initiate a chat, including optional settings and extra data.
    """
    provider: str
    model: str
    messages: List[ChatMessageDTO]
    max_tokens: Optional[int] = None
    temperature: Optional[float] = None
    response_format: Optional[str] = None
    json_schema: Optional[Dict[str, Any]] = None
    tools: Optional[List[Dict[str, Any]]] = None
    extra: Dict[str, Any] = {}


class KeysBody(BaseModel):
    """Represents a request body containing API keys for various providers.

    Used to receive and validate a mapping of provider environment variable names to their API keys.
    """
    keys: Dict[str, str]


class PrefsBody(BaseModel):
    """Represents a request body containing user or system preferences.

    Used to receive and validate a mapping of preference keys to their values.
    """
    prefs: Dict[str, Any]


class ModelsQuery(BaseModel):
    """Represents a query for available models from a provider.

    Used to specify the provider and whether to refresh the model list.
    """
    provider: str
    refresh: Optional[bool] = False


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
        from crux_providers.base.repositories.model_registry.repository import ModelRegistryRepository
    except Exception:
        # If the catalog loader or its dependencies are unavailable, skip seeding.
        return
    with suppress(Exception):  # pragma: no cover - best-effort
        repo = ModelRegistryRepository()
        model_catalog_loader.load_model_catalog(repository=repo)


def get_uow_dep() -> IUnitOfWork:
    """FastAPI dependency returning a UnitOfWork instance.

    This provides an abstraction layer so route handlers depend on the
    `IUnitOfWork` protocol instead of concrete database helper functions.
    Lifetime: a fresh UnitOfWork (and underlying connection) per request.
    It uses the centralized SQLite helper; future enhancements may introduce
    connection pooling or allow swapping the backend transparently via DI.
    """
    return get_uow()


def _build_env_to_provider_map() -> Dict[str, str]:
    """Create a mapping from environment variable names to provider names.

    This combines canonical mappings from ``ENV_MAP`` with any alias names in
    ``ENV_ALIASES`` so that incoming key payloads can reference either the
    canonical or alias variable names. The result is used by ``post_keys`` to
    normalize incoming keys to providers.

    Returns
    -------
    Dict[str, str]
        Mapping of environment variable name (e.g., ``OPENAI_API_KEY``) to
        provider identifier (e.g., ``"openai"``).
    """
    env_to_provider: Dict[str, str] = {v: k for k, v in ENV_MAP.items()}
    for prov, names in ENV_ALIASES.items():
        for n in names:
            env_to_provider.setdefault(n, prov)
    return env_to_provider


def _validate_body_as_dto(body: "ChatBody") -> ChatRequestDTO:
    """Validate inbound chat body strictly into a DTO.

    Converts the incoming ``ChatBody`` into a ``ChatRequestDTO`` performing
    strict pydantic validation so downstream code can rely on consistent
    shapes. Raises ``ValidationError`` on invalid input.

    Parameters
    ----------
    body: ChatBody
        The inbound request body.

    Returns
    -------
    ChatRequestDTO
        The validated DTO ready to be transformed into domain ``ChatRequest``.
    """
    return ChatRequestDTO(
        model=body.model,
        messages=[MessageDTO(role=m.role, content=m.content) for m in body.messages],
        max_tokens=body.max_tokens,
        temperature=body.temperature,
        response_format=body.response_format,
        json_schema=body.json_schema,
        tools=body.tools,
        extra=body.extra,
    )


def _create_adapter_or_raise(provider: str):
    """Create a provider adapter or raise a 400 HTTP error.

    Wraps ``ProviderFactory.create`` to convert an ``UnknownProviderError``
    into a ``HTTPException(400)`` suitable for controller paths.

    Parameters
    ----------
    provider: str
        Provider identifier provided by the client.

    Returns
    -------
    Any
        The instantiated adapter implementation.

    Raises
    ------
    HTTPException
        With ``status_code=400`` if the provider isn't recognized.
    """
    try:
        return ProviderFactory.create(provider)
    except UnknownProviderError as e:  # pragma: no cover - thin wrapper
        raise HTTPException(status_code=400, detail=str(e)) from e


def _build_models_response(provider: str, refresh: bool) -> Dict[str, Any]:
    """Return the models endpoint payload for a provider using the registry.

    This implementation is DB-first and uses the model registry repository
    as the single source of truth for model listings:

    - If a YAML catalog or prior refresh has populated the registry, the
      existing snapshot is returned directly.
    - If ``refresh`` is True, the repository attempts a provider-specific
      refresh before reading from SQLite.

    Parameters
    ----------
    provider: str
        Provider identifier from the request.
    refresh: bool
        Whether to trigger a refresh before loading from the registry.

    Returns
    -------
    Dict[str, Any]
        JSON-serializable response payload used by ``get_models``.
    """
    provider_norm = provider.lower().strip()
    if not provider_norm:
        raise HTTPException(status_code=400, detail="provider is required")
    try:
        from crux_providers.base.repositories.model_registry.repository import ModelRegistryRepository

        repo = ModelRegistryRepository()
        snapshot = repo.list_models(provider_norm, refresh=refresh)
    except Exception as e:  # pragma: no cover - defensive
        raise HTTPException(status_code=500, detail=str(e)) from e
    return {"ok": True, "snapshot": snapshot.to_dict()}


def _build_providers_response() -> Dict[str, Any]:
    """Return the providers endpoint payload using the model registry."""
    try:
        from crux_providers.base.repositories.model_registry.repository import ModelRegistryRepository
    except Exception as e:  # pragma: no cover - defensive
        raise HTTPException(
            status_code=500, detail=f"Model registry unavailable: {e}"
        ) from e
    repo = ModelRegistryRepository()
    try:
        providers = repo.list_providers()
    except Exception as e:  # pragma: no cover - defensive
        raise HTTPException(status_code=500, detail=str(e)) from e
    return {"ok": True, "providers": providers}


def _handle_chat(body: "ChatBody", uow: IUnitOfWork) -> Dict[str, Any]:
    """Validate, prepare, and execute a chat request, returning a response payload.

    This orchestrates the end-to-end chat flow for the ``post_chat`` route:
    - Ensures provider SDKs receive API keys via environment (using DI/UoW)
    - Resolves the provider adapter (converting unknown provider to HTTP 400)
    - Strictly validates the body via DTO conversion (HTTP 400 on failure)
    - Builds the domain request and invokes the adapter with metrics capture

    Parameters
    ----------
    body: ChatBody
        The inbound chat request body.
    uow: IUnitOfWork
        Unit-of-work dependency for key lookup and metrics persistence.

    Returns
    -------
    Dict[str, Any]
        A JSON-serializable payload with ``{"ok": True, "response": ...}`` on
        success. On failure, raises appropriate ``HTTPException``.

    Raises
    ------
    HTTPException
        - 400 for validation errors or unknown providers.
        - 500 for provider execution errors (with error details).
    """
    # Set env for SDKs if key is stored (DI-aware)
    set_env_for_provider(body.provider, uow=uow)

    # Adapter resolution (400 on unknown provider)
    adapter = _create_adapter_or_raise(body.provider)

    # Strict DTO validation before building domain request
    try:
        _ = _validate_body_as_dto(body)
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=e.errors()) from e

    req = build_chat_request(body)
    resp, err = chat_with_metrics(
        adapter, req, provider=body.provider, model=body.model, uow=uow
    )
    if err:
        raise HTTPException(status_code=500, detail=str(err)) from err
    return {"ok": True, "response": resp.to_dict()}

# Allow local dev origins; adjust as needed
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

    Returns:
        Dict[str, Any]: A dictionary with an "ok" status set to True.
    """
    return {"ok": True}


@app.post("/api/keys")
def post_keys(body: KeysBody, uow: IUnitOfWork = Depends(get_uow_dep)) -> Dict[str, Any]:
    """Store API keys for various providers from the request body.

    Accepts a mapping of environment variable names to API keys and persists them for each provider.

    Args:
        body: The request body containing the keys to store.
        uow: The unit of work for database operations.

    Returns:
        Dict[str, Any]: A dictionary indicating which keys were stored.
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

    Returns a dictionary indicating which provider keys are set without exposing the actual key values.

    Args:
        uow: The unit of work for database operations.

    Returns:
        Dict[str, Any]: A dictionary with a masked mapping of provider keys.
    """
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


@app.post("/api/prefs")
def post_prefs(body: PrefsBody, uow: IUnitOfWork = Depends(get_uow_dep)) -> Dict[str, Any]:
    """Update and store user or system preferences.

    Merges the provided preferences with existing ones and persists the updated preferences.

    Args:
        body: The request body containing preferences to update.
        uow: The unit of work for database operations.

    Returns:
        Dict[str, Any]: A dictionary with the updated preferences.
    """
    existing = uow.prefs.get_prefs().values
    existing.update(body.prefs or {})
    updated = uow.prefs.set_prefs(existing).values
    uow.commit()
    return {"ok": True, "prefs": updated}


@app.get("/api/prefs")
def get_prefs(uow: IUnitOfWork = Depends(get_uow_dep)) -> Dict[str, Any]:
    """Retrieve the current user or system preferences.

    Returns a dictionary containing all stored preferences.

    Args:
        uow: The unit of work for database operations.

    Returns:
        Dict[str, Any]: A dictionary with the current preferences.
    """
    return {"ok": True, "prefs": uow.prefs.get_prefs().values}


@app.get("/api/models")
def get_models(provider: str, refresh: bool = False) -> Dict[str, Any]:
    """Retrieve a list of available models for a given provider.

    Returns a snapshot of models if the provider supports model listing, otherwise returns an error.

    Args:
        provider: The name of the provider to query.
        refresh: Whether to refresh the model list.

    Returns:
        Dict[str, Any]: A dictionary containing the model snapshot or an error message.
    """
    return _build_models_response(provider, refresh)


@app.post("/api/chat")
def post_chat(body: ChatBody, uow: IUnitOfWork = Depends(get_uow_dep)) -> Dict[str, Any]:
    """Process a chat request and return the model's response.

    Validates the request, sets up the provider environment, and returns the chat response or an error.

    Args:
        body: The chat request body containing provider, model, and messages.
        uow: The unit of work for database operations.

    Returns:
        Dict[str, Any]: A dictionary containing the chat response or error details.
    """
    return _handle_chat(body, uow)


def get_app() -> FastAPI:
    """Return the FastAPI application instance.

    Provides access to the configured FastAPI app for use in deployment or testing.

    Returns:
        FastAPI: The FastAPI application instance.
    """
    return app
