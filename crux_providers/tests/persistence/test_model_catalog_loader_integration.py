"""Integration tests for YAML-backed model catalog loader and SQLite registry.

These tests validate that:

- The `load_model_catalog` service reads provider-centric YAML catalogs
  from ``crux_providers/catalog/providers``.
- Provider snapshots are materialized into the SQLite-backed model registry
  via the existing persistence helpers in
  `persistence.sqlite.model_registry_store`.
- Core production providers (OpenAI, Anthropic, Gemini, DeepSeek, Mistral,
  Groq, OpenRouter, Ollama, xAI) appear in the registry after loading.
- At least one XAI model (e.g. ``grok-2``) is correctly populated with
  Void-specific capability fields such as ``tool_format`` and
  ``system_message``.

These tests advance ADR-002 by asserting that the YAML catalog is a
first-class source of truth and that the registry surfaces it correctly.
"""

from __future__ import annotations

import os
import tempfile
from typing import Any, Dict, List, Set

import pytest

from crux_providers.service import db as svcdb
from crux_providers.service.model_catalog_loader import load_model_catalog
from crux_providers.persistence.sqlite import model_registry_store as store


def _init_temp_db() -> tempfile.TemporaryDirectory:
    """Initialize an isolated SQLite DB for model registry tests.

    This helper mirrors the pattern used in
    `test_model_registry_store.py`, but exercises the loader +
    persistence path instead of writing rows directly.

    Returns
    -------
    TemporaryDirectory
        A temporary directory whose lifetime is managed by the caller.
    """
    # Reset any existing global DB state used by the service layer.
    svcdb._reset_db_for_tests()  # type: ignore[attr-defined] - test-only internal helper

    # On Windows, SQLite may hold an open handle on the DB file when tests
    # attempt to clean up the temporary directory. Ignore cleanup errors to
    # avoid spurious PermissionError on rmtree while keeping isolation.
    tmpdir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
    db_path = os.path.join(tmpdir.name, "providers.db")
    vault_dir = tmpdir.name
    svcdb.init_db(db_path, vault_dir)
    return tmpdir


@pytest.mark.integration
def test_load_model_catalog_seeds_core_providers() -> None:
    """`load_model_catalog` must seed snapshots for core production providers.

    After loading the catalog into an isolated SQLite database, the
    `list_providers` helper should report at least the expected set of
    production providers that have YAML catalogs defined.
    """
    tmpdir = _init_temp_db()
    try:
        # Act: load all YAML catalogs into the fresh registry.
        load_model_catalog()

        providers: Set[str] = set(store.list_providers())
        # Sanity: ensure some providers exist at all.
        assert providers, "Expected non-empty provider set after catalog load"

        # Core production providers with YAML catalogs.
        expected: Set[str] = {
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
        missing = expected.difference(providers)
        assert not missing, f"Missing providers in registry after catalog load: {missing}"
    finally:
        tmpdir.cleanup()


@pytest.mark.integration
def test_load_model_catalog_populates_xai_models_with_capabilities() -> None:
    """XAI catalog entries must materialize into the registry with capabilities.

    This test specifically validates that the `xai.yaml` catalog is
    wired through:

    1. `load_model_catalog` parses the YAML document.
    2. A provider snapshot is stored under provider id ``"xai"``.
    3. At least one known model (``grok-2``) is present and has
       Void-specific capability fields such as ``tool_format`` and
       ``system_message`` populated as expected.
    """
    tmpdir = _init_temp_db()
    try:
        load_model_catalog()

        snapshot: Dict[str, Any] = store.load_models_snapshot("xai")
        assert snapshot, "Expected non-empty snapshot for provider 'xai'"

        models: List[Dict[str, Any]] = snapshot.get("models") or []
        assert isinstance(models, list) and models, "Expected at least one XAI model"

        # We know `grok-2` is defined in `xai.yaml`; treat its presence as a
        # regression guard for catalog wiring. If the catalog evolves, this
        # assertion can be updated alongside the YAML.
        grok2_list = [m for m in models if m.get("id") == "grok-2"]
        assert (
            grok2_list
        ), "Expected `grok-2` to be present in XAI snapshot (from xai.yaml catalog)"
        grok2 = grok2_list[0]

        caps: Dict[str, Any] = grok2.get("capabilities") or {}
        assert isinstance(
            caps, dict
        ), "Capabilities for `grok-2` must be a mapping after round-trip"

        # Check a small, stable subset of Void-specific fields rather than
        # over-specifying the entire capability blob.
        assert (
            caps.get("tool_format") == "openai"
        ), "Expected `tool_format: openai` for `grok-2`"
        assert (
            caps.get("system_message") == "system-role"
        ), "Expected `system_message: system-role` for `grok-2`"

        ctx = caps.get("context_window") or grok2.get("context_length")
        assert isinstance(ctx, int) and ctx > 0, "Context window for `grok-2` must be positive"
    finally:
        tmpdir.cleanup()