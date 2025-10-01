from __future__ import annotations

import importlib
import sys
from datetime import UTC, datetime, timezone
from pathlib import Path

from crux_providers.tests.utils import assert_true

_assert = assert_true


# Dynamically import repos module to access internal helper.
_CUR = Path(__file__).resolve()
for parent in _CUR.parents:
    if (parent / "productivity_tools").is_dir():
        if str(parent) not in sys.path:
            sys.path.insert(0, str(parent))
        break

repos_mod = importlib.import_module("crux_providers.persistence.sqlite.repos")  # type: ignore  # pragma: no cover
_parse_created_at = getattr(repos_mod, "_parse_created_at")  # internal helper


def test_iso_string_parsed_to_aware() -> None:
    iso = "2025-09-17T12:34:56.789+00:00"
    dt = _parse_created_at(iso)
    _assert(dt.tzinfo is not None, f"Expected tz-aware datetime: {dt}")
    # Allow normalized zero-padded microseconds (Python may render 789000)
    normalized_input = iso.replace(".789+", ".789000+")
    _assert(
        dt.isoformat() in {iso, normalized_input},
        f"Round-trip mismatch: {dt.isoformat()} vs {iso}",
    )


def test_naive_datetime_coerced_to_utc() -> None:
    naive = datetime(2025, 9, 17, 12, 0, 0)
    dt = _parse_created_at(naive)
    _assert(dt.tzinfo is not None and dt.tzinfo.utcoffset(dt) == timezone.utc.utcoffset(dt), f"Naive not coerced to UTC: {dt}")


def test_malformed_string_falls_back_to_epoch() -> None:
    malformed = "not-a-timestamp"
    dt = _parse_created_at(malformed)
    _assert(dt == datetime.fromtimestamp(0, tz=UTC), f"Malformed did not fallback to epoch: {dt}")


def test_already_aware_preserved() -> None:
    aware = datetime(2025, 9, 17, 13, 0, 0, tzinfo=timezone.utc)
    dt = _parse_created_at(aware)
    _assert(dt is aware or dt == aware, f"Aware datetime altered: {dt} vs {aware}")


def test_iso_without_timezone_treated_as_utc() -> None:
    iso_naive = "2025-09-17T10:00:00"
    dt = _parse_created_at(iso_naive)
    _assert(dt.tzinfo is not None, f"Expected tz assignment for naive ISO: {dt}")
    _assert(dt.hour == 10, f"Hour mismatch: {dt}")
