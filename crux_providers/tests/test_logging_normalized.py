"""Focused tests for crux_providers.base.logging.

Covers:
- _parse_level string parsing
- _coerce_tokens stability
- normalized_log_event emits required keys and respects aliasing
"""
from __future__ import annotations

import json
import logging
from typing import Mapping

from crux_providers.base.logging import (
    REQUIRED_NORMALIZED_KEYS,
    _parse_level,  # type: ignore[attr-defined]
    normalized_log_event,
    get_logger,
)
from crux_providers.base.log_support import LogContext


class _ListHandler(logging.Handler):
    """Capture log records into a list for assertions."""

    def __init__(self) -> None:
        super().__init__(level=logging.DEBUG)
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:  # pragma: no cover - exercised via tests
        msg = record.getMessage()
        self.messages.append(msg)


def test_parse_level_variants():
    assert _parse_level(None) == logging.INFO  # nosec B101
    assert _parse_level("debug") == logging.DEBUG  # nosec B101
    assert _parse_level("WARN") == logging.WARNING  # nosec B101
    assert _parse_level("unknown", default=logging.ERROR) == logging.ERROR  # nosec B101


def test_normalized_log_event_emits_required_keys_and_alias():
    logger = get_logger("providers.test.logging", json_mode=False)
    # Swap handler with list collector to avoid stderr noise
    handler = _ListHandler()
    logger.handlers[:] = [handler]

    ctx = LogContext(provider="p", model="m")
    normalized_log_event(
        logger,
        "stream.end",
        ctx,
        phase="finalize",
        attempt=None,
        error_code="TIMEOUT",
        emitted=3,
        tokens={"prompt": 10, "completion": 5},
        metrics={"time_to_first_token_ms": 12.3},
    )

    assert handler.messages, "expected a log message"  # nosec B101
    payload = json.loads(handler.messages[-1])
    for key in REQUIRED_NORMALIZED_KEYS:
        assert key in payload  # nosec B101
    # Back-compat alias 'code' mirrors error_code when provided
    assert payload["code"] == "TIMEOUT"  # nosec B101


def test_coerce_tokens_mapping_and_tuple_pairs():
    # Mapping preserved
    logger = get_logger("providers.test.logging2", json_mode=False)
    handler = _ListHandler()
    logger.handlers[:] = [handler]

    ctx = LogContext(provider="p", model="m")
    # Use tuple pairs to exercise conversion path
    normalized_log_event(
        logger,
        "stream.end",
        ctx,
        phase="finalize",
        tokens=[("a", 1), ("b", 2)],
    )
    payload = json.loads(handler.messages[-1])
    assert payload["tokens"] == {"a": 1, "b": 2}  # nosec B101
