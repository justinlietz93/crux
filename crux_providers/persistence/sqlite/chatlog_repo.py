"""SQLite-backed implementation of ``IChatLogRepo``.

Persists and retrieves chat transcripts with ISO8601 timestamps (UTC assumed
for naive values). All writes defer transaction commit to the Unit of Work.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Iterable, Optional

from ..interfaces.repos import ChatLog, IChatLogRepo
from .helpers import _chatlog_from_row


class ChatLogRepoSqlite(IChatLogRepo):
    """SQLite-backed chat transcript repository.

    Provides insertion, retrieval, and listing of chat transcripts. Timestamps
    are normalized to ISO8601 strings on write to ensure explicit semantics.
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def add(self, log: ChatLog) -> int:
        """Insert a chat log and return its primary key.

        Stores ``created_at`` as an ISO8601 string (UTC-assumed if naive) to
        eliminate reliance on sqlite's deprecated datetime adapter.
        """
        created_at = log.created_at
        if isinstance(created_at, datetime) and created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        created_at_str = created_at.isoformat() if isinstance(created_at, datetime) else str(created_at)
        cur = self.conn.execute(
            """
            INSERT INTO chat_logs(provider, model, role_user, role_assistant, metadata_json, created_at)
            VALUES(?, ?, ?, ?, ?, ?)
            """,
            (
                log.provider,
                log.model,
                log.role_user,
                log.role_assistant,
                json.dumps(log.metadata, ensure_ascii=False),
                created_at_str,
            ),
        )
        return int(cur.lastrowid)

    def get(self, chat_id: int) -> Optional[ChatLog]:
        """Return chat log by primary key or ``None`` if missing."""
        cur = self.conn.execute(
            "SELECT id, provider, model, role_user, role_assistant, metadata_json, created_at FROM chat_logs WHERE id = ?",
            (chat_id,),
        )
        r = cur.fetchone()
        return _chatlog_from_row(r) if r else None

    def list_recent(self, limit: int = 100) -> Iterable[ChatLog]:
        """Yield most recent chat logs (descending chronological) up to limit."""
        cur = self.conn.execute(
            "SELECT id, provider, model, role_user, role_assistant, metadata_json, created_at FROM chat_logs ORDER BY created_at DESC LIMIT ?",
            (limit,),
        )
        for r in cur.fetchall():
            yield _chatlog_from_row(r)
