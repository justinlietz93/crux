"""Shared helper functions for SQLite repository adapters.

This module centralizes common parsing and row-to-DTO conversion helpers used
by the SQLite repositories. Keeping these utilities in a single place avoids
duplication across repository modules while maintaining small, focused files.

Note: All timestamps are normalized to timezone-aware UTC ``datetime`` objects
on read to ensure consistent semantics and to avoid reliance on sqlite's
deprecated default datetime adapter.
"""

from __future__ import annotations

from contextlib import suppress
import json
from datetime import datetime, timezone
from typing import Any

from ..interfaces.repos import ChatLog, MetricEntry


def _parse_created_at(raw: Any) -> datetime:
    """Parse a stored timestamp into an aware UTC ``datetime``.

    Strategy:
    - If ``raw`` is already a ``datetime``: ensure tz-aware (assume UTC if naive).
    - If ``raw`` is a string: attempt ISO8601 parse, coercing naive to UTC.
    - On malformed input: return epoch UTC for defensive behavior.

    Parameters
    ----------
    raw:
        Value retrieved from SQLite, typically an ISO8601 string or datetime.

    Returns
    -------
    datetime
        A timezone-aware UTC datetime object.
    """
    if isinstance(raw, datetime):
        return raw if raw.tzinfo else raw.replace(tzinfo=timezone.utc)
    if isinstance(raw, str):
        with suppress(ValueError, TypeError):
            dt = datetime.fromisoformat(raw)
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    return datetime.fromtimestamp(0, tz=timezone.utc)


def _metric_from_row(r: Any) -> MetricEntry:
    """Convert a metrics row into a ``MetricEntry`` DTO.

    Parameters
    ----------
    r:
        Sequence matching the metrics SELECT column order.

    Returns
    -------
    MetricEntry
        Typed DTO suitable for use by callers.
    """
    return MetricEntry(
        provider=r[0],
        model=r[1],
        latency_ms=int(r[2]),
        tokens_prompt=int(r[3]) if r[3] is not None else None,
        tokens_completion=int(r[4]) if r[4] is not None else None,
        success=bool(r[5]),
        error_code=r[6],
        created_at=_parse_created_at(r[7]),
    )


def _chatlog_from_row(r: Any) -> ChatLog:
    """Convert a chat_logs row into a ``ChatLog`` DTO.

    Parameters
    ----------
    r:
        Sequence matching the chat_logs SELECT column order.

    Returns
    -------
    ChatLog
        Typed DTO representing a persisted chat transcript.
    """
    return ChatLog(
        id=int(r[0]),
        provider=r[1],
        model=r[2],
        role_user=r[3],
        role_assistant=r[4],
        metadata=json.loads(r[5]) if r[5] else {},
        created_at=_parse_created_at(r[6]),
    )
