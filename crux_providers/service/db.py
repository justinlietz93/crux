import contextlib
import atexit
import json
import os
import sqlite3
import threading
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from crux_providers.persistence.sqlite.sqlite_config import (
    enable_explicit_datetime,
    create_connection as _configured_sqlite_connection,
)
from crux_providers.persistence.sqlite.seed import import_seed_data
from crux_providers.persistence.sqlite.db_schema import ensure_schema as _ensure_schema

_conn_lock = threading.Lock()
_conn: Optional[sqlite3.Connection] = None
_db_path: Optional[str] = None

def _get_conn() -> sqlite3.Connection:
    """Returns a thread-safe SQLite connection to the database.

    Ensures the database connection is initialized and reused across calls. If the connection does not exist, it is created and configured for use in a multithreaded environment.

    Returns:
        sqlite3.Connection: The SQLite connection object.
    """
    global _conn
    # Bandit B101: avoid assert for runtime checks (can be stripped with -O).
    if not _db_path:
        raise RuntimeError("DB not initialized. Call init_db first.")
    if _conn is None:
        with _conn_lock:
            if _conn is None:
                # Ensure adapters registered before creating connection
                enable_explicit_datetime()
                # Use centralized configuration (applies WAL + busy timeout)
                _conn = _configured_sqlite_connection(_db_path)
                # Maintain previous row_factory expectation
                _conn.row_factory = sqlite3.Row
    return _conn


def _close_conn_safely() -> None:
    """Close the cached SQLite connection if it exists.

    This internal helper guards the global connection with the module-level
    lock and suppresses any close-time exceptions. It is intended for use by
    the public ``close_db()`` API and the process ``atexit`` hook to ensure
    we don't leak open sqlite3 connections which can surface as
    ``ResourceWarning`` during test runs under Python 3.13+.

    Side Effects:
        - If a connection is open, it will be closed and the cached reference
          set back to ``None``. The configured ``_db_path`` remains unchanged
          (so callers can re-initialize via ``_get_conn()`` after close if
          still needed within the same process lifecycle).
    """
    global _conn
    with _conn_lock:
        with contextlib.suppress(Exception):
            if _conn is not None:
                _conn.close()
        _conn = None


def close_db() -> None:
    """Public API to close the shared SQLite connection.

    Use this in tests or shutdown paths to proactively release the underlying
    sqlite3 connection and avoid resource warnings. Safe to call multiple
    times.

    Notes:
        This does not clear ``_db_path``. To fully reset both the connection
        and path (typical for isolated tests using temp DBs), prefer
        ``_reset_db_for_tests()``.
    """
    _close_conn_safely()


def ensure_initialized() -> None:
    """Initialize DB to default path if not already initialized.

    Useful for callers outside the FastAPI app (e.g., model importers).
    """
    if _db_path:
        return
    base_dir = os.path.dirname(__file__)
    vault_dir = os.path.normpath(os.path.join(base_dir, "..", "key_vault"))
    db_path = os.path.join(vault_dir, "providers.db")
    init_db(db_path, vault_dir)


def init_db(db_path: str, vault_dir: str) -> None:
    """Initialize the SQLite database and ensure schema and seed data are present.

    Sets the database path, creates necessary directories, initializes the schema, and imports seed data.

    Args:
        db_path: The file path to the SQLite database.
        vault_dir: The directory containing seed data for initialization.
    """
    global _db_path
    _reset_conn_if_switching_db(db_path)
    _db_path = db_path
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = _get_conn()
    cur = conn.cursor()
    _ensure_schema(cur)
    conn.commit()

    # One-time seed import separated for clarity (Issue #42)
    import_seed_data(conn, vault_dir)
    conn.commit()


def _reset_conn_if_switching_db(target_db_path: str) -> None:
    """Reset cached connection if switching to a different database file.

    Ensures that callers (notably tests or tooling that use temporary DBs)
    can call ``init_db`` repeatedly with different ``db_path`` values without
    leaking the existing connection. If no connection exists or the path is
    unchanged, this is a no-op.

    Parameters
    ----------
    target_db_path: str
        The database file path that ``init_db`` is about to use.

    Side Effects
    ------------
    - Closes the existing global connection if present and points to a
      different file than ``target_db_path``.
    - Sets the global cached connection reference back to ``None``.
    """
    global _conn
    if _conn is not None and _db_path and os.path.abspath(_db_path) != os.path.abspath(target_db_path):
        with _conn_lock:
            with contextlib.suppress(Exception):
                _conn.close()
            _conn = None

