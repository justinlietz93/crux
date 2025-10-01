"""Token usage extraction helpers (Issue #59).

This module centralizes *best-effort* extraction of token accounting
information from raw provider SDK response objects. It converts
provider-specific usage attribute names into a canonical mapping used
throughout the providers layer and structured logging:

    {"prompt": <int|None>, "completion": <int|None>, "total": <int|None>}

Design Principles
-----------------
1. Non-Intrusive: If a response object does not expose usage attributes the
   helper returns the placeholder mapping with all values ``None`` rather than
   raising. Providers can then decide whether to replace an existing
   placeholder only when at least one concrete integer is present.
2. Defensive Coercion: All numeric values are coerced via ``int`` inside a
   try/except block. Invalid or negative values downgrade to ``None`` and are
   not allowed to propagate exceptions into the provider hot path.
3. Derived Total: If ``total`` is missing but both ``prompt`` and
   ``completion`` are present the function derives the total as their sum. If
   only one component is present the total remains ``None`` to avoid implying
   completeness where data is partial.
4. Validation Integration: When available we import ``validate_token_usage``
   from ``streaming_metrics`` to perform structural / logical validation in a
   best-effort manner. Import errors (e.g., during partial test harness
   execution) are swallowed intentionally.

Supported Providers
-------------------
OpenAI:
    Expects attributes similar to the newer SDK response objects:
        ``response.usage.prompt_tokens``
        ``response.usage.completion_tokens`` (or ``response.usage.completion_tokens"``)
        ``response.usage.total_tokens``
Anthropic:
    Anticipates future SDK fields:
        ``response.usage.input_tokens`` (prompt side)
        ``response.usage.output_tokens`` (completion side)
        ``response.usage.total_tokens`` (optional)

If these attributes are absent the helpers simply return the None placeholder.

Failure Modes
-------------
* Attribute absence → returns placeholder mapping
* Non-integer / negative values → coerced to ``None``
* Unexpected exceptions → swallowed (logged optionally by caller) returning
  placeholder mapping

Public Functions
----------------
``extract_openai_token_usage(raw)``
    Attempt to map OpenAI style usage fields.
``extract_anthropic_token_usage(raw)``
    Attempt to map Anthropic style usage fields.

Both functions always succeed (never raise) and return the canonical mapping.
They are intentionally free of logging to keep them side-effect free; providers
may log diagnostics if the returned mapping still contains only ``None``.
"""

from __future__ import annotations

from typing import Any, Dict, Optional, cast, Mapping

# Structural protocols to avoid brittle getattr chains
from ..stubs import HasOpenAIUsage, HasAnthropicUsage

# Best-effort import; provider modules tolerate absence during isolated tests
try:  # pragma: no cover - thin defensive import
    # Import from the public streaming namespace (re-exported helper)
    from ..streaming import validate_token_usage  # type: ignore
except Exception:  # pragma: no cover
    def validate_token_usage(_usage: Dict[str, Optional[int]]):  # type: ignore
        return True

CanonicalUsage = Dict[str, Optional[int]]

PLACEHOLDER_USAGE: CanonicalUsage = {"prompt": None, "completion": None, "total": None}


def _coerce_int(value: Any) -> Optional[int]:
    """Coerce arbitrary value to a non-negative ``int`` or ``None``.

    Args:
        value: Arbitrary candidate value (may be ``None`` or numeric string).

    Returns:
        int | None: Integer if coercion succeeds and value is >= 0; otherwise ``None``.
    """
    if value is None:
        return None
    try:
        iv = int(value)  # type: ignore[arg-type]
        return iv if iv >= 0 else None
    except Exception:  # pragma: no cover - coercion failure path
        return None


