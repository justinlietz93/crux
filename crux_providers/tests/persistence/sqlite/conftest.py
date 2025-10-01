"""Shared fixtures for SQLite persistence tests.

Provides a `conn` fixture that creates an isolated on-disk SQLite database
per-test using `create_connection` and `init_schema`, then closes it after
the test completes. This avoids cross-test interference and ResourceWarnings.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterator

import pytest

from crux_providers.persistence.sqlite.engine import (
    create_connection,
    init_schema,
)


@pytest.fixture()
def conn(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    """Provision a fresh SQLite connection with schema initialized.

    Parameters
    ----------
    tmp_path: Path
        Pytest-provided temp directory unique per test invocation.

    Yields
    ------
    sqlite3.Connection
        Open connection to a temporary database file with schema created.
    """
    db_path = tmp_path / "providers.db"
    connection = create_connection(str(db_path))
    init_schema(connection)
    try:
        yield connection
    finally:
        connection.close()
