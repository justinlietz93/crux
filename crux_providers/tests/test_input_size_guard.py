"""Unit tests for input size guard utility.

Covers:
- Default-on guard with zero max (no-op).
- Enabled with sufficient limit (no exception).
- Enabled with exceeding input (raises ``ValueError``).
- Condensation helper reduces inputs to a configured maximum.
"""

from __future__ import annotations

import os
from contextlib import contextmanager

import pytest

from crux_providers.utils.input_size_guard import (
    enforce_max_input,
    is_guard_enabled,
    get_max_input_chars,
    condense_text_to_limit,
)


@contextmanager
def _env(**vals):
    """Temporarily set environment variables for the duration of a context.

    Restores original values on exit.
    """
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


def test_default_on_no_limit_noop():
    """Guard defaults to enabled but with zero max → enforcement is a no-op."""
    with _env(PROVIDERS_MAX_INPUT_ENABLED=None, PROVIDERS_MAX_INPUT_CHARS=None):
        assert is_guard_enabled() is True  # nosec B101 - pytest assertions acceptable in tests
        assert get_max_input_chars() == 0  # nosec B101 - pytest assertions acceptable in tests
        # Should not raise since eff_max <= 0
        enforce_max_input("x" * 1000)


def test_enabled_and_under_limit_ok():
    """Guard enabled: inputs at or under limit should pass."""
    with _env(PROVIDERS_MAX_INPUT_ENABLED="true", PROVIDERS_MAX_INPUT_CHARS="10"):
        assert is_guard_enabled() is True  # nosec B101 - pytest assertions acceptable in tests
        assert get_max_input_chars() == 10  # nosec B101 - pytest assertions acceptable in tests
        enforce_max_input("x" * 10)  # does not raise


def test_enabled_and_exceeds_raises():
    """Guard enabled: inputs over the limit should raise ValueError."""
    with _env(PROVIDERS_MAX_INPUT_ENABLED="1", PROVIDERS_MAX_INPUT_CHARS="5"):
        with pytest.raises(ValueError):
            enforce_max_input("x" * 6)


def test_condense_text_to_limit_truncates_and_bounds():
    """Condense helper must bound output length and preserve some context."""
    long = "ABCDEFGHIJKLMNOPQRSTUVWXYZ" * 100
    out = condense_text_to_limit(long, 50, chunk_chars=40)
    assert len(out) <= 50  # nosec B101 - test assertion
    # Expect an ellipsis in typical case
    assert "…" in out  # nosec B101 - test assertion


def test_condense_text_to_limit_multi_iteration():
    """Multiple condensation rounds should converge within the cap."""
    text = "0123456789" * 1000
    out = condense_text_to_limit(text, 80, chunk_chars=64, max_iterations=5)
    assert len(out) <= 80  # nosec B101 - test assertion
