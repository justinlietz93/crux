"""Schema initialization tests for the SQLite persistence layer.

This test suite validates that the `ensure_schema` helper creates all
required tables and indexes when run against a fresh in-memory database.
"""

from __future__ import annotations

import sqlite3

from crux_providers.persistence.sqlite.db_schema import ensure_schema


def _fetch_names(cur: sqlite3.Cursor, typ: str) -> set[str]:
    """Return a set of object names from ``sqlite_master`` for the given type.

    Parameters:
        cur: Active SQLite cursor.
        typ: Object type filter (e.g., ``"table"`` or ``"index"``).

    Returns:
        A set of object names.
    """

    return {
        row[0]
        for row in cur.execute(
            "SELECT name FROM sqlite_master WHERE type = ?", (typ,)
        )
    }


def test_ensure_schema_creates_tables_and_indexes() -> None:
    """Ensure `ensure_schema` creates all tables and indexes as expected.

    The test runs schema initialization against an in-memory SQLite database
    and asserts that required tables and indexes exist. It also validates that
    the composite model registry index is unique as intended.
    """

    conn = sqlite3.connect(":memory:")
    try:
        cur = conn.cursor()
        ensure_schema(cur)
        conn.commit()

        expected_tables = {
            "api_keys",
            "prefs",
            "metrics",
            "model_registry",
            "model_registry_meta",
            "observed_capabilities",
        }
        tables = _fetch_names(cur, "table")
        assert expected_tables.issubset(tables)  # nosec B101 - pytest test assertion; safe in tests

        expected_indexes = {
            "idx_metrics_provider_model",
            "idx_metrics_status",
            "idx_metrics_ts",
            "idx_models_provider",
            "idx_models_provider_model",
            "idx_observed_provider_model",
        }
        indexes = _fetch_names(cur, "index")
        assert expected_indexes.issubset(indexes)  # nosec B101 - pytest test assertion; safe in tests

        # Validate uniqueness for the composite (provider, model_id) index
        # on model_registry.
        pragma_rows = list(cur.execute("PRAGMA index_list('model_registry')"))
        # PRAGMA index_list columns: seq, name, unique, origin, partial
        unique_by_name = {row[1]: row[2] for row in pragma_rows}
        assert unique_by_name.get("idx_models_provider_model") == 1  # nosec B101 - pytest test assertion; safe in tests
    finally:
        conn.close()
