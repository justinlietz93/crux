"""Void-oriented capability enrichment helpers for model registry snapshots.

This module provides a thin, **adapter-style** layer that enriches the generic
``ModelInfo.capabilities`` mapping with a small set of **stable, provider-level
defaults** that Void Genesis IDE can consume via ``/api/models``.

Design constraints
------------------

- Does **not** change or depend on:
  - Provider SDKs
  - Runtime observations
  - The low-level capability inference helpers in
    [`get_models_base._infer_caps()`](crux/crux_providers/base/get_models_base.py:218)
    or [`_normalize_capabilities()`](crux/crux_providers/base/get_models_base.py:238).
- Only fills in **missing** keys using conservative, provider-scoped defaults.
  Existing capability flags coming from providers, registries, or observed data
  always win.
- Keeps heuristics **coarse** and intentionally avoids model-name regexes to
  stay aligned with the data-first posture in
  [`README.md`](crux/crux_providers/README.md:526) for observed capabilities.

The intent is to surface a minimal, **provider-agnostic** capability schema
for Void IDE and other thin clients, without introducing a second provider
"brain" outside Crux.

Current fields
--------------
 
The enrichment currently targets these keys inside ``ModelInfo.capabilities``:
 
- ``tool_format: str``
 
  Describes how tools are passed to a provider:
 
  - ``"openai"``    – OpenAI-style ``tools=[...]`` + function calling.
  - ``"anthropic"`` – Anthropic tools / tool_choice semantics.
  - ``"gemini"``    – Gemini tools (function calling) semantics.
  - ``"none"``      – No native tool surface; callers should fall back to
                      prompt-embedded tools (e.g., XML).
 
- ``system_message: str``
 
  Describes how system/developer instructions should be represented:
 
  - ``"developer-role"`` – Instructions supplied via a dedicated
    developer/assistant role or "instructions" field (OpenAI-style).
  - ``"system-role"``    – Instructions supplied as a regular "system" message
    within the chat history.
  - ``"separated"``      – Instructions supplied via a separate parameter
    (e.g., Anthropic ``system=...`` or Gemini ``system_instruction``).
  - ``"none"``           – No structured system channel; callers should inject
    instructions into the first user message or prompt prefix.
 
- ``fim: bool``
 
  Baseline flag for **fill-in-the-middle** support. This is conservative and
  defaults to ``False``; future work may populate this from explicit provider
  metadata or observations.
 
- ``tools_supported: bool``
 
  Coarse, provider-level flag indicating whether the provider exposes a native
  tool surface that Void can target. This is conservative and defaults to
  ``True`` for providers that offer OpenAI/Anthropic/Gemini-style tools.
  Callers may still consult finer-grained per-model capabilities or
  observations when available.
 
- ``max_tool_calls_per_turn: int | None``
 
  Soft upper bound on how many tool invocations an orchestrator should attempt
  in a single logical turn. ``None`` means "no explicit limit" (subject to the
  orchestrator's own safety caps).
 
These are intentionally minimal; they are sufficient for the IDE to:
 
- Choose between OpenAI / Anthropic / Gemini tool payloads.
- Decide how to encode system prompts per provider.
- Gate FIM-related behaviors safely.

Future fields (not yet populated here) may include:

- ``reasoning`` – structured configuration for reasoning modes.
- ``reserved_output_tokens`` – model-specific output budgeting hints.

All additions must remain backwards compatible with existing snapshots and
tests.

"""

from __future__ import annotations

from typing import Any, Dict

from ...config.defaults import (
    VOID_SYSTEM_MESSAGE_DEVELOPER_ROLE,
    VOID_SYSTEM_MESSAGE_NONE,
    VOID_SYSTEM_MESSAGE_SEPARATED,
    VOID_SYSTEM_MESSAGE_SYSTEM_ROLE,
    VOID_TOOL_FORMAT_ANTHROPIC,
    VOID_TOOL_FORMAT_GEMINI,
    VOID_TOOL_FORMAT_NONE,
    VOID_TOOL_FORMAT_OPENAI,
)

