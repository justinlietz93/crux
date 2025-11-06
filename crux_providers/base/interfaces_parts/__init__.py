"""Interfaces (Protocols) split into single-class modules.

This package provides one Protocol per file to satisfy governance rules
while allowing ``crux_providers.base.interfaces`` to re-export a stable API.
"""

from .llm_provider import LLMProvider
from .supports_streaming import SupportsStreaming
from .supports_json_output import SupportsJSONOutput
from .supports_responses_api import SupportsResponsesAPI
from .supports_tool_use import SupportsToolUse
from .model_listing_provider import ModelListingProvider
from .has_default_model import HasDefaultModel
from .context_manager import IContextManager
from .agent_runtime import IAgentRuntime
from .has_data import HasData
from .has_name_and_limits import HasName, HasTokenLimits, HasNameAndLimits
from .has_id import HasId
from .response_misc import HasCode, HasValue, HasText

__all__ = [
    "LLMProvider",
    "SupportsStreaming",
    "SupportsJSONOutput",
    "SupportsResponsesAPI",
    "SupportsToolUse",
    "ModelListingProvider",
    "HasDefaultModel",
    "IContextManager",
    "IAgentRuntime",
    "HasData",
    "HasName",
    "HasTokenLimits",
    "HasNameAndLimits",
    "HasId",
    "HasCode",
    "HasValue",
    "HasText",
]
