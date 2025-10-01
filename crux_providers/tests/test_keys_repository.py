"""Unit tests for KeysRepository behavior across env/config/settings fallbacks.

Covers presence/absence and ordering.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Iterator

from crux_providers.base.repositories.keys import KeysRepository


@contextmanager
def temp_env(**kwargs) -> Iterator[None]:
    old = {k: os.environ.get(k) for k in kwargs}
    try:
        for k, v in kwargs.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        yield
    finally:
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def test_env_precedence_over_settings():
    # The value below is a harmless placeholder; allowlist for secret scanners.
    with temp_env(OPENAI_API_KEY="from_env"):  # pragma: allowlist secret - dummy test value
        repo = KeysRepository()
        res = repo.get_resolution("openai")
    assert res.api_key == "from_env" and res.source == "env"  # nosec B101 - test assertion  # pragma: allowlist secret - dummy test value


def test_missing_key_returns_none():
    repo = KeysRepository()
    with temp_env(SOME_UNKNOWN=None):
        res = repo.get_resolution("nope")
    assert res.api_key is None and res.source in {"none", "config", "settings_db"}  # nosec B101


def test_env_alias_resolution_order():
    # Use GEMINI: prefer GEMINI_API_KEY over GOOGLE_API_KEY
    # The alias value is a harmless placeholder; allowlist for secret scanners.
    with temp_env(GEMINI_API_KEY=None, GOOGLE_API_KEY="alias_val"):  # pragma: allowlist secret - dummy test value
        repo = KeysRepository()
        res = repo.get_resolution("gemini")
    # If canonical is unset but alias set, we still resolve from env
    assert res.api_key == "alias_val" and res.source == "env"  # nosec B101  # pragma: allowlist secret - dummy test value
