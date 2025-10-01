from __future__ import annotations

import json
import sqlite3
import tempfile
from pathlib import Path
from typing import Dict

from crux_providers.persistence.sqlite.migrator import migrate_from_json_vault  # type: ignore  # pragma: no cover
from crux_providers.persistence.sqlite.repos import UnitOfWorkSqlite  # type: ignore  # pragma: no cover
from crux_providers.tests.utils import assert_true

_assert = assert_true


def _new_conn() -> sqlite3.Connection:
    """Create a new in-memory sqlite connection with required tables.

    Minimal schema is created for `keys` and `prefs` to satisfy repository
    expectations without pulling in unrelated tables (metrics, chat_logs) for
    these focused migration tests.
    """
    conn = sqlite3.connect(":memory:")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS keys (
            provider TEXT PRIMARY KEY,
            api_key TEXT NOT NULL,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS prefs (
            id INTEGER PRIMARY KEY,
            values_json TEXT,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    return conn


def _read_state(conn: sqlite3.Connection) -> Dict[str, Dict[str, str]]:
    """Helper to introspect current persisted keys & prefs for assertions.

    Returns plain dictionaries for both keys and prefs to keep tests focused on
    migration semantics rather than repository return types.
    """
    with UnitOfWorkSqlite(conn) as uow:
        providers = uow.keys.list_providers()  # type: ignore[attr-defined]
        keys = {p: (uow.keys.get_api_key(p) or "") for p in providers}
        prefs_snapshot = uow.prefs.get_prefs()  # type: ignore[attr-defined]
        prefs = prefs_snapshot.values
    return {"keys": keys, "prefs": prefs}


def test_no_files_noop() -> None:
    """When neither file exists, migration should not create tables with data."""
    conn = _new_conn()
    with tempfile.TemporaryDirectory() as tmp:
        migrate_from_json_vault(conn, tmp)
    state = _read_state(conn)
    _assert(state["keys"] == {}, f"Expected no keys imported: {state}")
    _assert(state["prefs"] == {}, f"Expected no prefs imported: {state}")
    # Explicitly close the SQLite connection to avoid ResourceWarning
    conn.close()


def test_only_keys_imported() -> None:
    conn = _new_conn()
    with tempfile.TemporaryDirectory() as tmp:
        Path(tmp, "keys.json").write_text(json.dumps({"openai": "KEY1", "other": "K2"}))
        migrate_from_json_vault(conn, tmp)
    state = _read_state(conn)
    _assert(state["keys"].get("openai") == "KEY1", f"Missing openai key: {state}")
    _assert(state["keys"].get("other") == "K2", f"Missing other key: {state}")
    _assert(state["prefs"] == {}, f"Prefs should remain empty: {state}")
    # Explicitly close the SQLite connection to avoid ResourceWarning
    conn.close()


def test_only_prefs_imported() -> None:
    conn = _new_conn()
    with tempfile.TemporaryDirectory() as tmp:
        Path(tmp, "prefs.json").write_text(json.dumps({"theme": "dark", "max": 5}))
        migrate_from_json_vault(conn, tmp)
    state = _read_state(conn)
    _assert(state["keys"] == {}, f"Keys should remain empty: {state}")
    # Value 5 should be coerced to string
    _assert(state["prefs"].get("max") == "5", f"Numeric pref not coerced: {state}")
    # Explicitly close the SQLite connection to avoid ResourceWarning
    conn.close()


def test_invalid_keys_json_ignored_prefs_still_loaded() -> None:
    conn = _new_conn()
    with tempfile.TemporaryDirectory() as tmp:
        Path(tmp, "keys.json").write_text("{ invalid json")
        Path(tmp, "prefs.json").write_text(json.dumps({"lang": "en"}))
        migrate_from_json_vault(conn, tmp)
    state = _read_state(conn)
    _assert(state["keys"] == {}, f"Malformed keys.json should be ignored: {state}")
    _assert(state["prefs"].get("lang") == "en", f"Prefs not imported after malformed keys.json: {state}")
    # Explicitly close the SQLite connection to avoid ResourceWarning
    conn.close()


def test_idempotent_and_overwrite() -> None:
    conn = _new_conn()
    with tempfile.TemporaryDirectory() as tmp:
        kf = Path(tmp, "keys.json")
        pf = Path(tmp, "prefs.json")
        kf.write_text(json.dumps({"openai": "OLD"}))
        pf.write_text(json.dumps({"mode": "basic"}))
        migrate_from_json_vault(conn, tmp)
        # Modify source
        kf.write_text(json.dumps({"openai": "NEW", "third": "X"}))
        pf.write_text(json.dumps({"mode": "advanced", "extra": True}))
        migrate_from_json_vault(conn, tmp)
    state = _read_state(conn)
    _assert(state["keys"].get("openai") == "NEW", f"Key not overwritten: {state}")
    _assert(state["keys"].get("third") == "X", f"New key not added: {state}")
    _assert(state["prefs"].get("mode") == "advanced", f"Pref not updated: {state}")
    _assert(state["prefs"].get("extra") == "True", f"Boolean pref not coerced to string: {state}")
    # Explicitly close the SQLite connection to avoid ResourceWarning
    conn.close()
