from __future__ import annotations

import sqlite3
from typing import Optional

from .engine import create_connection, init_schema
from .repos import UnitOfWorkSqlite


def get_uow(db_path: Optional[str] = None) -> UnitOfWorkSqlite:
    conn: sqlite3.Connection = create_connection(db_path)
    init_schema(conn)
    return UnitOfWorkSqlite(conn)


__all__ = [
    "create_connection",
    "init_schema",
    "UnitOfWorkSqlite",
    "get_uow",
]
