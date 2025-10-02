"""Pytest configuration for providers test suite.

Adds a session-scoped finalizer that ensures the providers' SQLite connection
is closed cleanly to reduce ResourceWarnings in CI and local runs.

This respects the architecture: we only call the public `close_db()` from the
DB service layer without reaching into internals.
"""

from __future__ import annotations

import atexit
from typing import Iterator, TYPE_CHECKING
from contextlib import suppress

import pytest

if TYPE_CHECKING:
    from crux_providers.mock import MockProvider


@pytest.fixture()
def enable_mock_providers(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Enable mock providers via environment toggle for the duration of a test."""

    monkeypatch.setenv("CRUX_USE_MOCKS", "1")
    yield
    monkeypatch.delenv("CRUX_USE_MOCKS", raising=False)


@pytest.fixture()
def mock_provider(enable_mock_providers) -> Iterator["MockProvider"]:
    """Yield a ``MockProvider`` instance configured for the default fixture."""

    from crux_providers.mock import MockProvider

    provider = MockProvider()
    yield provider


@pytest.fixture(scope="session", autouse=True)
def close_db_after_session() -> Iterator[None]:
    """Ensure providers DB connections are closed after the test session.

    - Uses a lazy import to avoid side effects at import time.
    - Registers an atexit hook as a secondary safety net in case of hard exits.
    """

    # Lazy import to avoid import-time side effects
    from crux_providers.service import db as providers_db

    def _cleanup() -> None:
        """Call the public close function; safe to call multiple times.

        Using ``contextlib.suppress`` avoids try/except/pass anti-patterns while
        keeping teardown resilient. ``close_db`` is idempotent and safe to call
        repeatedly.
        """
        with suppress(Exception):  # defensive: teardown must not fail tests
            providers_db.close_db()

    # Primary session teardown
    yield
    _cleanup()

    # Secondary guard for abnormal exits
    atexit.register(_cleanup)