# schema helpers moved to db_schema.ensure_schema


## Seed import helpers moved to persistence.sqlite.seed (Issue #42).


# --- Public API ---


def load_keys() -> Dict[str, str]:
    """Retrieves all API keys stored in the database.

    Returns a dictionary mapping provider names to their corresponding API keys.

    Returns:
        Dict[str, str]: A dictionary of provider names and their API keys.
    """
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute("SELECT provider, key FROM api_keys")
    return {row[0]: row[1] for row in cur.fetchall()}


def save_keys(keys: Dict[str, str]) -> None:
    """Saves or updates API keys in the database.

    Inserts or replaces the provided API keys for each provider. If a key already exists for a provider, it will be updated.

    Args:
        keys (Dict[str, str]): A dictionary of provider names and their API keys.
    """
    if not keys:
        return
    now = datetime.now(timezone.utc).isoformat()
    conn = _get_conn()
    cur = conn.cursor()
    for k, v in keys.items():
        cur.execute(
            "INSERT OR REPLACE INTO api_keys(provider, key, updated_at) VALUES (?, ?, ?)",
            (str(k), str(v), now),
        )
    conn.commit()


def load_prefs() -> Dict[str, Any]:
    """Retrieves all user preferences stored in the database.

    Returns a dictionary mapping preference names to their corresponding values, deserialized from JSON if possible.

    Returns:
        Dict[str, Any]: A dictionary of preference names and their values.
    """
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute("SELECT name, value FROM prefs")
    out: Dict[str, Any] = {}
    for row in cur.fetchall():
        name = row[0]
        try:
            out[name] = json.loads(row[1])
        except Exception:
            out[name] = row[1]
    return out


def save_prefs(prefs: Dict[str, Any]) -> None:
    """Saves or updates user preferences in the database.

    Inserts or replaces the provided preferences for each name. If a
    preference already exists, it will be updated.

    Args:
        prefs (Dict[str, Any]): A dictionary of preference names and their values.
    """
    if not prefs:
        return
    now = datetime.now(timezone.utc).isoformat()
    conn = _get_conn()
    cur = conn.cursor()
    for k, v in prefs.items():
        cur.execute(
            "INSERT OR REPLACE INTO prefs(name, value, updated_at) VALUES (?, ?, ?)",
            (str(k), json.dumps(v), now),
        )
    conn.commit()


def delete_pref(name: str) -> bool:
    """Delete a single preference by name.

    Args:
        name (str): The preference key to remove.

    Returns:
        bool: True if a row was deleted, False if the key did not exist.
    """
    if not name:
        # Empty key deletion is a safe no-op to avoid accidental full-table operations.
        return False
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM prefs WHERE name = ?", (name,))
    conn.commit()
    return cur.rowcount > 0


# --- Observed capabilities (public API) ---
def record_observed_capability(
    provider: str,
    model_id: str,
    feature: str,
    value: bool,
    *,
    updated_at: Optional[str] = None,
) -> None:
    """Record or update an observed capability flag in SQLite.

    Parameters:
        provider: Provider identifier (e.g., "openai").
        model_id: Model identifier.
        feature: Capability name (e.g., "vision").
        value: True if supported, False if explicitly unsupported.
        updated_at: Optional ISO 8601 timestamp; defaults to now (UTC).
    """
    ensure_initialized()
    conn = _get_conn()
    cur = conn.cursor()
    ts = updated_at or datetime.now(timezone.utc).isoformat()
    cur.execute(
        """
        INSERT INTO observed_capabilities(provider, model_id, feature, value, updated_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(provider, model_id, feature)
        DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at
        """,
        (provider, model_id, feature, 1 if value else 0, ts),
    )
    conn.commit()


