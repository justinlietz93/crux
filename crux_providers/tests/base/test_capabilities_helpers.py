"""Unit tests for base capabilities helpers (normalize, merge, attempt, observed)."""

from __future__ import annotations

from pathlib import Path

from crux_providers.base.capabilities import (
    apply_void_enrichment,
    load_observed,
    merge_capabilities,
    normalize_modalities,
    record_observation,
    should_attempt,
)
from crux_providers.tests.utils import assert_true
from crux_providers.service import db as _db


def test_normalize_modalities_basic() -> None:
    """Normalize mixed-case modalities and infer implied flags (image→vision)."""
    caps = normalize_modalities(["Text", "image", "AUDIO"])
    assert_true(caps.get("text") is True, "text should normalize true")
    assert_true(caps.get("image") is True, "image should normalize true")
    assert_true(caps.get("vision") is True, "image implies vision")
    assert_true(caps.get("audio") is True, "audio should normalize true")


def test_merge_capabilities_prefers_truthy() -> None:
    """Merging favors truthy values and preserves existing truths."""
    old = {"vision": False, "json_output": True}
    new = {"vision": True, "audio": True}
    merged = merge_capabilities(old, new)
    assert_true(merged.get("vision") is True, "new truth should override false")
    assert_true(merged.get("json_output") is True, "truth preserved from old")
    assert_true(merged.get("audio") is True, "new truth added")


def test_should_attempt_permissive_unknown() -> None:
    """Unknown caps are permissive; explicit False forbids attempts."""
    assert_true(should_attempt("vision", None) is True, "None permissive")
    assert_true(should_attempt("vision", {}) is True, "empty permissive")
    assert_true(should_attempt("vision", {"vision": True}) is True, "truth ok")
    assert_true(should_attempt("vision", {"vision": False}) is False, "false forbids")


def test_observed_round_trip(tmp_path: Path, monkeypatch) -> None:
    """Persist observations in SQLite and ensure non-destructive updates."""
    provider = "openai"
    root = tmp_path / "providers"
    root.mkdir(parents=True, exist_ok=True)

    # Initialize a temporary SQLite DB in the tmp directory
    db_path = str(tmp_path / "providers.db")
    _db.init_db(db_path, str(root))

    # Initially empty (DB-backed)
    assert_true(load_observed(provider) == {}, "observed starts empty")

    # Record a True observation and verify persistence
    record_observation(provider, "m1", "vision", True)
    data = load_observed(provider)
    assert_true(data.get("m1", {}).get("vision") is True, "vision persisted true")

    # Record a False observation for a different feature; ensure non-destructive
    record_observation(provider, "m1", "audio", False)
    data2 = load_observed(provider)
    assert_true(data2.get("m1", {}).get("vision") is True, "vision remains true")
    assert_true(data2.get("m1", {}).get("audio") is False, "audio set false")

    # DB-backed: ensure mapping reflects both flags
    data3 = load_observed(provider)
    assert_true(data3.get("m1", {}).get("vision") is True, "vision true retained")
    assert_true(data3.get("m1", {}).get("audio") is False, "audio false retained")


def test_apply_void_enrichment_adds_defaults_for_known_provider() -> None:
    """Void enrichment should add baseline tool_format/system_message for known providers."""
    caps = {}
    enriched = apply_void_enrichment("openai", "gpt-test", caps)
    assert_true(
        enriched.get("tool_format") is not None,
        f"tool_format default missing for openai: {enriched}",
    )
    assert_true(
        enriched.get("system_message") is not None,
        f"system_message default missing for openai: {enriched}",
    )


def test_apply_void_enrichment_preserves_existing_caps() -> None:
    """Existing capability flags must not be overwritten by Void enrichment."""
    caps = {
        "tool_format": "custom",
        "system_message": "custom-system",
    }
    enriched = apply_void_enrichment("openai", "gpt-test", caps)
    assert_true(
        enriched.get("tool_format") == "custom",
        f"existing tool_format should win over defaults: {enriched}",
    )
    assert_true(
        enriched.get("system_message") == "custom-system",
        f"existing system_message should win over defaults: {enriched}",
    )
