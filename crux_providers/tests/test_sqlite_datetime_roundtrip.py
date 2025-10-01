"""Deprecated: SQLite datetime roundtrip tests moved.

See `crux_providers/tests/persistence/sqlite/test_datetime_roundtrip.py`.
This file is intentionally skipped to avoid duplicate collection.
"""
import pytest

pytestmark = pytest.mark.skip(
    reason="Moved to crux_providers/tests/persistence/sqlite/test_datetime_roundtrip.py"
)
