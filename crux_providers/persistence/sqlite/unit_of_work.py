"""SQLite-backed Unit of Work implementation aggregating repositories.

This adapter composes repository implementations and manages transaction
boundaries. On context exit it commits when no exception occurred; otherwise it
rolls back. No implicit commits happen inside repositories.
"""

from __future__ import annotations

import sqlite3

from ..interfaces.repos import IUnitOfWork
from .chatlog_repo import ChatLogRepoSqlite
from .keystore_repo import KeyStoreRepoSqlite
from .metrics_repo import MetricsRepoSqlite
from .prefs_repo import PrefsRepoSqlite


class UnitOfWorkSqlite(IUnitOfWork):
    """Unit of Work implementation for SQLite.

    Aggregates concrete repository adapters and manages transaction boundaries.
    On context exit, commits when no exception was raised; otherwise rolls back.
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self.keys = KeyStoreRepoSqlite(conn)
        self.prefs = PrefsRepoSqlite(conn)
        self.metrics = MetricsRepoSqlite(conn)
        self.chats = ChatLogRepoSqlite(conn)
        self._active = False

    def __enter__(self) -> "UnitOfWorkSqlite":
        """Enter the managed context and mark the Unit of Work active."""
        self._active = True
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        """Finalize the context by committing or rolling back.

        Commits if no exception was raised; otherwise performs a rollback.
        Always clears the active flag at the end.
        """
        try:
            if exc_type is None:
                self.commit()
            else:
                self.rollback()
        finally:
            self._active = False

    def commit(self) -> None:
        """Commit the current transaction."""
        self._conn.commit()

    def rollback(self) -> None:
        """Rollback the current transaction (idempotent)."""
        self._conn.rollback()
