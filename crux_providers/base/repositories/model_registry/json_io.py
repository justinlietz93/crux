"""Deprecated module: JSON cache helpers removed (DB-first migration).

This module is intentionally empty. The model registry now persists and reads
exclusively from SQLite. JSON cache helpers were removed to avoid dual sources
of truth. Any legacy imports should be deleted; references remain here only to
prevent import errors in out-of-tree consumers until they migrate.
"""
