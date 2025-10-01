"""
Provider-agnostic domain models (DTOs) public surface.

This module re-exports the one-class-per-file implementations under
``crux_providers.base.models_parts`` to preserve backward-compatible imports while
enforcing governance on file size and cohesion.
"""

from .models_parts.content_part import ContentPart, ContentPartType
from .models_parts.message import Message, Role
from .models_parts.provider_metadata import ProviderMetadata
from .models_parts.chat_request import ChatRequest
from .models_parts.chat_response import ChatResponse
from .models_parts.model_info import ModelInfo
from .models_parts.model_registry_snapshot import ModelRegistrySnapshot

__all__ = [
    "ContentPart",
    "ContentPartType",
    "Message",
    "Role",
    "ProviderMetadata",
    "ChatRequest",
    "ChatResponse",
    "ModelInfo",
    "ModelRegistrySnapshot",
]
