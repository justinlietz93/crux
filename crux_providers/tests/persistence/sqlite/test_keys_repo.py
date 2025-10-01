"""Keys repository CRUD and provider listing tests."""
from __future__ import annotations

from typing import List

from crux_providers.persistence.sqlite.repos import KeyStoreRepoSqlite


def test_keys_repo_crud(conn):
    """Validate CRUD semantics and provider normalization/sorting."""
    keys = KeyStoreRepoSqlite(conn)

    assert keys.get_api_key("openai") is None  # nosec B101 test assertion
    keys.set_api_key("openai", "sk-1")
    assert keys.get_api_key("openai") == "sk-1"  # nosec B101 test assertion
    keys.set_api_key("openai", "sk-2")  # overwrite
    assert keys.get_api_key("openai") == "sk-2"  # nosec B101 test assertion
    keys.set_api_key("Anthropic", "ak-1")  # case insensitivity
    providers: List[str] = keys.list_providers()
    assert providers == ["anthropic", "openai"]  # sorted  # nosec B101
    keys.delete_api_key("openai")
    assert keys.get_api_key("openai") is None  # nosec B101 test assertion
