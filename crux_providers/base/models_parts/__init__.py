"""Models parts package public surface.

Re-exports individual DTOs so callers can import from
`crux_providers.base.models_parts` if needed, while `crux_providers.base.models` remains
the primary stable import path.
"""

from .content_part import ContentPart, ContentPartType
from .message import Message, Role
from .provider_metadata import ProviderMetadata
from .chat_request import ChatRequest
from .chat_response import ChatResponse
from .model_info import ModelInfo
from .model_registry_snapshot import ModelRegistrySnapshot

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
