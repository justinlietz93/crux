"""Capability enumeration & detection utilities.

Adapters do not need to manually enumerate capabilities; we infer them by
checking for marker mixin interfaces (abstract base / Protocol descendants)
and optional predicate methods (e.g. ``supports_streaming()``). This keeps
adoption incremental and avoids hard failures when a capability isn't yet
implemented.
"""

from __future__ import annotations

from typing import Any, Dict, FrozenSet, Optional

from ..interfaces import (
    HasDefaultModel,
    IAgentRuntime,
    IContextManager,
    LLMProvider,
    ModelListingProvider,
    SupportsJSONOutput,
    SupportsResponsesAPI,
    SupportsStreaming,
    SupportsToolUse,
)

# String constants (avoid Enum overhead for simple set operations)
CAP_STREAMING = "streaming"
CAP_JSON = "json_output"
CAP_RESPONSES_API = "responses_api"
CAP_MODEL_LISTING = "model_listing"
CAP_DEFAULT_MODEL = "default_model"
CAP_TOOL_USE = "tool_use"
CAP_CONTEXT_MANAGEMENT = "context_management"
CAP_AGENT_RUNTIME = "agent_runtime"


def detect_capabilities(provider: LLMProvider) -> FrozenSet[str]:  # type: ignore[type-arg]
    """Detect and return the set of capabilities supported by a provider.

    Inspects the provider for supported interfaces and predicate methods to infer available capabilities.

    Args:
        provider: The provider instance to inspect.

    Returns:
        FrozenSet[str]: A set of capability names supported by the provider.
    """
    caps: set[str] = set()
    if (
        isinstance(provider, SupportsStreaming)
        and provider.supports_streaming()
    ):
        caps.add(CAP_STREAMING)
    if (
        isinstance(provider, SupportsJSONOutput)
        and provider.supports_json_output()
    ):
        caps.add(CAP_JSON)
    if isinstance(provider, SupportsResponsesAPI):
        caps.add(CAP_RESPONSES_API)
    if isinstance(provider, ModelListingProvider):
        caps.add(CAP_MODEL_LISTING)
    if (
        isinstance(provider, HasDefaultModel)
        and provider.default_model() is not None
    ):
        caps.add(CAP_DEFAULT_MODEL)
    if (
        isinstance(provider, SupportsToolUse)
        and provider.supports_tool_use()
    ):
        caps.add(CAP_TOOL_USE)
    if isinstance(provider, IContextManager):
        caps.add(CAP_CONTEXT_MANAGEMENT)
    if isinstance(provider, IAgentRuntime):
        caps.add(CAP_AGENT_RUNTIME)
    return frozenset(caps)


def normalize_modalities(modalities: Any) -> Dict[str, bool]:
    """Derive capability flags strictly from a ``modalities`` list.

    Behavior:
    - Lower-cases each entry and sets the modality name to True.
    - Normalizes ``image`` into ``vision`` by also setting ``vision=True``.
    - Ignores non-iterable inputs and returns an empty mapping in that case.

    This function intentionally avoids any model-name heuristics and should be
    preferred anywhere we need a data-first capability baseline.

    Parameters:
        modalities: A list/tuple of modality identifiers or any other value.

    Returns:
        Dict[str, bool]: Mapping of capability names derived from modalities.
    """
    caps: Dict[str, bool] = {}
    if isinstance(modalities, (list, tuple)):
        for m in modalities:
            mstr = str(m).lower()
            caps[mstr] = True
            if mstr in {"image", "vision"}:
                caps["vision"] = True
    return caps


def merge_capabilities(old: Optional[Dict[str, Any]], new: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Merge two capability dictionaries, preserving truthy values.

    Non-destructive merge policy:
    - All keys from ``old`` are retained.
    - Keys from ``new`` are added when missing.
    - Where a key exists in both, the merged value is the boolean OR of their
      truthiness (prefers True if either is truthy).

    Parameters:
        old: Existing capability mapping (e.g., cached snapshot).
        new: Newly derived capability mapping (e.g., from current modalities).

    Returns:
        Dict[str, Any]: Merged capabilities.
    """
    out: Dict[str, Any] = dict(old or {})
    for k, v in (new or {}).items():
        out[k] = v if k not in out else bool(out[k]) or bool(v)
    return out


def should_attempt(feature: str, caps: Optional[Dict[str, Any]]) -> bool:
    """Return True if a feature should be attempted under permissive policy.

    Decision rule:
    - If capabilities are unknown (``caps`` is None), return True.
    - If the feature flag is absent, return True (unknown is permissive).
    - If the feature flag is explicitly False, return False.
    - Any truthy value returns True.

    Parameters:
        feature: Capability name to check (e.g., "vision").
        caps: Known capabilities mapping for the model, if any.

    Returns:
        bool: True to proceed, False to gate.
    """
    if caps is None:
        return True
    return True if feature not in caps else bool(caps.get(feature))


__all__ = [
    "CAP_STREAMING",
    "CAP_JSON",
    "CAP_RESPONSES_API",
    "CAP_MODEL_LISTING",
    "CAP_DEFAULT_MODEL",
    "CAP_TOOL_USE",
    "CAP_CONTEXT_MANAGEMENT",
    "CAP_AGENT_RUNTIME",
    "detect_capabilities",
    "normalize_modalities",
    "merge_capabilities",
    "should_attempt",
]
