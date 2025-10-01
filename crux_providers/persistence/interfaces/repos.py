"""Repository & Unit of Work protocol definitions for provider persistence layer.

This module declares the clean-architecture facing contracts used by the FastAPI
service layer. Controllers depend only on these abstractions; concrete
implementations live under `persistence/sqlite/` (or future backends).

Design Principles:
- No concrete behavior; pure structural typing via `Protocol`.
- Dataclasses represent DTOs crossing repository boundaries.
- No hard-coded timeouts or side effects; transaction control delegated to
    the `IUnitOfWork` implementation.

Failure / Error Semantics:
- Repository methods raise backend-specific exceptions only in truly
    exceptional conditions (I/O failures, integrity errors). Higher layers may
    add translation/adaptation as needed.

External Dependencies:
- None at runtime for these interfaces. Concrete implementations under
    `persistence/sqlite/` may depend on SQLite and related drivers, but those are
    not required to import or use these protocols and DTOs.

Timeout Strategy:
- These abstractions define contracts only and therefore introduce no timeouts.
    Implementations MUST source timeouts from centralized configuration
    (`get_timeout_config()`), and callers SHOULD wrap blocking start phases in
    `operation_timeout` where applicable.

Fallback Semantics:
- Interfaces do not provide fallback behavior. Implementations MAY offer
    read-only degradation (e.g., returning cached snapshots) where appropriate,
    but MUST document such behavior explicitly in their modules.

Extensibility Notes:
- Additional aggregate/query methods should be added here first, then
    implemented by concrete repos and exercised with contract tests.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Protocol, Tuple

# ---------- Data Transfer Objects ----------


@dataclass
class Prefs:
    """Preference key/value store snapshot.

    Attributes
    ----------
    values:
        Map of preference keys to string values (persisted as JSON).
    updated_at:
        Last modification timestamp in UTC.
    """

    values: Dict[str, str]
    updated_at: datetime


@dataclass
class MetricEntry:
    """Single invocation metric record.

    Attributes
    ----------
    provider: Normalized provider identifier (lowercase).
    model: Model identifier used for the request.
    latency_ms: End-to-end latency in milliseconds.
    tokens_prompt: Optional prompt token count (if available from provider).
    tokens_completion: Optional completion token count.
    success: True when request completed without provider error.
    error_code: Optional normalized error code when success is False.
    created_at: UTC timestamp of when the metric was recorded.
    """

    provider: str
    model: str
    latency_ms: int
    tokens_prompt: Optional[int]
    tokens_completion: Optional[int]
    success: bool
    error_code: Optional[str]
    created_at: datetime


@dataclass
class ChatLog:
    """Persisted chat exchange row.

    Attributes
    ----------
    id: Primary key (None until persisted).
    provider: Provider name for the interaction.
    model: Model used.
    role_user: User message content.
    role_assistant: Assistant reply (may be None if streaming not finalized).
    metadata: Opaque structured data (JSON serialized) for auxiliary info.
    created_at: UTC timestamp for ordering.
    """

    id: Optional[int]
    provider: str
    model: str
    role_user: str
    role_assistant: Optional[str]
    metadata: Dict[str, str]
    created_at: datetime


# ---------- Repository Protocols ----------


class IKeyStoreRepo(Protocol):
    """API key storage abstraction.

    All provider identifiers MUST be stored and returned in normalized (lowercase)
    form to ensure case-insensitive behavior at the service layer.
    """

    def get_api_key(self, provider: str) -> Optional[str]:
        """Return the API key for a given provider.

        Parameters
        ----------
        provider:
            Normalized (lowercase) provider identifier.

        Returns
        -------
        Optional[str]
            The stored API key if present; otherwise ``None``.
        """
        ...

    def set_api_key(self, provider: str, key: str) -> None:
        """Create or update the API key for a provider.

        Parameters
        ----------
        provider:
            Normalized provider identifier.
        key:
            API key value to persist.

        Notes
        -----
        No implicit commit is performed; caller controls transaction boundaries.
        """
        ...

    def delete_api_key(self, provider: str) -> None:
        """Remove the API key for a provider if present.

        Parameters
        ----------
        provider:
            Normalized provider identifier.

        Notes
        -----
        This operation is idempotent and MUST NOT perform an implicit commit.
        """
        ...

    def list_providers(self) -> List[str]:
        """Return a sorted list of providers with stored API keys.

        Returns
        -------
        List[str]
            Sorted list (ascending) of normalized provider identifiers.
        """
        ...


class IPrefsRepo(Protocol):
    """Preferences repository abstraction."""

    def get_prefs(self) -> Prefs:
        """Fetch the current preference snapshot.

        Returns
        -------
        Prefs
            A preferences DTO representing the current values.

        Notes
        -----
        Implementations may create an empty row if storage is uninitialized.
        """
        ...

    def set_prefs(self, values: Dict[str, str]) -> Prefs:
        """Replace stored preferences atomically (no implicit commit).

        Parameters
        ----------
        values:
            Mapping of preference keys to string values.

        Returns
        -------
        Prefs
            The updated preference snapshot.

        Notes
        -----
        Transaction commit is controlled by the caller's Unit of Work.
        """
        ...

class IMetricsRepo(Protocol):
    """Metrics repository providing persistence & aggregate queries."""
    def add_metric(self, entry: MetricEntry) -> None:
        """Persist a single metric entry.

        Implementations perform an INSERT but MUST NOT commit; caller
        controls transaction via UnitOfWork boundary.
        """
        ...

    def aggregate_latency(
        self, provider: str, model: Optional[str] = None
    ) -> Tuple[int, int]:
        """Return aggregate latency statistics for a given scope.

        Parameters
        ----------
        provider:
            Normalized provider identifier to filter by.
        model:
            Optional model identifier; when provided, restrict aggregation to
            that model, otherwise include all models for the provider.

        Returns
        -------
        Tuple[int, int]
            A tuple of ``(count, avg_latency_ms)`` where ``count`` is the
            number of metric rows considered and ``avg_latency_ms`` is the
            average latency (rounded/truncated per implementation contract).
        """
        ...

    def recent_errors(self, limit: int = 50) -> Iterable[MetricEntry]:
        """Yield the most recent error metric entries.

        Parameters
        ----------
        limit:
            Maximum number of rows to return (default 50).

        Returns
        -------
        Iterable[MetricEntry]
            An iterable of error entries ordered from newest to oldest.
        """
        ...

    def summary(self) -> Dict[str, Any]:  # pragma: no cover
        """Return aggregate usage summary across all metrics.

        Contract mirrors legacy `svcdb.metrics_summary()` output shape:
        {
            "total": int,                          # total metric rows
            "by_provider": [                       # descending by count
                {"provider": str, "count": int, "avg_ms": float},
            ],
            "by_model": [                          # top N models (impl may truncate)
                {"model": str, "count": int, "avg_ms": float},
            ],
        }

        Implementations MUST:
        - Exclude soft-deleted / invalid rows (if schema adds such flags later).
        - Return counts as integers and average latency as float milliseconds.
        - Not perform a commit (pure read aggregation) and avoid side effects.
        """
        ...


class IChatLogRepo(Protocol):
    """Chat transcript storage abstraction."""

    def add(self, log: ChatLog) -> int:
        """Persist a new chat log row returning its primary key.

        Parameters
        ----------
        log:
            The chat log DTO to persist.

        Returns
        -------
        int
            The auto-incremented primary key of the inserted row.

        Notes
        -----
        No implicit commit; caller controls transaction boundaries.
        """
        ...

    def get(self, chat_id: int) -> Optional[ChatLog]:
        """Return a chat log by primary key.

        Parameters
        ----------
        chat_id:
            Primary key of the chat log.

        Returns
        -------
        Optional[ChatLog]
            The chat log instance if found, otherwise ``None``.
        """
        ...

    def list_recent(self, limit: int = 100) -> Iterable[ChatLog]:
        """Yield the most recent chat logs in descending chronological order.

        Parameters
        ----------
        limit:
            Maximum number of rows to return (default 100).

        Returns
        -------
        Iterable[ChatLog]
            An iterable of chat log records.
        """
        ...


class IUnitOfWork(Protocol):
    """Transactional boundary aggregating repository instances.

    Implementations manage lifecycle of underlying connections / sessions.
    All write operations MUST be explicitly committed by calling `commit()`;
    otherwise they are subject to rollback semantics on scope exit.
    """

    keys: IKeyStoreRepo
    prefs: IPrefsRepo
    metrics: IMetricsRepo
    chats: IChatLogRepo

    def __enter__(self) -> "IUnitOfWork":  # pragma: no cover
        """Enter the managed context.

        Returns
        -------
        IUnitOfWork
            The active Unit of Work instance to be used within the context.
        """
        ...

    def __exit__(self, exc_type, exc, tb) -> None:  # pragma: no cover
        """Cleanup context resources.

        Parameters
        ----------
        exc_type:
            Exception type if an error was raised within the context; otherwise ``None``.
        exc:
            Exception instance; otherwise ``None``.
        tb:
            Traceback instance; otherwise ``None``.

        Notes
        -----
        Implementations may rollback if an exception occurred.
        """
        ...

    def commit(self) -> None:
        """Persist all pending changes atomically.

        Notes
        -----
        After successful commit, pending Unit of Work state should be cleared
        or reinitialized according to the implementation's transaction model.
        """
        ...

    def rollback(self) -> None:
        """Undo all uncommitted changes.

        Notes
        -----
        This operation MUST be idempotent and safe to call multiple times.
        """
        ...
