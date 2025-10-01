from __future__ import annotations

import os
from typing import Any, Dict

from crux_providers.service import db as svcdb


def setup_db(tmp_path: str) -> None:
    # Ensure isolation across tests since the module keeps a global connection
    import contextlib

    with contextlib.suppress(Exception):
        svcdb._reset_db_for_tests()
    db_file = os.path.join(tmp_path, "providers.db")
    vault_dir = os.path.join(tmp_path, "vault")
    os.makedirs(vault_dir, exist_ok=True)
    svcdb.init_db(db_file, vault_dir)


def test_keys_roundtrip(tmp_path):
    setup_db(str(tmp_path))
    svcdb.save_keys({"openai": "sk-test"})
    keys = svcdb.load_keys()
    assert keys["openai"] == "sk-test"  # nosec B101 test assertion


def test_save_empty_keys(tmp_path):
    setup_db(str(tmp_path))
    svcdb.save_keys({})  # no-op
    assert svcdb.load_keys() == {}  # nosec B101 test assertion


def test_overwrite_keys(tmp_path):
    setup_db(str(tmp_path))
    svcdb.save_keys({"openai": "sk-test"})
    svcdb.save_keys({"openai": "sk-new"})
    assert svcdb.load_keys()["openai"] == "sk-new"  # nosec B101 test assertion


def test_invalid_provider_names(tmp_path):
    setup_db(str(tmp_path))
    svcdb.save_keys({"": "sk-empty"})  # empty string accepted currently
    svcdb.save_keys({"@invalid!": "sk-special"})
    keys = svcdb.load_keys()
    assert keys[""] == "sk-empty"  # nosec B101 test assertion
    assert keys["@invalid!"] == "sk-special"  # nosec B101 test assertion


def test_prefs_roundtrip(tmp_path):
    setup_db(str(tmp_path))
    prefs_in: Dict[str, Any] = {"default_provider": "openai", "theme": {"mode": "dark"}}
    svcdb.save_prefs(prefs_in)
    prefs_out = svcdb.load_prefs()
    assert prefs_out["default_provider"] == "openai"  # nosec B101 test assertion
    assert prefs_out["theme"]["mode"] == "dark"  # nosec B101 test assertion


def test_prefs_unusual_types(tmp_path):
    setup_db(str(tmp_path))
    prefs_in: Dict[str, Any] = {
        "none_value": None,
        "list_value": [1, 2, 3],
        "number_value": 42,
        "float_value": 3.14,
        "dict_value": {"a": 1, "b": [2, 3]},
    }
    svcdb.save_prefs(prefs_in)
    out = svcdb.load_prefs()
    assert out["none_value"] is None  # nosec B101 test assertion
    assert out["list_value"] == [1, 2, 3]  # nosec B101 test assertion
    assert out["number_value"] == 42  # nosec B101 test assertion
    assert out["float_value"] == 3.14  # nosec B101 test assertion
    assert out["dict_value"] == {"a": 1, "b": [2, 3]}  # nosec B101 test assertion


def test_prefs_update_and_remove(tmp_path):
    setup_db(str(tmp_path))
    svcdb.save_prefs({"default_provider": "openai", "theme": {"mode": "dark"}})
    # Update default_provider
    svcdb.save_prefs({"default_provider": "anthropic"})
    out = svcdb.load_prefs()
    assert out["default_provider"] == "anthropic"  # nosec B101 test assertion
    # True remove using delete_pref
    removed = svcdb.delete_pref("default_provider")
    assert removed is True  # nosec B101 test assertion
    out2 = svcdb.load_prefs()
    assert "default_provider" not in out2  # nosec B101 test assertion
    # Update remaining key
    svcdb.save_prefs({"theme": {"mode": "light"}})
    out3 = svcdb.load_prefs()
    assert out3["theme"]["mode"] == "light"  # nosec B101 test assertion


def test_record_metric(tmp_path):
    setup_db(str(tmp_path))
    svcdb.record_metric(
        provider="openai", model="gpt-4o-mini", duration_ms=123, status="ok"
    )
    # Query directly to ensure insert happened
    conn = svcdb._get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT provider, model, duration_ms, status FROM metrics ORDER BY id DESC LIMIT 1"
    )
    row = cur.fetchone()
    assert row[0] == "openai"  # nosec B101 test assertion
    assert row[1] == "gpt-4o-mini"  # nosec B101 test assertion
    assert row[2] == 123  # nosec B101 test assertion
    assert row[3] == "ok"  # nosec B101 test assertion


def test_record_metric_missing_optional_model(tmp_path):
    setup_db(str(tmp_path))
    # model is nullable per schema
    svcdb.record_metric(provider="openai", model=None, duration_ms=50, status="ok")
    conn = svcdb._get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT provider, model, duration_ms, status FROM metrics ORDER BY id DESC LIMIT 1"
    )
    row = cur.fetchone()
    assert row[0] == "openai"  # nosec B101 test assertion
    assert row[1] is None  # nosec B101 test assertion
    assert row[2] == 50  # nosec B101 test assertion
    assert row[3] == "ok"  # nosec B101 test assertion


def test_record_metric_status_error(tmp_path):
    setup_db(str(tmp_path))
    svcdb.record_metric(
        provider="openai",
        model="gpt-4o-mini",
        duration_ms=200,
        status="error",
        error_type="TimeoutError",
    )
    conn = svcdb._get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT provider, model, duration_ms, status, error_type FROM metrics ORDER BY id DESC LIMIT 1"
    )
    row = cur.fetchone()
    assert row[0] == "openai"  # nosec B101 test assertion
    assert row[1] == "gpt-4o-mini"  # nosec B101 test assertion
    assert row[2] == 200  # nosec B101 test assertion
    assert row[3] == "error"  # nosec B101 test assertion
    assert row[4] == "TimeoutError"  # nosec B101 test assertion


def test_record_metric_negative_duration(tmp_path):
    import pytest

    setup_db(str(tmp_path))
    with pytest.raises(ValueError):
        svcdb.record_metric(
            provider="openai", model="gpt-4o-mini", duration_ms=-10, status="ok"
        )


def test_sqlite_pragmas_and_indexes(tmp_path):
    setup_db(str(tmp_path))
    conn = svcdb._get_conn()
    cur = conn.cursor()
    cur.execute("PRAGMA journal_mode")
    assert cur.fetchone()[0].lower() == "wal"  # nosec B101 test assertion
    cur.execute("PRAGMA busy_timeout")
    assert int(cur.fetchone()[0]) >= 5000  # nosec B101 test assertion
    # indexes exist
    cur.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND name like 'idx_metrics_%'"
    )
    names = {r[0] for r in cur.fetchall()}
    assert {
        "idx_metrics_provider_model",
        "idx_metrics_status",
        "idx_metrics_ts",
    }.issubset(
        names
    )  # nosec B101 test assertion
