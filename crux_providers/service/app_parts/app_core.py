from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import HTTPException
from pydantic import BaseModel, ValidationError

from crux_providers.base.dto import ChatRequestDTO, MessageDTO
from crux_providers.base.factory import ProviderFactory, UnknownProviderError
from crux_providers.config.env import ENV_ALIASES, ENV_MAP
from crux_providers.persistence.interfaces.repos import IUnitOfWork
from crux_providers.persistence.sqlite import get_uow
from crux_providers.service import db as svcdb
from crux_providers.service.helpers import (
    build_chat_request,
    chat_with_metrics,
    set_env_for_provider,
)


class ChatMessageDTO(BaseModel):
    """Represents a single chat message with a role and content.

    Used to encapsulate the role (e.g., user, assistant) and the message
    content for chat interactions.
    """

    role: str
    content: Any


class ChatBody(BaseModel):
    """Represents the body of a chat request.

    Encapsulates all parameters required to initiate a chat, including
    optional settings and extra data.
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

    Used to receive and validate a mapping of provider environment variable
    names to their API keys.
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


def get_uow_dep() -> IUnitOfWork:
    """FastAPI dependency returning a UnitOfWork instance."""
    return get_uow()


def _build_env_to_provider_map() -> Dict[str, str]:
    """Create a mapping from environment variable names to provider names.

    This combines canonical mappings from ``ENV_MAP`` with any alias names in
    ``ENV_ALIASES`` so that incoming key payloads can reference either the
    canonical or alias variable names.
    """
    env_to_provider: Dict[str, str] = {v: k for k, v in ENV_MAP.items()}
    for prov, names in ENV_ALIASES.items():
        for n in names:
            env_to_provider.setdefault(n, prov)
    return env_to_provider


def _validate_body_as_dto(body: ChatBody) -> ChatRequestDTO:
    """Validate inbound chat body strictly into a DTO."""
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
    """Create a provider adapter or raise a 400 HTTP error."""
    try:
        return ProviderFactory.create(provider)
    except UnknownProviderError as e:  # pragma: no cover - thin wrapper
        raise HTTPException(status_code=400, detail=str(e)) from e


def _build_models_response(provider: str, refresh: bool) -> Dict[str, Any]:
    """Return the models endpoint payload for a provider using the registry."""
    provider_norm = provider.lower().strip()
    if not provider_norm:
        raise HTTPException(status_code=400, detail="provider is required")
    try:
        from crux_providers.base.repositories.model_registry.repository import (
            ModelRegistryRepository,
        )

        repo = ModelRegistryRepository()
        snapshot = repo.list_models(provider_norm, refresh=refresh)
    except Exception as e:  # pragma: no cover - defensive
        raise HTTPException(status_code=500, detail=str(e)) from e
    return {"ok": True, "snapshot": snapshot.to_dict()}


def _build_providers_response() -> Dict[str, Any]:
    """Return the providers endpoint payload using the model registry.

    The HTTP surface intentionally exposes a minimal list of provider ids
    (strings) for thin clients such as Void Genesis IDE. Additional metadata
    remains available via the repository and persistence layers.
    """
    try:
        svcdb.ensure_initialized()
        raw_providers = svcdb.list_model_providers()
    except Exception as e:  # pragma: no cover - defensive
        raise HTTPException(status_code=500, detail=str(e)) from e

    providers: List[str] = []
    for item in raw_providers or []:
        if isinstance(item, str) and item:
            providers.append(item)
        elif isinstance(item, dict):
            pid = item.get("provider") or item.get("id")
            if isinstance(pid, str) and pid:
                providers.append(pid)

    return {"ok": True, "providers": providers}


def _handle_chat(body: ChatBody, uow: IUnitOfWork) -> Dict[str, Any]:
    """Validate, prepare, and execute a chat request, returning a response payload."""
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


__all__ = [
    "ChatMessageDTO",
    "ChatBody",
    "KeysBody",
    "PrefsBody",
    "ModelsQuery",
    "get_uow_dep",
    "_build_env_to_provider_map",
    "_build_models_response",
    "_build_providers_response",
    "_handle_chat",
]