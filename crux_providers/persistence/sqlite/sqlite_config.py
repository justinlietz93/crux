"""SQLite configuration utilities.

Purpose
-------
Centralize SQLite connection initialization, explicit datetime handling, and
(transitional) suppression of noisy Python 3.12 deprecation warnings related to
implicit timestamp conversion.

This module defines an explicit adapter/converter pair for timezone-aware
UTC datetimes using ISO 8601 (``YYYY-MM-DDTHH:MM:SS.ffffff+00:00``). It should
be imported exactly once early in application startup (e.g., before repository
initialization) so that global sqlite3 registration occurs.

Deprecation Warning Strategy
----------------------------
Python 3.12 introduced a deprecation for legacy timestamp conversion behaviors.
This module relies exclusively on explicit adapters/converters, so no warning
filter is required. Earlier transitional filters have been removed after the
refactors tracked in issues #39 and #42 were completed.

Functions
---------
create_connection(path: str) -> sqlite3.Connection
    Returns a connection with adapters registered and pragmatic settings applied.

enable_explicit_datetime(): None
    Registers adapter/converter once (idempotent) and installs warning filter.

Design Notes
------------
* WAL journaling + busy_timeout improve concurrency under read-heavy workloads.
* We enforce UTC datetimes; naive datetimes raise ValueError to avoid silent TZ bugs.
* Connection uses detect_types flags to trigger converter invocation.

Interop With engine.py
----------------------
There are two connection factories in this codebase:

1) This module (`sqlite_config.create_connection`) which registers explicit
    adapters/converters and uses `detect_types` for typed round-trips. It is
    used by `providers.service.db` and associated tests that assert strict UTC
    behavior and warning suppression.

2) `persistence/sqlite/engine.py.create_connection` which intentionally avoids
    `detect_types` so timestamp columns are returned as raw strings; callers
    then parse ISO8601 explicitly (see `repos._parse_created_at`). This path is
    used by maintenance utilities (e.g., timestamp backfill) and legacy repos
    that rely on string parsing semantics.

Do not mix connections from both factories in the same code path; choose the
appropriate strategy per caller. Migration roadmap tracks consolidating on a
single explicit policy once upstream repositories are fully refactored.
"""
from __future__ import annotations

from datetime import datetime, timezone
import sqlite3
from pathlib import Path

_ADAPTER_REGISTERED = False


def _adapt_datetime(value: datetime) -> str:
    """Adapt a timezone-aware UTC datetime to ISO8601 TEXT.

    Raises
    ------
    ValueError
        If the datetime is naive or not UTC.
    """
    if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
        raise ValueError("Datetime must be timezone-aware UTC")
    # Normalize to UTC explicitly
    return value.astimezone(timezone.utc).isoformat()


def _convert_datetime(raw: bytes) -> datetime:
    """Convert ISO8601 TEXT column back to UTC-aware datetime.

    Parameters
    ----------
    raw: bytes
        Raw value from SQLite driver.
    """
    text = raw.decode("utf-8")
    # Using fromisoformat preserves microseconds and offset
    dt = datetime.fromisoformat(text)
    # Ensure UTC normalization (some inputs might include +00:00 still OK)
    return dt.astimezone(timezone.utc)


def enable_explicit_datetime() -> None:
    """Register datetime adapters/converters for ISO8601 UTC round-trips.

    Idempotent: safe to call multiple times.
    """
    global _ADAPTER_REGISTERED
    if _ADAPTER_REGISTERED:
        return

    sqlite3.register_adapter(datetime, _adapt_datetime)
    sqlite3.register_converter("TIMESTAMP", _convert_datetime)
    sqlite3.register_converter("DATETIME", _convert_datetime)
    _ADAPTER_REGISTERED = True


def create_connection(path: str) -> sqlite3.Connection:
    """Create a configured SQLite connection.

    Applies:
    * Explicit datetime adapters
    * WAL journal mode
    * busy_timeout (5s) to mitigate lock contention

    Parameters
    ----------
    path: str
        Filesystem path to SQLite database file. Creates parent dirs if needed.
    """
    enable_explicit_datetime()
    db_path = Path(path)
    if not db_path.parent.exists():  # pragma: no cover - defensive
        db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(
        str(db_path),
        detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES,
        isolation_level=None,  # autocommit style; adjust if transactions layered elsewhere
        check_same_thread=False,
    )
    # Pragmas
    with conn:  # autocommit context
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA busy_timeout=5000;")
    return conn


__all__ = [
    "create_connection",
    "enable_explicit_datetime",
]
