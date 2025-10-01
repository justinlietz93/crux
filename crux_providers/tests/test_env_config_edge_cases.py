"""Edge-case tests for `crux_providers.config.env` helpers.

Covers placeholder detection, alias resolution order, empty-string handling,
and canonical env promotion when only an alias is present.
"""

from __future__ import annotations

import os
from typing import Iterable

import pytest

from crux_providers.config.env import (
    ENV_ALIASES,
    ENV_MAP,
    get_env_var_candidates,
    get_env_var_name,
    is_placeholder,
    resolve_provider_key,
    set_canonical_env_if_missing,
)


def _clear_vars(monkeypatch: pytest.MonkeyPatch, names: Iterable[str]) -> None:
    """Helper to clear provided environment variable names."""
    for n in names:
        if n in os.environ:
            monkeypatch.delenv(n, raising=False)


def _expect(condition: bool, message: str) -> None:
    """Fail the test with a clear message when condition is False.

    Avoids Python 'assert' to satisfy Bandit B101 policy in tests.
    """
    if not condition:
        pytest.fail(message)


def test_get_env_var_name_known_and_unknown() -> None:
    """Known providers map to canonical names; unknown returns None."""
    _expect(get_env_var_name("openai") == ENV_MAP["openai"], "openai canonical mismatch")
    _expect(get_env_var_name("OpenAI") == ENV_MAP["openai"], "OpenAI case-insensitive mismatch")
    _expect(get_env_var_name("unknown_provider") is None, "unknown provider should return None")


def test_get_env_var_candidates_order() -> None:
    """Candidates yield canonical first, then aliases preserving order."""
    cands = list(get_env_var_candidates("gemini"))
    _expect(cands[0] == ENV_MAP["gemini"], "canonical should be first candidate")
    _expect(tuple(cands[1:]) == tuple(n for n in ENV_ALIASES["gemini"] if n != cands[0]), "aliases order mismatch")


@pytest.mark.parametrize(
    "value,expected",
    [
        (None, False),
        ("", False),
        ("   ", False),
        ("test_abc", True),
        ("PLACEHOLDER", True),
        ("xxchangemexx", True),
        ("some-example-key", True),
        ("real_key_value", False),
    ],
)
def test_is_placeholder_variants(value: str | None, expected: bool) -> None:
    """Placeholder heuristic handles common variants and whitespace/case."""
    _expect(is_placeholder(value) is expected, f"placeholder detection mismatch for {value!r}")


def test_resolve_provider_key_prefers_canonical(monkeypatch: pytest.MonkeyPatch) -> None:
    """When both canonical and alias are set, canonical should win."""
    canonical = ENV_MAP["gemini"]
    alias = next(n for n in ENV_ALIASES["gemini"] if n != canonical)
    _clear_vars(monkeypatch, [canonical, alias])

    monkeypatch.setenv(canonical, "canon_val")
    monkeypatch.setenv(alias, "alias_val")
    val, used = resolve_provider_key("gemini")
    _expect(val == "canon_val" and used == canonical, "should prefer canonical over alias")


def test_resolve_provider_key_uses_alias_when_canonical_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    """If only alias is set, it should be returned along with the alias name."""
    canonical = ENV_MAP["gemini"]
    alias = next(n for n in ENV_ALIASES["gemini"] if n != canonical)
    _clear_vars(monkeypatch, [canonical, alias])

    monkeypatch.setenv(alias, "alias_val")
    val, used = resolve_provider_key("gemini")
    _expect(val == "alias_val" and used == alias, "should return alias when canonical missing")


def test_resolve_provider_key_ignores_empty_strings(monkeypatch: pytest.MonkeyPatch) -> None:
    """Empty strings should be treated as missing and ignored."""
    canonical = ENV_MAP["openai"]
    _clear_vars(monkeypatch, [canonical])
    monkeypatch.setenv(canonical, "")
    val, used = resolve_provider_key("openai")
    _expect(val is None and used is None, "empty strings must be ignored")


def test_set_canonical_env_if_missing_promotes_alias(monkeypatch: pytest.MonkeyPatch) -> None:
    """A real alias value should be promoted to canonical if canonical is missing/placeholder."""
    canonical = ENV_MAP["gemini"]
    alias = next(n for n in ENV_ALIASES["gemini"] if n != canonical)
    _clear_vars(monkeypatch, [canonical, alias])

    # Canonical missing, alias has a real value → should promote
    monkeypatch.setenv(alias, "real_value")
    set_canonical_env_if_missing("gemini", os.environ[alias])
    _expect(os.environ.get(canonical) == "real_value", "alias should promote to canonical when missing")

    # Canonical set to placeholder, new real value should overwrite
    monkeypatch.setenv(canonical, "placeholder_value")
    monkeypatch.setenv(alias, "real_value_2")
    set_canonical_env_if_missing("gemini", os.environ[alias])
    _expect(os.environ.get(canonical) == "real_value_2", "placeholder canonical should be overwritten by real value")

    # No promotion when provided value is empty/None
    set_canonical_env_if_missing("gemini", "")
    _expect(os.environ.get(canonical) == "real_value_2", "empty values must not overwrite canonical")