def _finalize_usage(prompt: Optional[int], completion: Optional[int], total: Optional[int]) -> CanonicalUsage:
    """Finalize canonical usage dict deriving missing ``total`` when feasible.

    If ``total`` is missing but both component counts are present it computes
    their sum. Structural validation is applied (best-effort). Returns a new
    mapping (does not mutate inputs).

    Args:
        prompt: Prompt token count or ``None``.
        completion: Completion token count or ``None``.
        total: Total token count or ``None``.

    Returns:
        CanonicalUsage: Mapping with keys ``prompt``, ``completion``, ``total``.
    """
    if total is None and prompt is not None and completion is not None:
        total = prompt + completion
    usage: CanonicalUsage = {"prompt": prompt, "completion": completion, "total": total}
    try:  # Validation should never throw upstream
        validate_token_usage(usage)  # type: ignore[arg-type]
    except Exception:  # pragma: no cover
        # If validation fails we degrade to placeholder to avoid partial corruption
        return PLACEHOLDER_USAGE.copy()
    return usage


def extract_openai_token_usage(raw_response: Any) -> CanonicalUsage:
    """Extract OpenAI token usage metrics from a raw SDK response object.

    The function supports both completion-style and responses API objects so
    long as they expose a ``usage`` attribute with expected fields. Missing
    fields simply yield ``None`` values.

    Args:
        raw_response: Provider SDK response object (may be any type).

    Returns:
        CanonicalUsage: Usage mapping with ``prompt``, ``completion`` and ``total`` keys.
    """
    if raw_response is None:
        return PLACEHOLDER_USAGE.copy()

    usage_obj: Any = None
    # Accept both mapping-style responses (dicts) and SDK objects with attributes
    if isinstance(raw_response, Mapping):
        usage_obj = raw_response.get("usage")
    else:
        try:
            obj = cast(HasOpenAIUsage, raw_response)
            usage_obj = obj.usage
        except Exception:  # pragma: no cover - structural mismatch
            return PLACEHOLDER_USAGE.copy()

    # Defensive access for both mapping and attribute objects
    if isinstance(usage_obj, Mapping):
        prompt = _coerce_int(usage_obj.get("prompt_tokens"))
        completion = _coerce_int(usage_obj.get("completion_tokens"))
        total = _coerce_int(usage_obj.get("total_tokens"))
    else:
        prompt = _coerce_int(getattr(usage_obj, "prompt_tokens", None))
        completion = _coerce_int(getattr(usage_obj, "completion_tokens", None))
        total = _coerce_int(getattr(usage_obj, "total_tokens", None))
    return _finalize_usage(prompt, completion, total)


def extract_anthropic_token_usage(raw_response: Any) -> CanonicalUsage:
    """Extract Anthropic token usage metrics from raw response if available.

    Anticipates future (or newer) SDKs that attach a ``usage`` object with
    input/output token counts. Older SDKs that lack these attributes simply
    produce the placeholder mapping.

    Args:
        raw_response: Provider SDK response object.

    Returns:
        CanonicalUsage: Usage mapping with keys ``prompt``, ``completion`` and ``total``.
    """
    if raw_response is None:
        return PLACEHOLDER_USAGE.copy()

    usage_obj: Any = None
    if isinstance(raw_response, Mapping):
        usage_obj = raw_response.get("usage")
    else:
        try:
            obj = cast(HasAnthropicUsage, raw_response)
            usage_obj = obj.usage
        except Exception:  # pragma: no cover - structural mismatch
            return PLACEHOLDER_USAGE.copy()

    if isinstance(usage_obj, Mapping):
        prompt = _coerce_int(usage_obj.get("input_tokens"))
        completion = _coerce_int(usage_obj.get("output_tokens"))
        total = _coerce_int(usage_obj.get("total_tokens"))
    else:
        prompt = _coerce_int(getattr(usage_obj, "input_tokens", None))
        completion = _coerce_int(getattr(usage_obj, "output_tokens", None))
        total = _coerce_int(getattr(usage_obj, "total_tokens", None))
    return _finalize_usage(prompt, completion, total)


__all__ = [
    "extract_openai_token_usage",
    "extract_anthropic_token_usage",
    "PLACEHOLDER_USAGE",
]
