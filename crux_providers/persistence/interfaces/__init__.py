"""Persistence interfaces package for provider service.

Defines repository protocols and shared DTOs for keys, prefs, metrics, and chat logs,
plus a Unit of Work abstraction. Concrete implementations live under persistence adapters
such as SQLite.
"""

from .repos import (  # noqa: F401
    ChatLog,
    IChatLogRepo,
    IKeyStoreRepo,
    IMetricsRepo,
    IPrefsRepo,
    IUnitOfWork,
    MetricEntry,
    Prefs,
)
