"""
Providers Base Package

Exports provider-agnostic contracts, DTOs, repositories, and the provider factory
for use within the providers layer (and, later, by orchestrators).

Conforms to the hybrid clean architecture scaffolding:
- Interfaces: normalized provider boundaries
- Models (DTOs): serialization-friendly request/response objects
- Repositories: model registry and key resolution
- Factory: lazy creation of provider adapters by canonical name
"""

from .factory import ProviderFactory, UnknownProviderError
from .interfaces import (
    HasDefaultModel,
    LLMProvider,
    ModelListingProvider,
    SupportsJSONOutput,
    SupportsResponsesAPI,
)
from .models import (
    ChatRequest,
    ChatResponse,
    ContentPart,
    ContentPartType,
    Message,
    ModelInfo,
    ModelRegistrySnapshot,
    ProviderMetadata,
    Role,
)
from .repositories.keys import KeyResolution, KeysRepository
from .repositories.model_registry.repository import ModelRegistryRepository
from .timeouts import TimeoutConfig, get_timeout_config, operation_timeout
from .cancellation import CancellationToken, CancelledError
from .streaming import (
    StreamMetrics,
    finalize_stream,
    StreamController,
    BaseStreamingAdapter,
)

__all__ = [
    # Models
    "Role",
    "ContentPartType",
    "ContentPart",
    "Message",
    "ProviderMetadata",
    "ChatRequest",
    "ChatResponse",
    "ModelInfo",
    "ModelRegistrySnapshot",
    # Interfaces
    "LLMProvider",
    "SupportsJSONOutput",
    "SupportsResponsesAPI",
    "ModelListingProvider",
    "HasDefaultModel",
    # Repositories
    "ModelRegistryRepository",
    "KeysRepository",
    "KeyResolution",
    # Factory
    "ProviderFactory",
    "UnknownProviderError",
    # Timeouts & Cancellation
    "TimeoutConfig",
    "get_timeout_config",
    "operation_timeout",
    "CancellationToken",
    "CancelledError",
    # Streaming
    "BaseStreamingAdapter",
    "StreamMetrics",
    "finalize_stream",
    "StreamController",
]
