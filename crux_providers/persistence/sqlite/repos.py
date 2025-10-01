"""Public re-exports for SQLite repository adapters and Unit of Work.

This module now serves as a thin aggregator to preserve import stability while
keeping concrete implementations in focused modules that respect line-count and
one-class-per-file guidelines.
"""

from .keystore_repo import KeyStoreRepoSqlite
from .prefs_repo import PrefsRepoSqlite
from .metrics_repo import MetricsRepoSqlite
from .chatlog_repo import ChatLogRepoSqlite
from .unit_of_work import UnitOfWorkSqlite
from .helpers import _parse_created_at  # re-export for test compatibility

__all__ = [
    "KeyStoreRepoSqlite",
    "PrefsRepoSqlite",
    "MetricsRepoSqlite",
    "ChatLogRepoSqlite",
    "UnitOfWorkSqlite",
    "_parse_created_at",
]
