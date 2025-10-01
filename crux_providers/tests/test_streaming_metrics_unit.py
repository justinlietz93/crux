"""Unit tests for streaming metrics helpers.

Covers apply_token_usage, build_token_usage, and validate_token_usage including
negative values, mismatched totals, and mapping key shape.
"""
from __future__ import annotations

import pytest

from crux_providers.base.streaming import (
    StreamMetrics,
    apply_token_usage,
    build_token_usage,
    validate_token_usage,
)


def test_build_and_apply_token_usage_and_validation_pass():
    metrics = StreamMetrics()
    usage = build_token_usage(3, 7)
    assert usage == {"prompt": 3, "completion": 7, "total": 10}  # nosec B101 - pytest assert in tests
    apply_token_usage(metrics, prompt=3, completion=7)
    ok, reason = validate_token_usage(metrics)
    assert ok is True and reason is None  # nosec B101 - pytest assert in tests


def test_validate_rejects_negative_and_mismatched_total():
    m = StreamMetrics()
    # negative value
    m.prompt_tokens = -1
    ok, reason = validate_token_usage(m)
    assert ok is False and "negative" in (reason or "")  # nosec B101 - pytest assert in tests

    # mismatched total
    m = StreamMetrics()
    apply_token_usage(m, prompt=2, completion=2, total=5)
    ok, reason = validate_token_usage(m)
    assert ok is False and "mismatch" in (reason or "")  # nosec B101 - pytest assert in tests


def test_validate_tokens_mapping_shape_and_raise_on_error():
    m = StreamMetrics()
    apply_token_usage(m, prompt=1, completion=1)  # sets tokens mapping
    # tamper with mapping keys
    m.tokens = {"p": 1, "c": 1, "t": 2}
    ok, reason = validate_token_usage(m)
    assert ok is False and "keys mismatch" in (reason or "")  # nosec B101 - pytest assert in tests

    # raise path
    m = StreamMetrics()
    m.total_tokens = -5
    with pytest.raises(ValueError):
        validate_token_usage(m, raise_on_error=True)
