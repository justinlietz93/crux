"""Datetime adapter roundtrip & warning suppression test.

Validates:
1. No DeprecationWarning about sqlite timestamp conversion is emitted.
2. Datetime stored and retrieved matches original UTC value (within exact equality since ISO8601 preserves microseconds).
"""
from __future__ import annotations

from datetime import datetime, timezone
import warnings

from crux_providers.persistence.sqlite.sqlite_config import (
    create_connection,
)


def test_datetime_roundtrip_no_deprecation(tmp_path):
    db = tmp_path / "test_dt.sqlite"
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        conn = create_connection(str(db))
        with conn:
            conn.execute("CREATE TABLE sample (id INTEGER PRIMARY KEY, created TIMESTAMP)")
            now_utc = datetime.now(timezone.utc)
            conn.execute("INSERT INTO sample (created) VALUES (?)", (now_utc,))
            row = conn.execute("SELECT created FROM sample").fetchone()
        conn.close()
    # Filter for undesired deprecation warnings
    deprecations = [wn for wn in w if issubclass(wn.category, DeprecationWarning)]
    if any("sqlite" in str(wn.message).lower() and "timestamp" in str(wn.message).lower() for wn in deprecations):  # nosec - test validation
        raise AssertionError("Unexpected sqlite timestamp DeprecationWarning emitted")
    fetched = row[0]
    if fetched != now_utc:
        raise AssertionError(f"Roundtrip mismatch: stored {now_utc!r} fetched {fetched!r}")
