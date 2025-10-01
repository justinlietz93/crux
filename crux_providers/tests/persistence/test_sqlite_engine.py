"""Contract tests for SQLite engine helpers and ChatLog repository.

These tests validate:
- get_db_path user path expansion
- db_session initializes schema and applies PRAGMAs
- ChatLogRepoSqlite basic add/get/list behavior
"""

from __future__ import annotations
from pathlib import Path
from typing import List

from crux_providers.persistence.sqlite.engine import db_session, get_db_path
from crux_providers.persistence.sqlite.chatlog_repo import ChatLogRepoSqlite
from crux_providers.persistence.interfaces.repos import ChatLog
from datetime import datetime, timezone, timedelta


def test_get_db_path_expands_user() -> None:
    """Ensure tildes in user-specified paths are expanded to absolute paths."""
    raw = str(Path("~/.local/share/providers.db"))
    expanded = get_db_path(raw)
    assert "~" not in str(expanded)  # nosec B101 - pytest assertion in tests
    assert expanded.is_absolute()  # nosec B101 - pytest assertion in tests


def test_db_session_initializes_schema_and_pragmas(tmp_path: Path) -> None:
    """db_session should create required tables and set PRAGMA defaults."""
    db_file = tmp_path / "providers.db"
    with db_session(str(db_file)) as conn:
        # tables exist
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        for name in ("keys", "prefs", "chat_logs", "metrics"):
            assert name in tables  # nosec B101 - pytest assertion in tests
        # pragmas applied
        journal_mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        assert str(journal_mode).lower() == "wal"  # nosec B101 - pytest assertion in tests
        busy_timeout = conn.execute("PRAGMA busy_timeout").fetchone()[0]
        assert isinstance(busy_timeout, int) and busy_timeout > 0  # nosec B101 - pytest assertion in tests


def test_chatlog_repo_add_get_list(tmp_path: Path) -> None:
    """ChatLog repository should insert, retrieve, and list logs reliably."""
    db_file = tmp_path / "providers.db"
    with db_session(str(db_file)) as conn:
        repo = ChatLogRepoSqlite(conn)
        now = datetime.now(tz=timezone.utc)
        # insert two rows with different timestamps to test ordering
        id1 = repo.add(
            ChatLog(
                id=None,
                provider="openai",
                model="gpt-5",
                role_user="Hello",
                role_assistant="Hi there",
                metadata={"run": "t1"},
                created_at=now - timedelta(seconds=5),
            )
        )
        assert isinstance(id1, int) and id1 > 0  # nosec B101 - pytest assertion in tests
        id2 = repo.add(
            ChatLog(
                id=None,
                provider="openai",
                model="gpt-5",
                role_user="How are you?",
                role_assistant="Doing great!",
                metadata={"run": "t2"},
                created_at=now,
            )
        )
        assert id2 > id1  # nosec B101 - pytest assertion in tests
        # get
        item = repo.get(id2)
        assert item is not None  # nosec B101 - pytest assertion in tests
        assert item.id == id2  # nosec B101 - pytest assertion in tests
        assert item.metadata.get("run") == "t2"  # nosec B101 - pytest assertion in tests
        # list_recent ordered by created_at desc
        recent: List[ChatLog] = list(repo.list_recent(limit=10))
        assert len(recent) >= 2  # nosec B101 - pytest assertion in tests
        assert recent[0].id == id2  # nosec B101 - pytest assertion in tests
        assert recent[1].id == id1  # nosec B101 - pytest assertion in tests