# Provider-level defaults for tool and system semantics.
#
# These values are intentionally coarse and reflect *families* of providers
# rather than individual models. They can be overridden by:
#   - explicit capabilities persisted in the registry
#   - observed capabilities merged at read time
#
# The mapping is kept small and focused; adding new providers should be done
# deliberately and accompanied by tests.
#
# NOTE: Keys are canonical provider identifiers as used by
#       [`ModelRegistryRepository.list_models()`](crux/crux_providers/base/repositories/model_registry/repository_parts/model_registry_repository.py:40)  # noqa: E501
_PROVIDER_DEFAULTS: Dict[str, Dict[str, Any]] = {
    # OpenAI-style JSON / function calling providers.
    "openai": {
        "tool_format": VOID_TOOL_FORMAT_OPENAI,
        "system_message": VOID_SYSTEM_MESSAGE_DEVELOPER_ROLE,
        "fim": False,
        # OpenAI models expose native tool surfaces; callers may still consult
        # finer-grained per-model caps when available.
        "tools_supported": True,
        # Soft orchestrator hint; the IDE will treat this as an upper bound for
        # tool invocations per logical turn, not a hard provider limit.
        "max_tool_calls_per_turn": 8,
    },
    "openrouter": {
        "tool_format": VOID_TOOL_FORMAT_OPENAI,
        "system_message": VOID_SYSTEM_MESSAGE_DEVELOPER_ROLE,
        "fim": False,
        "tools_supported": True,
        "max_tool_calls_per_turn": 8,
    },
    "deepseek": {
        "tool_format": VOID_TOOL_FORMAT_OPENAI,
        "system_message": VOID_SYSTEM_MESSAGE_DEVELOPER_ROLE,
        "fim": False,
        "tools_supported": True,
        "max_tool_calls_per_turn": 8,
    },
    "xai": {
        "tool_format": VOID_TOOL_FORMAT_OPENAI,
        "system_message": VOID_SYSTEM_MESSAGE_DEVELOPER_ROLE,
        "fim": False,
        "tools_supported": True,
        "max_tool_calls_per_turn": 8,
    },
    "groq": {
        "tool_format": VOID_TOOL_FORMAT_OPENAI,
        "system_message": VOID_SYSTEM_MESSAGE_SYSTEM_ROLE,
        "fim": False,
        "tools_supported": True,
        "max_tool_calls_per_turn": 8,
    },
    "mistral": {
        "tool_format": VOID_TOOL_FORMAT_OPENAI,
        "system_message": VOID_SYSTEM_MESSAGE_SYSTEM_ROLE,
        "fim": False,
        "tools_supported": True,
        "max_tool_calls_per_turn": 8,
    },
    "ollama": {
        # Ollama presents a local OpenAI-ish surface in many setups, but a
        # number of models may not support tools at all. Tool gating for these
        # models should still consult finer-grained caps or observations.
        "tool_format": VOID_TOOL_FORMAT_OPENAI,
        "system_message": VOID_SYSTEM_MESSAGE_SYSTEM_ROLE,
        "fim": False,
        # Coarse provider-level default: allow tools by default, with more
        # cautious decisions made at per-model or observed-capability layers.
        "tools_supported": True,
        "max_tool_calls_per_turn": 8,
    },
    # Anthropic-style tools + separate system channel.
    "anthropic": {
        "tool_format": VOID_TOOL_FORMAT_ANTHROPIC,
        "system_message": VOID_SYSTEM_MESSAGE_SEPARATED,
        "fim": False,
        "tools_supported": True,
        "max_tool_calls_per_turn": 8,
    },
    # Gemini-style tools + explicit system_instruction channel.
    "gemini": {
        "tool_format": VOID_TOOL_FORMAT_GEMINI,
        "system_message": VOID_SYSTEM_MESSAGE_SEPARATED,
        "fim": False,
        "tools_supported": True,
        "max_tool_calls_per_turn": 8,
    },
}


def apply_void_enrichment(provider: str, model_id: str, caps: Dict[str, Any] | None) -> Dict[str, Any]:
    """Return a capabilities mapping enriched with Void-oriented defaults.

    Parameters
    ----------
    provider:
        Canonical provider identifier (e.g., ``"openai"``, ``"anthropic"``).
        The value is normalized to lower case and stripped before lookup.

    model_id:
        Model identifier as stored in :class:`ModelInfo`. Currently unused for
        enrichment decisions but accepted for future per-model tuning. The
        parameter is retained to keep the contract stable.

    caps:
        Existing capabilities mapping from the registry (including any
        provider-normalized entries and runtime-observed flags). May be
        ``None`` or empty; this function never mutates the input mapping.

    Returns
    -------
    Dict[str, Any]
        A **new** capabilities dictionary containing all original entries plus
        any missing baseline keys filled from provider defaults. Existing keys
        are never overwritten.

    Behavior
    --------
    - If the provider has no entry in ``_PROVIDER_DEFAULTS``, the mapping is
      returned unchanged.
    - For providers with defaults:
      - ``tool_format`` is set when absent.
      - ``system_message`` is set when absent.
      - ``fim`` is set when absent.
      - ``tools_supported`` is set when absent.
      - ``max_tool_calls_per_turn`` is set when absent.

    Rationale
    ---------
    This helper centralizes Void-specific capability enrichment inside the
    Crux providers layer so that thin clients (e.g., Void Genesis IDE) can
    depend on a small, **documented** set of capability keys from
    ``/api/models`` instead of re-implementing provider heuristics in
    TypeScript.

    The enrichment operates strictly as a **post-processing adapter** on top of
    the existing registry+observation pipeline:

    - Base capabilities come from provider metadata and
      [`_normalize_capabilities()`](crux/crux_providers/base/get_models_base.py:238).
    - Observed runtime flags are merged in
      [`ModelRegistryRepository._apply_observed()`](crux/crux_providers/base/repositories/model_registry/repository_parts/model_registry_repository.py:64).
    - This function then fills missing defaults, producing a mapping suitable
      for Void and other orchestrators.

    """
    base: Dict[str, Any] = dict(caps or {})
    provider_key = (provider or "").lower().strip()
    profile = _PROVIDER_DEFAULTS.get(provider_key)
    if not profile:
        # No Void-specific defaults for this provider; return mapping unchanged.
        return base

    # Non-destructive merge: existing keys always win, with the exception that
    # ``tools_supported`` and ``max_tool_calls_per_turn`` treat ``None`` as
    # "missing" so that provider-level defaults can fill in sane values.
    for key, value in profile.items():
        if key in ("tools_supported", "max_tool_calls_per_turn"):
            existing = base.get(key, None)
            if existing is None:
                base[key] = value
            continue
        base.setdefault(key, value)

    return base


__all__ = ["apply_void_enrichment"]