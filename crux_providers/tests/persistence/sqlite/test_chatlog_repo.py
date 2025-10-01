"""Chat log repository insertion and recent listing tests."""
from __future__ import annotations

from crux_providers.persistence.sqlite.repos import ChatLogRepoSqlite
from crux_providers.persistence.interfaces.repos import ChatLog


def test_chatlog_repo_add_and_list_recent(conn):
    """Ensure insertion and reverse-chronological listing semantics."""
    chats = ChatLogRepoSqlite(conn)

    logs = [
        ChatLog(
            id=None,
            provider="openai",
            model="gpt-4o-mini",
            role_user="Hi",
            role_assistant="Hello",
            metadata={"seq": 1},
            created_at="2025-01-01 00:00:00",
        ),
        ChatLog(
            id=None,
            provider="openai",
            model="gpt-4o-mini",
            role_user="How are you?",
            role_assistant="Great",
            metadata={"seq": 2},
            created_at="2025-01-01 00:00:01",
        ),
        ChatLog(
            id=None,
            provider="openai",
            model="gpt-4o-mini",
            role_user="Bye",
            role_assistant="Bye!",
            metadata={"seq": 3},
            created_at="2025-01-01 00:00:02",
        ),
    ]
    for l in logs:
        chats.add(l)
    conn.commit()

    recent = list(chats.list_recent(limit=5))
    seqs = [r.metadata["seq"] for r in recent]
    assert seqs == [3, 2, 1]  # reverse chronological  # nosec B101
