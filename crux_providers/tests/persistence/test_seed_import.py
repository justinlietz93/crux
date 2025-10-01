"""Tests for seed data import helpers (Issue #42).

Validates that keys and prefs JSON files are imported only when tables are
empty and that subsequent calls do not duplicate data.
"""

from __future__ import annotations

import json
import os
import sqlite3
import tempfile

from crux_providers.persistence.sqlite.seed import import_seed_data
from crux_providers.persistence.sqlite.sqlite_config import (
    create_connection,
    enable_explicit_datetime,
)


def _make_conn(db_path: str) -> sqlite3.Connection:
    enable_explicit_datetime()
    conn = create_connection(db_path)
    cur = conn.cursor()
    # Minimal schema subset for seeding
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS api_keys (
            provider TEXT PRIMARY KEY,
            key TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS prefs (
            name TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    conn.commit()
    return conn


def test_seed_import_only_when_empty():
    tmpdir = tempfile.TemporaryDirectory()
    vault_dir = tmpdir.name
    db_path = os.path.join(vault_dir, "seed.db")
    # Write seed JSON files
    with open(os.path.join(vault_dir, "keys.json"), "w", encoding="utf-8") as f:
        json.dump({"openai": "KEY1", "xai": "KEY2"}, f)
    with open(os.path.join(vault_dir, "prefs.json"), "w", encoding="utf-8") as f:
        json.dump({"temperature": 0.7, "max_tokens": 1024}, f)

    conn = _make_conn(db_path)
    import_seed_data(conn, vault_dir)
    cur = conn.cursor()
    cur.execute("SELECT provider, key FROM api_keys ORDER BY provider")
    keys = cur.fetchall()
    if len(keys) != 2:
        raise AssertionError("Expected 2 keys imported on first run")
    cur.execute("SELECT name, value FROM prefs ORDER BY name")
    prefs = cur.fetchall()
    if len(prefs) != 2:
        raise AssertionError("Expected 2 prefs imported on first run")

    # Modify JSON to ensure second import isn't applied when tables non-empty
    with open(os.path.join(vault_dir, "keys.json"), "w", encoding="utf-8") as f:
        json.dump({"new": "SHOULD_NOT_APPLY"}, f)
    import_seed_data(conn, vault_dir)
    cur.execute("SELECT COUNT(*) FROM api_keys")
    if cur.fetchone()[0] != 2:
        raise AssertionError("Seed import should not reapply when table non-empty")
    # Close connection
    conn.close()


def test_seed_import_idempotent_upsert_when_empty_then_modified():
    tmpdir = tempfile.TemporaryDirectory()
    vault_dir = tmpdir.name
    db_path = os.path.join(vault_dir, "seed2.db")
    with open(os.path.join(vault_dir, "keys.json"), "w", encoding="utf-8") as f:
        json.dump({"openai": "K1"}, f)
    conn = _make_conn(db_path)
    import_seed_data(conn, vault_dir)
    # Clear keys table to simulate re-seed scenario
    cur = conn.cursor()
    cur.execute("DELETE FROM api_keys")
    conn.commit()
    with open(os.path.join(vault_dir, "keys.json"), "w", encoding="utf-8") as f:
        json.dump({"openai": "K2"}, f)
    import_seed_data(conn, vault_dir)
    cur.execute("SELECT key FROM api_keys WHERE provider='openai'")
    val = cur.fetchone()[0]
    if val != "K2":
        raise AssertionError("Upsert after table clear should import updated value")
    # Close connection
    conn.close()