def load_observed_capabilities(provider: str) -> Dict[str, Dict[str, bool]]:
    """Load observed capability flags for a provider as a nested mapping."""
    ensure_initialized()
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT model_id, feature, value FROM observed_capabilities WHERE provider = ?",
        (provider,),
    )
    out: Dict[str, Dict[str, bool]] = {}
    for model_id, feature, value in cur.fetchall():
        d = out.get(model_id)
        if d is None:
            d = {}
            out[model_id] = d
        d[str(feature)] = bool(int(value))
    return out


# --- Testing / internal utilities ---
def _reset_db_for_tests() -> None:
    """Reset global DB connection/state for test isolation.

    Closes existing connection, clears the DB path, and allows subsequent
    tests to initialize a fresh temporary database.
    """
    global _conn, _db_path
    with _conn_lock:
        with contextlib.suppress(Exception):
            if _conn is not None:
                _conn.close()
        _conn = None
        _db_path = None


def record_metric(
    *,
    provider: Optional[str],
    model: Optional[str],
    duration_ms: Optional[int],
    status: str,
    error_type: Optional[str] = None,
    tokens_in: Optional[int] = None,
    tokens_out: Optional[int] = None,
) -> None:
    """Record a single provider metric row.

    Persists a metric entry capturing provider, model, duration, status, optional
    error type, and token counts. This helper performs an immediate insert and
    commits the transaction on success.

    Parameters:
        provider: Provider name (e.g., ``"openai"``). Nullable for generic events.
        model: Model identifier (e.g., ``"gpt-4o-mini"``). Nullable when unknown.
        duration_ms: Execution duration in milliseconds. If provided, must be
            greater than or equal to zero. ``None`` is allowed for events that
            did not complete or where timing is unavailable.
        status: Outcome label such as ``"ok"`` or ``"error"``.
        error_type: Optional error classification (e.g., ``"TimeoutError"``) when
            ``status == "error"``.
        tokens_in: Optional input token count.
        tokens_out: Optional output token count.

    Returns:
        None: The function writes to the database and commits; it does not
        return a value.

    Raises:
        ValueError: If ``duration_ms`` is provided and is negative.

    Side Effects:
        - Opens a connection (or reuses a cached one) via ``_get_conn()``.
        - Executes an ``INSERT`` into the ``metrics`` table.
        - Commits the current transaction upon success.

    Notes:
        - Timeouts/retries are not applicable at this layer; callers should
          apply provider-level retry/cancellation policies earlier in the call
          chain. This function is strictly a persistence primitive.
    """
    # Basic validation
    if duration_ms is not None and duration_ms < 0:
        raise ValueError("duration_ms cannot be negative")
    conn = _get_conn()
    cur = conn.cursor()
    now = datetime.now(timezone.utc).isoformat()
    metric_values = (
        now,
        provider,
        model,
        duration_ms,
        status,
        error_type,
        tokens_in,
        tokens_out,
    )
    cur.execute(
        """
        INSERT INTO metrics(ts, provider, model, duration_ms, status, error_type, tokens_in, tokens_out)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        metric_values,
    )
    conn.commit()


## Model registry helpers relocated
# Re-export helpers for backward compatibility; new code should import from
# `persistence.sqlite.model_registry_store`.
with contextlib.suppress(Exception):  # pragma: no cover - optional dependency
    from crux_providers.persistence.sqlite.model_registry_store import (  # type: ignore
        save_models_snapshot,
        load_models_snapshot,
        list_providers as _list_model_providers,
    )
    # Re-export to preserve backward compatibility for existing imports.
    globals()["save_models_snapshot"] = save_models_snapshot
    globals()["load_models_snapshot"] = load_models_snapshot
    globals()["list_model_providers"] = _list_model_providers
    # Help type checkers understand these are part of the module API.
    _existing_all = globals().get("__all__")
    if isinstance(_existing_all, list):
        _existing_all.extend(
            ["save_models_snapshot", "load_models_snapshot", "list_model_providers"]
        )  # type: ignore[misc]
    else:
        globals()["__all__"] = [
            "save_models_snapshot",
            "load_models_snapshot",
            "list_model_providers",
        ]


# Ensure the global SQLite connection is closed upon interpreter exit to avoid
# ResourceWarning noise in tests or tooling that inspects unclosed resources.
# This is safe because it simply closes if the connection exists; otherwise
# it's a no-op.
atexit.register(_close_conn_safely)
