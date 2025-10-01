"""Deprecated: SQLite tests moved to `crux_providers/tests/persistence/sqlite/`.

This legacy aggregator file is intentionally skipped to avoid duplicate test
collection. See the focused tests under `persistence/sqlite/` for active
coverage (keys, prefs, metrics, chatlog, migrator, unit_of_work).
"""
import pytest

# Skip entire module with clear pointer to the new location
pytestmark = pytest.mark.skip(
    reason="Moved to crux_providers/tests/persistence/sqlite/*.py"
)
