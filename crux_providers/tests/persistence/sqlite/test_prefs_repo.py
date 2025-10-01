"""Preferences repository roundtrip and overwrite tests."""
from __future__ import annotations

from crux_providers.persistence.sqlite.repos import PrefsRepoSqlite


def test_prefs_repo_roundtrip(conn):
    """Ensure prefs can be set, fetched, and overwritten predictably."""
    prefs = PrefsRepoSqlite(conn)
    out = prefs.get_prefs()
    assert out.values == {}  # nosec B101

    prefs.set_prefs({"theme": "dark", "max_tokens": "1024"})
    out2 = prefs.get_prefs()
    assert out2.values["theme"] == "dark"  # nosec B101

    prefs.set_prefs({"theme": "light"})
    out3 = prefs.get_prefs()
    assert out3.values == {"theme": "light"}  # nosec B101
