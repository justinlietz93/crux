"""Integration tests for `/api/models` and `/api/providers` endpoints.

These tests validate that:

- The HTTP surface for the model registry (`/api/providers`, `/api/models`)
  reflects the same SQLite-backed source of truth used by the IDE.
- Core catalog-backed providers are present in `/api/providers`.
- `/api/models` returns well-formed snapshots with:
  - Matching `provider` id.
  - Non-empty `models` lists for core providers.
  - No duplicate `id` values per provider.
  - Model entries shaped compatibly with the IDE's expectations
    (fields like `id`, `name`, `capabilities`, `context_length`).

The tests deliberately re-use the temporary DB initialization helper from
`test_model_catalog_loader_integration` to ensure the HTTP APIs see the same
SQLite state as the lower-level persistence tests.
"""

from __future__ import annotations

from typing import Any, Dict, List, Set

import pytest
from fastapi.testclient import TestClient

from crux_providers.service.app import get_app
from crux_providers.service.model_catalog_loader import load_model_catalog
from crux_providers.tests.persistence.test_model_catalog_loader_integration import (  # type: ignore[attr-defined]
    _init_temp_db,
)


_CORE_PROVIDERS: Set[str] = {
    "openai",
    "anthropic",
    "gemini",
    "deepseek",
    "mistral",
    "groq",
    "openrouter",
    "ollama",
    "xai",
}


@pytest.mark.integration
def test_api_providers_includes_core_catalog_backed_providers() -> None:
    """`/api/providers` should list all core catalog-backed providers.

    After seeding the SQLite registry via `load_model_catalog`, the HTTP
    `/api/providers` endpoint must expose, at minimum, the same set of core
    providers validated by the catalog integration tests. This guards the
    service wiring from silently diverging from the persistence layer.
    """
    tmpdir = _init_temp_db()
    try:
        # Seed registry from YAML catalogs into the isolated DB.
        load_model_catalog()

        client = TestClient(get_app())
        resp = client.get("/api/providers")
        assert resp.status_code == 200, f"Unexpected status: {resp.status_code}"
        payload = resp.json()
        assert payload.get("ok") is True, "Expected ok=True from /api/providers"

        providers = set(payload.get("providers") or [])
        assert providers, "Expected non-empty provider set from /api/providers"

        missing = _CORE_PROVIDERS.difference(providers)
        assert (
            not missing
        ), f"Missing providers in /api/providers response: {sorted(missing)}"
    finally:
        tmpdir.cleanup()


@pytest.mark.integration
def test_api_models_snapshots_are_well_formed_and_de_duplicated() -> None:
    """`/api/models` snapshots must be stable and compatible with IDE expectations.

    For each core catalog-backed provider:

    - `/api/models?provider=...` returns `ok=True` and a snapshot with matching
      `provider` id.
    - The `models` list is non-empty.
    - Model `id` values are unique per provider (no duplicates).
    - Each model entry exposes the minimal shape expected by the IDE:
      - `id`: str
      - `name`: str
      - `capabilities`: dict
      - `context_length`: int | None
    """
    tmpdir = _init_temp_db()
    try:
        load_model_catalog()

        client = TestClient(get_app())

        for provider in sorted(_CORE_PROVIDERS):
            resp = client.get("/api/models", params={"provider": provider, "refresh": False})
            assert (
                resp.status_code == 200
            ), f"Unexpected status for provider {provider!r}: {resp.status_code}"
            payload = resp.json()
            assert payload.get("ok") is True, f"Expected ok=True for provider {provider!r}"

            snapshot: Dict[str, Any] = payload.get("snapshot") or {}
            assert snapshot.get("provider") == provider, (
                f"Snapshot provider mismatch: expected {provider!r}, "
                f"got {snapshot.get('provider')!r}"
            )

            models: List[Dict[str, Any]] = snapshot.get("models") or []
            assert isinstance(
                models, list
            ), f"Expected list of models for provider {provider!r}, got {type(models)!r}"
            assert models, f"Expected at least one model for provider {provider!r}"

            # Ensure model IDs are unique per provider.
            ids = [m.get("id") for m in models]
            assert all(
                isinstance(mid, str) and mid for mid in ids
            ), f"All models for provider {provider!r} must have non-empty string ids"
            assert len(ids) == len(
                set(ids)
            ), f"Duplicate model ids found for provider {provider!r}: {ids}"

            # Basic shape compatibility with IDE expectations.
            for m in models:
                assert "name" in m and isinstance(
                    m["name"], str
                ), f"Model entry for {provider!r} missing string name: {m!r}"

                caps = m.get("capabilities")
                assert isinstance(
                    caps, dict
                ), f"Model capabilities for {provider!r} must be a dict, got {type(caps)!r}"

                # context_length is optional but, when present, should be an int.
                ctx = m.get("context_length")
                if ctx is not None:
                    assert isinstance(
                        ctx, int
                    ), f"context_length for {provider!r} must be int or None, got {type(ctx)!r}"
    finally:
        tmpdir.cleanup()