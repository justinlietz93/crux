"""Smoke tests for relocated model registry store (Issue #39).

Ensures that saving and loading a model snapshot through the new
`persistence.sqlite.model_registry_store` path works and returns the expected
shape. Uses in-memory temporary DB via test fixture resetting service db.
"""

from __future__ import annotations

import os
import tempfile
from typing import Any, Dict

from crux_providers.service import db as svcdb
from crux_providers.persistence.sqlite import model_registry_store as store


def test_save_and_load_snapshot_roundtrip():
    # Reset DB state then initialize a temp path
    svcdb._reset_db_for_tests()  # type: ignore  # test-only internal helper
    tmpdir = tempfile.TemporaryDirectory()
    db_path = os.path.join(tmpdir.name, "providers.db")
    vault_dir = tmpdir.name
    svcdb.init_db(db_path, vault_dir)

    models = [
        {"id": "model-alpha", "name": "Alpha", "context_length": 8192, "capabilities": {"stream": True}},
        "raw-string-model",
    ]
    store.save_models_snapshot(
        "unit-test-provider",
        models,
        fetched_via="api",
        metadata={"source": "test"},
    )
    snap: Dict[str, Any] = store.load_models_snapshot("unit-test-provider")
    if not snap:
        raise AssertionError("Expected non-empty snapshot after save")
    if snap.get("provider") != "unit-test-provider":
        raise AssertionError("Provider field mismatch in snapshot")
    model_list = snap.get("models")
    if not isinstance(model_list, list) or len(model_list) != 2:
        raise AssertionError("Expected two models round-tripped")
    # Ensure normalization applied to raw string model
    raw_entry = [m for m in model_list if m["id"] == "raw-string-model"]
    if not raw_entry:
        raise AssertionError("Raw string model not normalized into snapshot")
