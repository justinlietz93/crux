"""
Unit tests for helper utilities in providers package.

Covers:
- _safe_format: resilient formatting without KeyError; preserves unknown placeholders; handles escaped braces.
- _attempt_json_repair: removes code fences, trims to JSON, drops trailing commas, balances brackets/braces/quotes.
"""
from __future__ import annotations

import json
import pytest

from crux_providers import _safe_format, _attempt_json_repair  # type: ignore


def test_safe_format_basic_and_missing_keys():
    tpl = "Hello {name}, today is {day}."
    ctx = {"name": "Ada"}
    out = _safe_format(tpl, ctx)
    assert out == "Hello Ada, today is {day}."


def test_safe_format_escaped_braces():
    tpl = "Value: {{ {key} }}"
    ctx = {"key": 42}
    out = _safe_format(tpl, ctx)
    # Escaped braces become single braces; key replaced
    assert out == "Value: { 42 }"


@pytest.mark.parametrize(
    "raw, expect_json",
    [
        ("```json\n{\n  \"a\": 1,\n}\n```", {"a": 1}),
        ("noise before {\n \"b\": [1,2,],\n", {"b": [1, 2]}),
        ("[ {\"c\": \"x\" }", [{"c": "x"}]),
        ("{\"d\": \"unbalanced quotes }", {"d": "unbalanced quotes "}),
    ],
)
def test_attempt_json_repair_makes_json_loads_possible(raw: str, expect_json):
    repaired = _attempt_json_repair(raw)
    loaded = json.loads(repaired)
    assert loaded == expect_json
