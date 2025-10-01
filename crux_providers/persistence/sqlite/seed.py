"""SQLite seed data import helpers.

This module centralizes the logic for importing initial API keys and
preferences from JSON files in a provider vault directory. Extracted from
`service/db.py` to reduce its size and cyclomatic complexity (Issue #42).

Responsibilities
----------------
- Read JSON mapping files safely (return None on any error or non-object root).
- Import keys and prefs only when target tables are empty (decision is made by
  caller; helpers perform idempotent upserts).
- Provide a single `import_seed_data(conn, vault_dir)` orchestration helper.

Failure Semantics
-----------------
Parsing or file errors are non-fatal; they short-circuit that specific file
import while leaving the database unchanged for that table. Timestamps are
stored as UTC ISO strings using the current time at import.

Timeout & Security Considerations
---------------------------------
All operations are local filesystem + SQLite writes; no network IO or external
processes invoked, so no explicit timeout wrapper is used here. Upstream
callers still execute within broader application timeouts as applicable.
"""

from __future__ import annotations

import contextlib
import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional
import sqlite3

__all__ = [
    "read_json_dict",
    "import_keys_json",
    "import_prefs_json",
    "import_seed_data",
]


def read_json_dict(file_path: str) -> Optional[Dict[str, Any]]:
    """Read a JSON file and return a dict root or None.

    Returns None if the file does not exist, cannot be parsed, or the root is
    not a JSON object.
    """
    if not os.path.exists(file_path):
        return None
    with contextlib.suppress(Exception):
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                return data
    return None


def import_keys_json(conn: sqlite3.Connection, vault_dir: str) -> None:
    """Import API keys from `keys.json` if present.

    Performs INSERT OR REPLACE for each key to maintain idempotency.
    """
    keys_path = os.path.join(vault_dir, "keys.json")
    data = read_json_dict(keys_path)
    if not data:
        return
    now = datetime.now(timezone.utc).isoformat()
    cur = conn.cursor()
    for k, v in data.items():
        cur.execute(
            "INSERT OR REPLACE INTO api_keys(provider, key, updated_at) VALUES (?, ?, ?)",
            (str(k), str(v), now),
        )


def import_prefs_json(conn: sqlite3.Connection, vault_dir: str) -> None:
    """Import preferences from `prefs.json` if present.

    Values are JSON-serialized to preserve type fidelity on retrieval.
    """
    prefs_path = os.path.join(vault_dir, "prefs.json")
    data = read_json_dict(prefs_path)
    if not data:
        return
    now = datetime.now(timezone.utc).isoformat()
    cur = conn.cursor()
    for k, v in data.items():
        cur.execute(
            "INSERT OR REPLACE INTO prefs(name, value, updated_at) VALUES (?, ?, ?)",
            (str(k), json.dumps(v), now),
        )


def import_seed_data(conn: sqlite3.Connection, vault_dir: str) -> None:
    """Import seed keys and prefs if tables are empty.

    Args:
        conn: Active SQLite connection.
        vault_dir: Directory containing optional `keys.json` / `prefs.json`.
    """
    cur = conn.cursor()
    with contextlib.suppress(Exception):
        cur.execute("SELECT COUNT(*) FROM api_keys")
        if cur.fetchone()[0] == 0:
            import_keys_json(conn, vault_dir)
    with contextlib.suppress(Exception):
        cur.execute("SELECT COUNT(*) FROM prefs")
        if cur.fetchone()[0] == 0:
            import_prefs_json(conn, vault_dir)
