"""Migrator idempotency tests for importing from JSON vault files."""
from __future__ import annotations

import json
from pathlib import Path

from crux_providers.persistence.sqlite.migrator import migrate_from_json_vault
from crux_providers.persistence.sqlite.engine import create_connection, init_schema


def _apply_migration(conn, vault_dir: Path) -> None:
    """Helper to run migration and commit in one step."""
    migrate_from_json_vault(conn, str(vault_dir))
    conn.commit()


def test_migrator_idempotent(tmp_path: Path):
    """Ensure repeated migrations do not duplicate rows and handle overwrites."""
    vault_dir = tmp_path / "vault"
    vault_dir.mkdir(parents=True, exist_ok=True)
    (vault_dir / "keys.json").write_text(json.dumps({"openai": "sk-123", "anthropic": "ak-456"}))
    (vault_dir / "prefs.json").write_text(json.dumps({"default_provider": "openai", "theme": "dark"}))

    db_path = tmp_path / "providers.db"
    conn = create_connection(str(db_path))
    init_schema(conn)

    # First migration
    _apply_migration(conn, vault_dir)
    cur = conn.execute("SELECT COUNT(*) FROM keys")
    assert cur.fetchone()[0] == 2  # nosec B101
    cur = conn.execute("SELECT values_json FROM prefs WHERE id = 1")
    values_first = json.loads(cur.fetchone()[0])
    assert values_first["default_provider"] == "openai"  # nosec B101

    # Second migration (should NOT duplicate rows or change values)
    _apply_migration(conn, vault_dir)
    cur = conn.execute("SELECT COUNT(*) FROM keys")
    assert cur.fetchone()[0] == 2  # nosec B101

    # Modify one key and re-run migration to ensure importer overwrites
    (vault_dir / "keys.json").write_text(json.dumps({"openai": "sk-NEW"}))
    _apply_migration(conn, vault_dir)
    cur = conn.execute("SELECT api_key FROM keys WHERE provider='openai'")
    assert cur.fetchone()[0] == "sk-NEW"  # nosec B101
    conn.close()
