"""SQLite-backed implementation of ``IPrefsRepo``.

Stores a single-row preferences document with JSON-serialized values and an
``updated_at`` timestamp. All write operations defer transaction commit to the
Unit of Work. This adapter favors clear semantics and defensive parsing.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone

from ..interfaces.repos import IPrefsRepo, Prefs


class PrefsRepoSqlite(IPrefsRepo):
    """SQLite-backed repository for user preferences.

    Stores and retrieves user preferences as a single-row JSON document while
    tracking the last update timestamp. No implicit commits are performed.
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        """Initialize the preferences repository.

        Parameters
        ----------
        conn:
            Active SQLite connection configured by the engine layer.
        """
        self.conn = conn

    def get_prefs(self) -> Prefs:
        """Retrieve the current preferences snapshot.

        Returns
        -------
        Prefs
            Preferences DTO. When no row exists, returns an empty map with
            ``updated_at`` set to epoch UTC (aware).
        """
        cur = self.conn.execute(
            "SELECT values_json, updated_at FROM prefs WHERE id = 1"
        )
        row = cur.fetchone()
        if not row:
            # Use epoch UTC as aware datetime for initial prefs timestamp.
            return Prefs(values={}, updated_at=datetime.fromtimestamp(0, tz=timezone.utc))
        values = json.loads(row[0]) if row[0] else {}
        updated_at = (
            datetime.fromisoformat(row[1]) if isinstance(row[1], str) else row[1]
        )
        return Prefs(values=values, updated_at=updated_at)

    def set_prefs(self, values: dict[str, str]) -> Prefs:
        """Replace stored preferences atomically (no implicit commit).

        Parameters
        ----------
        values:
            Mapping of preference keys to string values.

        Returns
        -------
        Prefs
            Updated preferences snapshot after persistence.
        """
        values_json = json.dumps(values, ensure_ascii=False)
        self.conn.execute(
            "INSERT INTO prefs(id, values_json, updated_at) VALUES(1, ?, CURRENT_TIMESTAMP) ON CONFLICT(id) DO UPDATE SET values_json=excluded.values_json, updated_at=CURRENT_TIMESTAMP",
            (values_json,),
        )
        return self.get_prefs()
