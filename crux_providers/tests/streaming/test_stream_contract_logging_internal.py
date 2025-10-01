"""Logging contract test: INTERNAL start-shape error.

Validates finalize-phase structured log when starter returns a mapping
missing the required 'stream' key. Ensures:
- Finalize log contains error_code "internal".
- emitted == False and emitted_count == 0.
- phase == "finalize".
"""
from __future__ import annotations

import json
from typing import Any

from crux_providers.base.streaming import BaseStreamingAdapter
from crux_providers.base.logging import LogContext, get_logger


def _starter_invalid_mapping():  # pragma: no cover - executed via test
    return {"request_id": "abc-123"}  # missing 'stream'


def _translator(_: object):  # pragma: no cover - no deltas expected
    return None


def _retry_factory(_: str):  # pragma: no cover - deterministic
    from crux_providers.base.resilience.retry import RetryConfig
    return RetryConfig(max_attempts=1, delay_base=0.0)


def _maybe_parse_json(line: str):
    line = line.strip()
    if not line or (not line.startswith('{')) or (not line.endswith('}')):
        return None
    # Minimal structural validation before json.loads to avoid blanket try/except continue.
    if '"event"' not in line and '"phase"' not in line:
        return None
    return json.loads(line)


def _extract_finalize_payload(log_records: list[Any]):
    finalize_payloads = []
    for rec in log_records:
        line = getattr(rec, 'getMessage', lambda: rec)()
        obj = _maybe_parse_json(line)
        if not obj:
            continue
        if obj.get("phase") == "finalize":
            finalize_payloads.append(obj)
    if not finalize_payloads:
        raise AssertionError("expected at least one finalize log record")
    return finalize_payloads[-1]


def test_logging_internal_start_shape(log_capture):
    print("TEST: logging finalize payload includes error_code=internal for starter shape violation")
    logger = get_logger("providers.test.internal_logging", json_mode=True)
    adapter = BaseStreamingAdapter(
        ctx=LogContext(provider="fake_provider", model="fake-model"),
        provider_name="fake_provider",
        model="fake-model",
        starter=_starter_invalid_mapping,
        translator=_translator,
        retry_config_factory=_retry_factory,
        logger=logger,
    )
    events = list(adapter.run())
    if len(events) != 1:
        raise AssertionError(f"expected 1 terminal event got {len(events)}")
    payload = _extract_finalize_payload(log_capture)
    if payload.get("error_code") != "internal":
        raise AssertionError(f"expected error_code internal, got {payload}")
    if payload.get("emitted") is not False:
        raise AssertionError(f"expected emitted False, got {payload}")
    if payload.get("emitted_count") not in (0, None):
        raise AssertionError(f"expected emitted_count 0, got {payload}")
    if payload.get("phase") != "finalize":
        raise AssertionError(f"expected phase finalize, got {payload}")
