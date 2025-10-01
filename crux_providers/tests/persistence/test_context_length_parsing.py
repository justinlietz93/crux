"""Edge-case tests for context length parsing (Issue #40).

Validates that `_parse_context_length` accepts various human-readable
notations and rejects invalid or ambiguous ones by returning None.

The grammar under test (see model_registry_store._parse_context_length docstring):
  - Plain integers ("4096")
  - Comma separated thousands ("4,096")
  - Kilo suffix ("8k", "8K") = value * 1000
  - Decimal kilo suffix ("1.5k" -> 1500, "0.75K" -> 750)
  - Optional trailing ' tokens' label ("8k tokens")
  - Reject zero/negative, empty, malformed decimals, unknown suffixes

These tests ensure future refactors do not regress parsing behavior for
model registry ingestion normalization.
"""

from __future__ import annotations

import os
import tempfile
from typing import Any, Optional

from crux_providers.service import db as svcdb
from crux_providers.persistence.sqlite import model_registry_store as mstore
from crux_providers.persistence.sqlite.model_registry_store import _parse_context_length  # type: ignore


def _roundtrip_context(value: Any) -> Optional[int]:
    """Helper invoking the parser directly.

    Returns the integer context length or None.
    """
    return _parse_context_length(value)


def test_plain_integer():
    if _roundtrip_context(4096) != 4096:
        raise AssertionError("Expected 4096 for integer input")
    if _roundtrip_context("8192") != 8192:
        raise AssertionError("Expected 8192 for string integer input")


def test_commas_and_tokens_label():
    if _roundtrip_context("4,096") != 4096:
        raise AssertionError("Comma thousands parsing failed")
    if _roundtrip_context("32,000 tokens") != 32000:
        raise AssertionError("Comma thousands with tokens label parsing failed")


def test_kilo_suffix_whole_and_decimal():
    if _roundtrip_context("8k") != 8000:
        raise AssertionError("k suffix parsing failed (lowercase)")
    if _roundtrip_context("8K") != 8000:
        raise AssertionError("k suffix parsing failed (uppercase)")
    if _roundtrip_context("1.5k") != 1500:
        raise AssertionError("decimal k parsing failed (1.5k)")
    if _roundtrip_context("0.75K") != 750:
        raise AssertionError("decimal k parsing failed (0.75K)")
    if _roundtrip_context("8k tokens") != 8000:
        raise AssertionError("k suffix with tokens label parsing failed")


def test_reject_zero_negative_and_malformed():
    if _roundtrip_context(0) is not None:
        raise AssertionError("Zero should be rejected")
    if _roundtrip_context(-1) is not None:
        raise AssertionError("Negative int should be rejected")
    if _roundtrip_context("-5") is not None:
        raise AssertionError("Negative string should be rejected")
    if _roundtrip_context("k") is not None:
        raise AssertionError("Standalone 'k' should be rejected")
    if _roundtrip_context("1.2.3k") is not None:
        raise AssertionError("Malformed decimal should be rejected")
    if _roundtrip_context("8m") is not None:  # unsupported magnitude suffix
        raise AssertionError("Unsupported suffix 'm' should be rejected")
    if _roundtrip_context("") is not None:
        raise AssertionError("Empty string should be rejected")
    if _roundtrip_context(None) is not None:
        raise AssertionError("None should be rejected")


def test_integration_with_model_save_and_load():
    """Ensure parsed values persist through snapshot save/load cycle."""
    svcdb._reset_db_for_tests()  # type: ignore
    tmpdir = tempfile.TemporaryDirectory()
    db_path = os.path.join(tmpdir.name, "providers.db")
    vault_dir = tmpdir.name
    svcdb.init_db(db_path, vault_dir)

    # Use diverse representations
    models = [
        {"id": "a", "context_length": "4,096"},
        {"id": "b", "context_length": "1.5k"},
        {"id": "c", "context_length": "8k tokens"},
        {"id": "d", "context_length": "0"},  # rejected -> None
        {"id": "e", "context_length": "bad"},  # rejected -> None
    ]
    mstore.save_models_snapshot("parse-test", models)
    snap = mstore.load_models_snapshot("parse-test")
    # Build dict for easy lookup
    ctx_map = {m["id"]: m.get("context_length") for m in snap.get("models", [])}
    if ctx_map["a"] != 4096:
        raise AssertionError("Integration: expected 4096 for 'a'")
    if ctx_map["b"] != 1500:
        raise AssertionError("Integration: expected 1500 for 'b'")
    if ctx_map["c"] != 8000:
        raise AssertionError("Integration: expected 8000 for 'c'")
    if ctx_map["d"] is not None:
        raise AssertionError("Integration: expected None for rejected '0'")
    if ctx_map["e"] is not None:
        raise AssertionError("Integration: expected None for 'bad'")
