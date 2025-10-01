"""UnitOfWorkSqlite commit and rollback semantics tests."""
from __future__ import annotations

import pytest

from crux_providers.persistence.sqlite.repos import UnitOfWorkSqlite


def test_unit_of_work_commit_and_rollback(conn):
    """Verify context manager commits on success and rolls back on exception."""
    # Commit path
    with UnitOfWorkSqlite(conn) as uow:
        uow.keys.set_api_key("openai", "sk-1")
    cur = conn.execute("SELECT COUNT(*) FROM keys")
    assert cur.fetchone()[0] == 1  # nosec B101

    # Rollback path
    with pytest.raises(RuntimeError):
        with UnitOfWorkSqlite(conn) as uow:
            uow.keys.set_api_key("anthropic", "ak-1")
            raise RuntimeError("force rollback")
    cur = conn.execute("SELECT COUNT(*) FROM keys")
    # original row only (rollback removed second insert)
    assert cur.fetchone()[0] == 1  # nosec B101
