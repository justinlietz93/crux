"""
Contract tests for SQLite repository adapters and UnitOfWork behavior.

These tests use an in-memory SQLite database and call `init_schema` to
initialize tables. They validate:
- Prefs round-trip with commit vs rollback
- Keystore provider normalization and deletion
- Metrics aggregate latency computation
- Chat logs basic CRUD and ordering
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone


import pytest

from crux_providers.persistence.sqlite.engine import init_schema
from crux_providers.persistence.sqlite.repos import (
    UnitOfWorkSqlite,
)
from crux_providers.persistence.interfaces.repos import (
    Prefs,
    MetricEntry,
    ChatLog,
)


def _make_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_schema(conn)
    return conn


def test_prefs_commit_and_rollback():
    conn = _make_conn()

    # 1) Default snapshot should be empty values and epoch UTC timestamp
    with UnitOfWorkSqlite(conn) as uow:
        snap = uow.prefs.get_prefs()
        assert isinstance(snap, Prefs)
        assert snap.values == {}
        assert snap.updated_at.tzinfo is not None
        assert snap.updated_at <= datetime.now(timezone.utc)

    # 2) Commit a preference change
    with UnitOfWorkSqlite(conn) as uow:
        uow.prefs.set_prefs({"theme": "dark", "page_size": "50"})
        # commit happens on context exit
    with UnitOfWorkSqlite(conn) as uow:
        snap = uow.prefs.get_prefs()
        assert snap.values == {"theme": "dark", "page_size": "50"}

    # 3) Attempt to change, then rollback via exception
    with pytest.raises(RuntimeError):
        with UnitOfWorkSqlite(conn) as uow:
            uow.prefs.set_prefs({"theme": "light"})
            raise RuntimeError("force rollback")
    with UnitOfWorkSqlite(conn) as uow:
        snap = uow.prefs.get_prefs()
        assert snap.values == {"theme": "dark", "page_size": "50"}
    # Close connection
    conn.close()


def test_keystore_normalization_and_delete():
    conn = _make_conn()

    with UnitOfWorkSqlite(conn) as uow:
        assert uow.keys.get_api_key("OpenAI") is None
        uow.keys.set_api_key("OpenAI", "sk-test")
        # Commit on exit
    with UnitOfWorkSqlite(conn) as uow:
        # Case-insensitive lookup and normalized provider listing
        assert uow.keys.get_api_key("openai") == "sk-test"
        providers = uow.keys.list_providers()
        assert providers == ["openai"]

        # Delete and verify removal
        uow.keys.delete_api_key("OPENAI")
        # Commit on exit
    with UnitOfWorkSqlite(conn) as uow:
        assert uow.keys.get_api_key("openai") is None
        assert uow.keys.list_providers() == []
    # Close connection
    conn.close()


def test_metrics_aggregate_latency():
    conn = _make_conn()

    now = datetime.now(timezone.utc)
    entries = [
        MetricEntry("openai", "gpt-4o", 100, 10, 20, True, None, now),
        MetricEntry("openai", "gpt-4o", 200, 12, 22, True, None, now),
        MetricEntry("openai", "gpt-4o-mini", 300, 8, 18, False, "timeout", now),
        MetricEntry("anthropic", "claude-3", 400, 15, 25, True, None, now),
    ]

    with UnitOfWorkSqlite(conn) as uow:
        for e in entries:
            uow.metrics.add_metric(e)
        # commit on exit

    with UnitOfWorkSqlite(conn) as uow:
        count, avg = uow.metrics.aggregate_latency("openai")
        assert count == 3
        assert avg in (200, 199)  # integer average (floor/truncate) allowed

        count_m, avg_m = uow.metrics.aggregate_latency("openai", model="gpt-4o")
        assert count_m == 2
        assert avg_m in (150, 149)

        # Check recent errors yields the failed entry
        errs = list(uow.metrics.recent_errors(limit=5))
        assert any(e.success is False for e in errs)
    # Close connection
    conn.close()


def test_chatlog_add_get_list_recent():
    conn = _make_conn()
    now = datetime.now(timezone.utc)

    log = ChatLog(
        id=None,
        provider="openai",
        model="gpt-4o",
        role_user="Hello",
        role_assistant="Hi!",
        metadata={"session": "abc123"},
        created_at=now,
    )

    with UnitOfWorkSqlite(conn) as uow:
        new_id = uow.chats.add(log)
        assert isinstance(new_id, int)
        # commit on exit

    with UnitOfWorkSqlite(conn) as uow:
        fetched = uow.chats.get(new_id)
        assert fetched is not None
        assert fetched.id == new_id
        assert fetched.provider == "openai"
        assert fetched.model == "gpt-4o"
        assert fetched.role_user == "Hello"
        assert fetched.role_assistant == "Hi!"
        assert fetched.metadata == {"session": "abc123"}
        assert fetched.created_at.tzinfo is not None

        recent = list(uow.chats.list_recent(limit=10))
        assert any(c.id == new_id for c in recent)
    # Close connection
    conn.close()
