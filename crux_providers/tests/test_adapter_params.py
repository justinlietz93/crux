"""Tests for AdapterParams DTO and ProviderFactory parameter coercion.

Covers:
- Basic creation and `.model_dump()` round-trip of `AdapterParams`.
- `_coerce_params` merge precedence rules (kwargs override params; shallow
    merge for headers/extra).
"""

from __future__ import annotations

from crux_providers.base.dto.adapter_params import AdapterParams
from crux_providers.base.factory import ProviderFactory


def test_adapter_params_round_trip():
    params = AdapterParams(
        provider="openai",
        model="gpt-4o",
        api_key="k",
        base_url="https://api.example.com",
        organization="org",
        timeout_seconds=12.5,
        headers={"X-Trace": "1"},
        extra={"region": "us"},
    )
    dumped = params.model_dump()
    assert dumped["provider"] == "openai"  # nosec B101 - test assertion
    assert dumped["headers"]["X-Trace"] == "1"  # nosec B101 - test assertion


def test_coerce_params_merge_precedence():
    base = AdapterParams(headers={"A": "1"}, extra={"x": 1})
    kwargs = {"headers": {"B": "2"}, "extra": {"x": 2}, "model": "m"}
    merged = ProviderFactory._coerce_params(base, kwargs)
    # kwargs wins on overlapping keys
    assert merged["headers"]["B"] == "2"  # nosec B101 - test assertion
    assert merged["extra"]["x"] == 2  # nosec B101 - test assertion
    # provider field should be stripped before constructor call
    assert "provider" not in merged  # nosec B101 - test assertion
    # kwargs overlay applied last
    assert merged["model"] == "m"  # nosec B101 - test assertion
