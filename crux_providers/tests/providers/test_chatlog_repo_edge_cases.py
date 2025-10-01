from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from typing import Dict

from crux_providers.persistence.sqlite.repos import UnitOfWorkSqlite  # type: ignore  # pragma: no cover
from crux_providers.tests.utils import assert_true

_assert = assert_true


def _new_conn() -> sqlite3.Connection:
    """Create a fresh in-memory connection with only the chat_logs table.

    Returns:
        sqlite3.Connection: Configured connection ready for repository use.
    """
    conn = sqlite3.connect(":memory:")
    conn.execute(
        """
        CREATE TABLE chat_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            provider TEXT NOT NULL,
            model TEXT NOT NULL,
            role_user TEXT NOT NULL,
            role_assistant TEXT,
            metadata_json TEXT NOT NULL,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    return conn


def _add_log(
    conn: sqlite3.Connection,
    provider: str,
    model: str,
    user: str,
    assistant: str | None,
    metadata: Dict[str, str],
    created_at: datetime,
) -> int:
    """Insert a chat log row via the Unit of Work and return its id.

    Imported inline to avoid an unused import when only helper uses the DTO.
    """
    from crux_providers.persistence.interfaces import ChatLog  # type: ignore  # pragma: no cover

    with UnitOfWorkSqlite(conn) as uow:
        log = ChatLog(
            id=None,
            provider=provider,
            model=model,
            role_user=user,
            role_assistant=assistant,
            metadata=metadata,
            created_at=created_at,
        )
        new_id = uow.chats.add(log)  # type: ignore[attr-defined]
    return new_id


def test_empty_list_recent_returns_no_logs() -> None:
    conn = _new_conn()
    with UnitOfWorkSqlite(conn) as uow:
        logs = list(uow.chats.list_recent())  # type: ignore[attr-defined]
    _assert(not logs, f"Expected empty list when no chat logs exist: {logs}")
    # Explicitly close the SQLite connection to avoid ResourceWarning
    conn.close()


def test_add_and_get_log_metadata_roundtrip() -> None:
    conn = _new_conn()
    ts = datetime.now(UTC)
    metadata = {"session": "abc123", "topic": "intro"}
    new_id = _add_log(conn, "openai", "gpt-4", "Hello", "Hi there", metadata, ts)

    with UnitOfWorkSqlite(conn) as uow:
        fetched = uow.chats.get(new_id)  # type: ignore[attr-defined]
    _assert(fetched is not None, "Expected fetched chat log not None")
    _assert(fetched.id == new_id, f"ID mismatch: {fetched}")
    _assert(fetched.provider == "openai", f"Provider mismatch: {fetched}")
    _assert(fetched.model == "gpt-4", f"Model mismatch: {fetched}")
    _assert(fetched.role_user == "Hello", f"User role mismatch: {fetched}")
    _assert(fetched.role_assistant == "Hi there", f"Assistant role mismatch: {fetched}")
    _assert(fetched.metadata == metadata, f"Metadata mismatch: {fetched.metadata}")
    # Explicitly close the SQLite connection to avoid ResourceWarning
    conn.close()


def test_list_recent_ordering_desc_created_at() -> None:
    conn = _new_conn()
    base = datetime.now(UTC) - timedelta(minutes=5)
    # Insert 3 logs with ascending timestamps; expect reverse order in list_recent
    ids = [
        _add_log(
            conn,
            "anthropic" if i % 2 == 0 else "openai",
            f"model-{i}",
            f"Q{i}",
            f"A{i}",
            {"idx": str(i)},
            base + timedelta(minutes=i),
        )
        for i in range(3)
    ]
    with UnitOfWorkSqlite(conn) as uow:
        recent = list(uow.chats.list_recent())  # type: ignore[attr-defined]
    ordered_ids = [c.id for c in recent]
    # Expect last inserted (highest timestamp) first
    _assert(
        ordered_ids == ids[::-1],
        f"Ordering mismatch. Expected {ids[::-1]} got {ordered_ids}",
    )
    # Explicitly close the SQLite connection to avoid ResourceWarning
    conn.close()


def test_list_recent_limit() -> None:
    conn = _new_conn()
    now = datetime.now(UTC)
    for i in range(5):
        _add_log(
            conn,
            "openai",
            "gpt-4o",
            f"Question {i}",
            f"Answer {i}",
            {"n": str(i)},
            now + timedelta(seconds=i),
        )
    limit = 3
    with UnitOfWorkSqlite(conn) as uow:
        subset = list(uow.chats.list_recent(limit=limit))  # type: ignore[attr-defined]
    _assert(len(subset) == limit, f"Limit not enforced: got {len(subset)}")
    times = [c.created_at for c in subset]
    _assert(
        times == sorted(times, reverse=True),
        f"Subset not in descending order by created_at: {times}",
    )
    # Explicitly close the SQLite connection to avoid ResourceWarning
    conn.close()


def test_get_nonexistent_returns_none() -> None:
    conn = _new_conn()
    with UnitOfWorkSqlite(conn) as uow:
        missing = uow.chats.get(9999)  # type: ignore[attr-defined]
    _assert(missing is None, f"Expected None for missing id, got {missing}")
    # Explicitly close the SQLite connection to avoid ResourceWarning
    conn.close()
