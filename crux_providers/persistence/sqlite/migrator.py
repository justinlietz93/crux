from __future__ import annotations

import json
import sqlite3
from contextlib import suppress
from pathlib import Path
from typing import Optional

from .repos import UnitOfWorkSqlite


def _vault_base(vault_dir: Optional[str]) -> Path:
    """Resolve the directory containing legacy JSON vault files.

    The vault contains optional `keys.json` and `prefs.json` used for a one-time
    (idempotent) bootstrap of API credentials and user preferences into the
    SQLite persistence stores. If `vault_dir` is not supplied, the function
    defaults to the packaged `crux_providers/key_vault` directory so local
    development can seed data without extra configuration.

    Parameters
    ----------
    vault_dir: Optional[str]
        Optional explicit filesystem path to a directory containing
        `keys.json` and/or `prefs.json`.

    Returns
    -------
    Path
        Absolute `Path` to the directory that should be inspected for legacy
        JSON seed files.
    """
    return (
        Path(vault_dir)
        if vault_dir
        else Path(__file__).resolve().parent.parent.parent / "key_vault"
    )


def _import_keys(uow: UnitOfWorkSqlite, keys_path: Path) -> None:
    """Import provider API keys from a legacy `keys.json` file.

    Behavior
    --------
    - Silently returns if the file does not exist.
    - Wraps parsing in a broad exception suppressor because malformed JSON or
      unexpected types should not abort the overall migration (best-effort import).
    - Only string→string pairs with non-empty values are persisted.
    - Each key is upserted via the keys repository (`set_api_key`).

    Parameters
    ----------
    uow: UnitOfWorkSqlite
        Active unit of work managing repositories in a transaction scope.
    keys_path: Path
        Path to the `keys.json` file to parse.

    Failure Modes
    -------------
    - Malformed JSON, non-dict top-level structure, or non-string members are
      ignored (no exception raised).
    - Unexpected exceptions (I/O, JSON decode) are suppressed by design.
    """
    if not keys_path.exists():
        return
    with suppress(Exception):  # pragma: no cover - defensive
        data = json.loads(keys_path.read_text())
        if isinstance(data, dict):
            for provider, key in data.items():
                if isinstance(provider, str) and isinstance(key, str) and key:
                    uow.keys.set_api_key(provider, key)


def _import_prefs(uow: UnitOfWorkSqlite, prefs_path: Path) -> None:
    """Import user preference key/value pairs from legacy `prefs.json`.

    Behavior mirrors `_import_keys` but coerces all values to strings to ensure
    consistent storage. Non-existent or invalid files are ignored silently.

    Parameters
    ----------
    uow: UnitOfWorkSqlite
        Active unit of work for persistence.
    prefs_path: Path
        Path to the `prefs.json` file.

    Notes
    -----
    - All values are stringified (`str(v)`) to avoid schema drift if upstream
      JSON contains mixed numeric / boolean types.
    - Broad suppression maintains idempotent, best-effort semantics.
    """
    if not prefs_path.exists():
        return
    with suppress(Exception):  # pragma: no cover - defensive
        pdata = json.loads(prefs_path.read_text())
        if isinstance(pdata, dict):
            uow.prefs.set_prefs({k: str(v) for k, v in pdata.items()})


def migrate_from_json_vault(
    conn: sqlite3.Connection, vault_dir: Optional[str] = None
) -> None:
    """Idempotently migrate legacy JSON vault data into SQLite repositories.

    This function is the public entry point for seeding provider API keys and
    user preference values from optional JSON files. Its operation is *safe* to
    call multiple times: keys are upserted (overwriting existing values) and
    preferences are fully replaced each run, producing deterministic final
    state that mirrors the source files.

    Source Files
    ------------
    - `keys.json`: Mapping of `{provider: api_key}` (strings only). Empty or
      invalid entries are skipped.
    - `prefs.json`: Mapping of arbitrary preference keys to primitive values;
      all values are coerced to strings before persistence.

    Parameters
    ----------
    conn: sqlite3.Connection
        Open SQLite connection. Caller owns connection lifetime.
    vault_dir: Optional[str]
        Optional explicit directory containing the JSON vault. If omitted,
        uses the packaged default via `_vault_base`.

    Behavior
    --------
    - Quickly returns if neither file exists (reduces unnecessary UoW setup).
    - Executes imports inside a UnitOfWork to ensure atomicity on success.
    - Broad exceptions during individual file import are suppressed to avoid
      partial termination; other file (if present) will still be attempted.

    Failure Modes
    -------------
    - Silently no-ops if files are missing or malformed.
    - Does NOT raise on JSON parsing failures (best-effort seed philosophy).

    Idempotency
    -----------
    Re-running the migration produces the same persisted state except where
    source file *contents* changed (in which case keys/prefs are updated to
    match the new content).
    """
    base = _vault_base(vault_dir)
    keys_path = base / "keys.json"
    prefs_path = base / "prefs.json"

    # Early exit if neither file exists (reduces branching depth)
    if not (keys_path.exists() or prefs_path.exists()):
        return

    with UnitOfWorkSqlite(conn) as uow:
        _import_keys(uow, keys_path)
        _import_prefs(uow, prefs_path)
