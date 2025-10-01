"""Test that naive datetime insertion raises ValueError via explicit adapter.

Ensures UTC enforcement policy remains intact and prevents silent storage of local times.
"""
from __future__ import annotations

from datetime import datetime
import pytest

from crux_providers.persistence.sqlite.sqlite_config import create_connection


def test_naive_datetime_insertion_raises(tmp_path):
    conn = create_connection(str(tmp_path / "naive.sqlite"))
    with conn:
        conn.execute("CREATE TABLE sample (id INTEGER PRIMARY KEY, created TIMESTAMP)")
        naive = datetime.now()  # No tzinfo
        with pytest.raises(ValueError):
            conn.execute("INSERT INTO sample (created) VALUES (?)", (naive,))
    conn.close()
