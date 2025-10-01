"""Pytest configuration for providers test suite.

Adds a session-scoped finalizer that ensures the providers' SQLite connection
is closed cleanly to reduce ResourceWarnings in CI and local runs.

This respects the architecture: we only call the public `close_db()` from the
DB service layer without reaching into internals.
"""

from __future__ import annotations

import atexit
from typing import Iterator
from contextlib import suppress

import pytest


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
