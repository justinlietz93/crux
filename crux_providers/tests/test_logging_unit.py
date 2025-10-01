from __future__ import annotations

import json
import logging

from crux_providers.base.logging import (
    LogContext,
    get_logger,
    normalized_log_event,
)


def test_get_logger_env_overrides_level(monkeypatch, capsys):
    monkeypatch.setenv("PROVIDERS_LOG_LEVEL", "ERROR")
    logger = get_logger(name="providers.test", json_mode=True, level=logging.DEBUG)
    # INFO log shouldn't appear
    logger.info("hello")
    out = capsys.readouterr().err
    assert out == ""  # nosec B101 - asserts are appropriate in unit tests
    # ERROR should be emitted as JSON
    logger.error("fail")
    out = capsys.readouterr().err
    data = json.loads(out.strip())
    assert data["level"] == "ERROR"  # nosec B101 - asserts are appropriate in unit tests


def test_normalized_log_event_includes_required_keys(capsys):
    logger = get_logger(name="providers.test2", json_mode=True)
    ctx = LogContext(provider="p", model="m", request_id="r1")
    normalized_log_event(
        logger,
        "stream.finalize",
        ctx,
        phase="finalize",
        attempt=1,
        error_code=None,
        emitted=True,
        tokens={"prompt": 1, "completion": 2, "total": 3},
        include_raw_code_alias=True,
        extra_field=123,
    )
    out = capsys.readouterr().err
    data = json.loads(out.strip())
    payload = json.loads(data["msg"])  # inner payload from log_event
    # Required normalized keys except fields with None values are dropped by log_event
    for k in ("structured", "phase", "attempt", "emitted", "tokens"):
        assert k in payload  # nosec B101 - asserts are fine in tests
    assert "error_code" not in payload  # nosec B101 - asserts are fine in tests
    assert payload["extra_field"] == 123  # nosec B101 - asserts are fine in tests
