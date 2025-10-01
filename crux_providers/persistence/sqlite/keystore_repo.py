"""SQLite-backed implementation of ``IKeyStoreRepo``.

This module provides the ``KeyStoreRepoSqlite`` class responsible for storing
and retrieving provider API keys. All write operations defer transaction
commit/rollback to the surrounding Unit of Work, ensuring clean separation of
concerns and testability.
"""

from __future__ import annotations

import sqlite3
from typing import List, Optional

from ..interfaces.repos import IKeyStoreRepo


class KeyStoreRepoSqlite(IKeyStoreRepo):
    """SQLite-backed repository for managing API keys.

    Provides methods to store, retrieve, update, and delete API keys for
    different providers using SQLite. All writes defer transaction commit to
    the Unit of Work; no implicit commits occur here.
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        """Initialize the key store repository.

        Parameters
        ----------
        conn:
            Active SQLite connection configured by the engine layer.
        """
        self.conn = conn

    def get_api_key(self, provider: str) -> Optional[str]:
        """Retrieve the API key for a given provider.

        Parameters
        ----------
        provider:
            Provider identifier (case-insensitive); normalized to lowercase.

        Returns
        -------
        Optional[str]
            The API key if present, otherwise ``None``.
        """
        cur = self.conn.execute(
            "SELECT api_key FROM keys WHERE provider = ?", (provider.lower(),)
        )
        row = cur.fetchone()
        return row[0] if row else None

    def set_api_key(self, provider: str, key: str) -> None:
        """Insert or update an API key for a provider (no implicit commit).

        Parameters
        ----------
        provider:
            Provider identifier (case-insensitive); normalized to lowercase.
        key:
            API key value to persist.

        Side Effects
        ------------
        Performs an upsert into the ``keys`` table and updates ``updated_at``.
        Transaction commit is deferred to the surrounding Unit of Work.
        """
        self.conn.execute(
            "INSERT INTO keys(provider, api_key, updated_at) VALUES(?, ?, CURRENT_TIMESTAMP) ON CONFLICT(provider) DO UPDATE SET api_key=excluded.api_key, updated_at=CURRENT_TIMESTAMP",
            (provider.lower(), key),
        )

    def delete_api_key(self, provider: str) -> None:
        """Delete the API key for a given provider (idempotent, no commit).

        Parameters
        ----------
        provider:
            Provider identifier (case-insensitive); normalized to lowercase.
        """
        self.conn.execute("DELETE FROM keys WHERE provider = ?", (provider.lower(),))

    def list_providers(self) -> List[str]:
        """Return a sorted list of providers with stored API keys.

        Returns
        -------
        List[str]
            Provider identifiers in ascending lexical order.
        """
        cur = self.conn.execute("SELECT provider FROM keys ORDER BY provider")
        return [r[0] for r in cur.fetchall()]
