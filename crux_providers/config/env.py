"""crux_providers.config.env
=========================

Centralized environment variable mapping and helpers for provider credentials.

Purpose
-------
- Provide a single source of truth for mapping provider identifiers to their
  corresponding environment variable names (canonical and aliases).
- Offer small utilities to look up and set provider API keys in a consistent,
    well-documented way across the crux_providers package.

Design Notes
------------
- Canonical mapping is defined in ``ENV_MAP``. Some providers (e.g., Gemini)
  historically support multiple env var names; list those in ``ENV_ALIASES``
  with the canonical name first to establish precedence.
- Helper functions are intentionally small and framework-agnostic to respect
  the layered architecture. No external dependencies are introduced.

Failure Modes
-------------
- Functions return ``None`` when a provider is unknown or no value is present.
- Helpers never raise on missing providers or unset variables; callers decide
  how to proceed (e.g., fallback to config or a key repository).

"""

from __future__ import annotations

import os
from typing import Dict, Iterable, Optional, Tuple

# Canonical provider → env var mapping
ENV_MAP: Dict[str, str] = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
    # Gemini has used both GEMINI_API_KEY and GOOGLE_API_KEY historically.
    # Prefer GEMINI_API_KEY as canonical but accept GOOGLE_API_KEY as alias.
    "gemini": "GEMINI_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
    "xai": "XAI_API_KEY",
}


# Provider → ordered tuple of acceptable env var names (canonical first)
ENV_ALIASES: Dict[str, Tuple[str, ...]] = {
    "gemini": ("GEMINI_API_KEY", "GOOGLE_API_KEY"),
}


def is_placeholder(val: Optional[str]) -> bool:
    """Return True if the provided string looks like a placeholder/test value.

    Heuristics: contains 'placeholder', 'changeme', 'example', or starts with
    'test_'. The check is case-insensitive and resilient to surrounding spaces.

    Parameters
    ----------
    val: Optional[str]
        The value to evaluate.

    Returns
    -------
    bool
        True when the value is considered a placeholder or test token.
    """
    if val is None:
        return False
    v = str(val).strip().lower()
    return (
        "placeholder" in v
        or "changeme" in v
        or "example" in v
        or v.startswith("test_")
    )


def get_env_var_name(provider: str) -> Optional[str]:
    """Return the canonical environment variable name for a provider.

    Parameters
    ----------
    provider: str
        Provider identifier (case-insensitive).

    Returns
    -------
    Optional[str]
        Canonical env var name or None if the provider is unknown.
    """
    return ENV_MAP.get(provider.lower()) if provider else None


def get_env_var_candidates(provider: str) -> Iterable[str]:
    """Yield acceptable environment variable names for a provider.

    The canonical name is yielded first, followed by any aliases.

    Parameters
    ----------
    provider: str
        Provider identifier (case-insensitive).

    Yields
    ------
    str
        Environment variable names in priority order.
    """
    p = (provider or "").lower()
    canonical = ENV_MAP.get(p)
    if canonical:
        yield canonical
    for alias in ENV_ALIASES.get(p, ()):  # pragma: no branch - small tuples
        if alias != canonical:
            yield alias


def resolve_provider_key(provider: str) -> Tuple[Optional[str], Optional[str]]:
    """Resolve an API key for a provider from the process environment.

    Iterates through the candidate environment variable names in priority
    order and returns the first non-empty value.

    Parameters
    ----------
    provider: str
        Provider identifier (case-insensitive).

    Returns
    -------
    Tuple[Optional[str], Optional[str]]
        (value, env_var_used) where value is the first non-empty credential
        found and env_var_used is the corresponding environment variable name.
        (None, None) when nothing is set.
    """
    for name in get_env_var_candidates(provider):
        if val := os.environ.get(name):
            return val, name
    return None, None


def set_canonical_env_if_missing(provider: str, value: Optional[str]) -> None:
    """Ensure the canonical env var for a provider is set to a real value.

    If the canonical variable is unset or currently holds a placeholder value,
    and a non-empty ``value`` is provided, set it. This is useful when reading
    compatible aliases or repo-configured values and promoting them to the
    canonical location for consistency across the codebase.

    Parameters
    ----------
    provider: str
        Provider identifier (case-insensitive).
    value: Optional[str]
        The API key/token to write when appropriate.
    """
    if not value:
        return
    canonical = get_env_var_name(provider)
    if not canonical:
        return
    current = os.environ.get(canonical)
    if not current or is_placeholder(current):
        os.environ[canonical] = value


__all__ = [
    "ENV_MAP",
    "ENV_ALIASES",
    "is_placeholder",
    "get_env_var_name",
    "get_env_var_candidates",
    "resolve_provider_key",
    "set_canonical_env_if_missing",
]
