"""SQLite schema helpers for the provider service.

Extracted from ``service.db`` to keep files under the 500-LOC limit and to
clarify responsibilities. This module contains table/index creation routines
only (no connection management or seed import).
"""

from __future__ import annotations

import sqlite3


def ensure_schema(cur: sqlite3.Cursor) -> None:
    """Create tables and indexes if they do not exist."""
    _create_core_tables(cur)
    _create_model_registry_tables(cur)
    _create_indexes(cur)


def _create_core_tables(cur: sqlite3.Cursor) -> None:
    """Create core tables for API keys, preferences, and metrics if they do not exist.

    This function initializes the main tables required for storing API keys, user preferences, and metrics.
    """
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS api_keys (
            provider TEXT PRIMARY KEY,
            key TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS prefs (
            name TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            provider TEXT,
            model TEXT,
            duration_ms INTEGER,
            status TEXT,
            error_type TEXT,
            tokens_in INTEGER,
            tokens_out INTEGER
        )
        """
    )


def _create_model_registry_tables(cur: sqlite3.Cursor) -> None:
    """Create model registry and related tables if they do not exist.

    This function sets up the tables for model registry, registry metadata, and observed capabilities.
    """
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS model_registry (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            provider TEXT NOT NULL,
            model_id TEXT NOT NULL,
            name TEXT,
            family TEXT,
            context_length INTEGER,
            capabilities TEXT,
            updated_at TEXT
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS model_registry_meta (
            provider TEXT PRIMARY KEY,
            fetched_at TEXT,
            fetched_via TEXT,
            metadata TEXT
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS observed_capabilities (
            provider TEXT NOT NULL,
            model_id TEXT NOT NULL,
            feature  TEXT NOT NULL,
            value    INTEGER NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (provider, model_id, feature)
        )
        """
    )


def _create_indexes(cur: sqlite3.Cursor) -> None:
    """Create indexes for metrics, model registry, and observed capabilities tables.

    This function ensures that the necessary indexes exist to optimize query performance on key columns.
    """
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_metrics_provider_model ON metrics(provider, model)"
    )
    cur.execute("CREATE INDEX IF NOT EXISTS idx_metrics_status ON metrics(status)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_metrics_ts ON metrics(ts)")
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_models_provider ON model_registry(provider)"
    )
    cur.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_models_provider_model ON model_registry(provider, model_id)"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_observed_provider_model ON observed_capabilities(provider, model_id)"
    )


__all__ = ["ensure_schema"]
