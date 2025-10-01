from __future__ import annotations

import os


from crux_providers.config.env import (
    ENV_MAP,
    ENV_ALIASES,
    is_placeholder,
    get_env_var_name,
    resolve_provider_key,
    set_canonical_env_if_missing,
)


def _with_env(**pairs):
    # simple context manager replacement for brevity in tests
    prev = {}
    for k, v in pairs.items():
        prev[k] = os.environ.get(k)
        os.environ[k] = v
    try:
        yield
    finally:
        for k, v in prev.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def test_env_map_contains_expected_keys():
    for p in ["openai", "anthropic", "deepseek", "gemini", "openrouter", "xai"]:
        assert p in ENV_MAP


def test_get_env_var_name_and_aliases():
    assert get_env_var_name("openai") == "OPENAI_API_KEY"
    assert get_env_var_name("gemini") == "GEMINI_API_KEY"
    assert "gemini" in ENV_ALIASES
    assert ENV_ALIASES["gemini"][0] == "GEMINI_API_KEY"


def test_is_placeholder_heuristics():
    assert is_placeholder("placeholder-value")
    assert is_placeholder("ChangeMe123")
    assert is_placeholder("example-key")
    assert is_placeholder("test_token")
    assert not is_placeholder("real-value")


def test_resolve_provider_key_prefers_canonical(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "canon")
    monkeypatch.setenv("GOOGLE_API_KEY", "alias")
    val, used = resolve_provider_key("gemini")
    assert val == "canon"
    assert used == "GEMINI_API_KEY"


def test_set_canonical_env_if_missing(monkeypatch):
    # canonical not set, alias present
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("GOOGLE_API_KEY", "alias-value")
    set_canonical_env_if_missing("gemini", os.environ.get("GOOGLE_API_KEY"))
    assert os.environ.get("GEMINI_API_KEY") == "alias-value"
