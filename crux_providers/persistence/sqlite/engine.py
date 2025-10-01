"""SQLite engine helpers for the persistence layer.

Purpose
-------
Provide safe, centralized helpers for opening SQLite connections and ensuring
schema availability for local development and light-concurrency scenarios.

External dependencies
---------------------
- Standard library only (``sqlite3``). No side effects at import time.

Timeout and reliability strategy
--------------------------------
- Applies a standard ``busy_timeout`` (milliseconds) from
  ``crux_providers.config.defaults`` to mitigate lock contention.
- Enables WAL journaling and NORMAL synchronous mode for durability with good
  interactive performance.

Fallback semantics
------------------
No fallback/caching is implemented at this layer; callers should handle
operational errors and decide on degraded behavior if desired.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional

from ...config.defaults import (
    SQLITE_BUSY_TIMEOUT_MS,
    SQLITE_JOURNAL_MODE,
    SQLITE_SYNCHRONOUS,
)

DEFAULT_DB_DIR = Path(__file__).resolve().parent.parent.parent / "key_vault"
DEFAULT_DB_PATH = DEFAULT_DB_DIR / "providers.db"


def _ensure_dir(p: Path) -> None:
    """Create directory ``p`` (and parents) if missing.

    Parameters
    ----------
    p:
        Target directory to ensure exists.
    """
    p.mkdir(parents=True, exist_ok=True)


def get_db_path(db_path: Optional[str] = None) -> Path:
    """Return a concrete database file path.

    Parameters
    ----------
    db_path:
        Optional string path. When ``None``, defaults to ``DEFAULT_DB_PATH``.
        User-provided values are passed through ``Path.expanduser()`` to allow
        ``~`` home shortcuts.

    Returns
    -------
    Path
        Absolute path to the SQLite database file (not created yet).
    """
    return Path(db_path).expanduser() if db_path else DEFAULT_DB_PATH


def create_connection(db_path: Optional[str] = None) -> sqlite3.Connection:
    """Open a SQLite connection with sane defaults and apply PRAGMA settings.

    Behavior
    --------
    - Ensures the parent directory exists prior to opening the database file.
    - Avoids ``detect_types`` so that TIMESTAMP columns are returned as raw
      strings; repository code is responsible for explicit ISO8601 handling.
    - Applies journal mode, synchronous mode, and busy timeout from centralized
      defaults for safe local use.

    Parameters
    ----------
    db_path:
        Optional path to the database file. When omitted, ``DEFAULT_DB_PATH``
        is used.

    Returns
    -------
    sqlite3.Connection
        An open connection with ``row_factory`` set to ``sqlite3.Row``.
    """
    path = get_db_path(db_path)
    _ensure_dir(path.parent)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    # Performance and concurrency settings
    conn.execute(f"PRAGMA journal_mode={SQLITE_JOURNAL_MODE};")
    conn.execute(f"PRAGMA synchronous={SQLITE_SYNCHRONOUS};")
    conn.execute(f"PRAGMA busy_timeout={SQLITE_BUSY_TIMEOUT_MS};")  # ms
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    """Create required tables if they do not exist, then commit.

    Schema overview
    ---------------
    - ``keys``: provider → API key mapping
    - ``prefs``: singleton preferences row (values serialized as JSON)
    - ``chat_logs``: persisted chat transcripts
    - ``metrics``: per-invocation metrics with optional token counts

    Notes
    -----
    This function performs a ``COMMIT`` to persist DDL changes.
    """
    # keys table: provider -> encrypted/cleartext key
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS keys (
            provider TEXT PRIMARY KEY,
            api_key  TEXT NOT NULL,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """
    )

    # prefs: single row k/v as JSON for flexibility
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS prefs (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            values_json TEXT NOT NULL,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """
    )

    # chat logs
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS chat_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            provider TEXT NOT NULL,
            model TEXT NOT NULL,
            role_user TEXT NOT NULL,
            role_assistant TEXT,
            metadata_json TEXT NOT NULL,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """
    )

    # metrics
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            provider TEXT NOT NULL,
            model TEXT NOT NULL,
            latency_ms INTEGER NOT NULL,
            tokens_prompt INTEGER,
            tokens_completion INTEGER,
            success INTEGER NOT NULL,
            error_code TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """
    )

    conn.commit()


@contextmanager
def db_session(db_path: Optional[str] = None) -> Iterator[sqlite3.Connection]:
    """Context manager yielding a connection with schema initialized.

    Transaction semantics
    ---------------------
    - Commits when the context exits normally.
    - Rolls back if an exception is raised inside the context.
    - Always closes the connection on exit.

    Parameters
    ----------
    db_path:
        Optional path to the database file. When omitted, the default path is
        used.
    """
    conn = create_connection(db_path)
    try:
        init_schema(conn)
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
