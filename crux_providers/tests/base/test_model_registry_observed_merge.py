"""Tests for merging observed capabilities into model registry snapshots.

Validates that ``ModelRegistryRepository`` merges observed capability flags
persisted in SQLite (``observed_capabilities``) into each model's
``capabilities`` field at read time. This test enforces the DB-first policy
by seeding the model snapshot via SQLite instead of JSON files.
"""

from __future__ import annotations

from pathlib import Path

from crux_providers.base.capabilities import record_observation
from crux_providers.base.repositories.model_registry.repository import (
    ModelRegistryRepository,
)
from crux_providers.service import db as _db
from crux_providers.tests.utils import assert_true


def _write_models_db(root: Path, provider: str, models_payload: dict) -> None:
    """Seed a minimal provider snapshot directly into SQLite (DB-first).

    This helper enforces the database-as-source-of-truth policy by persisting
    the provided model list into SQLite without any JSON involvement. The
    database must be initialized before calling this helper.

    Args:
        root: Temporary providers root (used only to construct DB path upstream).
        provider: Provider identifier (e.g., ``"dummy"``).
        models_payload: Mapping containing a ``models`` list of dicts to persist.
    """
    models = models_payload.get("models") or []
    _db.save_models_snapshot(
        provider,
        models,
        fetched_at=None,
        fetched_via="test_seed",
        metadata={},
    )


def _seed_observed_db(provider: str, flags: dict) -> None:
    """Seed observed capabilities into SQLite for a provider."""

    for mid, feats in flags.items():
        for feat, val in feats.items():
            record_observation(provider, mid, feat, bool(val))


def test_repository_applies_observed_capabilities(tmp_path: Path) -> None:
    """Repository must merge observed flags into model capabilities."""

    provider = "dummy"
    models_payload = {
        "models": [
            {
                "id": "m1",
                "name": "Dummy 1",
                "capabilities": {},
            }
        ]
    }
    _db.init_db(str(tmp_path / "providers.db"), str(tmp_path))
    _write_models_db(tmp_path, provider, models_payload)
    _seed_observed_db(
        provider,
        {
            "m1": {
                "json_output": True,
                "structured_streaming": False,
            }
        },
    )

    repo = ModelRegistryRepository(providers_root=tmp_path)
    snap = repo.list_models(provider, refresh=False)
    assert_true(len(snap.models) == 1, "single model present")
    m = snap.models[0]
    assert_true(m.capabilities.get("json_output") is True, "json_output merged true")
    assert_true(
        m.capabilities.get("structured_streaming") is False,
        "structured_streaming merged false",
    )
