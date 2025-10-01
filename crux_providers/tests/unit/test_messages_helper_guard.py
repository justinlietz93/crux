"""Tests for message helper guard enforcement.

Validates that `extract_system_and_user` applies the input-size guard when
enabled via environment variables and raises `ValueError` on exceed.
"""
from __future__ import annotations

import os
import importlib
from contextlib import contextmanager

import pytest

from crux_providers.base.models import Message


@contextmanager
def _env(**vals):
    old = {k: os.environ.get(k) for k in vals}
    try:
        for k, v in vals.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = str(v)
        yield
    finally:
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def test_extract_system_and_user_condenses_on_exceed():
    # Enable guard and set a small max so the concatenated user text exceeds it.
    with _env(PROVIDERS_MAX_INPUT_ENABLED="1", PROVIDERS_MAX_INPUT_CHARS="5"):
        # Reload module to ensure env is respected
        from crux_providers.base.utils import messages as messages_mod
        importlib.reload(messages_mod)

        msgs = [
            Message(role="system", content="rules"),
            Message(role="user", content="hello"),
            Message(role="user", content="world"),
        ]
        system, users = messages_mod.extract_system_and_user(msgs)
    assert system == "rules"  # nosec B101 - pytest test assertion
    assert len(users) <= 5  # nosec B101 - pytest test assertion
    assert users  # nosec B101 - condensed non-empty test assertion
