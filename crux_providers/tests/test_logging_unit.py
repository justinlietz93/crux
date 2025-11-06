"""Unit coverage for structured logging utilities and helpers."""

from __future__ import annotations

import io
import json
import logging

from crux_providers.base.logging import (
    LogContext,
    configure_logger,
    get_logger,
    normalized_log_event,
)
from crux_providers.base.log_support import JsonFormatter


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


def test_json_formatter_hoists_json_message() -> None:
    """Ensure the formatter hoists JSON message keys without double escaping."""

    formatter = JsonFormatter()
    record = logging.LogRecord(
        name="providers.test.json",
        level=logging.INFO,
        pathname=__file__,
        lineno=0,
        msg=json.dumps({"provider": "ollama", "event": "cli.prompt"}),
        args=(),
        exc_info=None,
    )
    formatted = formatter.format(record)
    payload = json.loads(formatted)
    assert payload["provider"] == "ollama"  # nosec B101 - validates hoisting
    assert "msg" not in payload  # nosec B101 - CLI events suppress raw message noise


def test_child_logger_uses_parent_handler_without_duplicates() -> None:
    """Verify child loggers propagate to the base handler without duplicate lines."""

    logger = get_logger(name="providers.test.child", json_mode=False)
    base_logger = logging.getLogger("providers")
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(logging.Formatter("%(message)s"))
    setattr(handler, "_providers_console_handler", True)
    handler.setLevel(base_logger.level)
    base_logger.handlers[:] = [handler]

    logger.info("alpha")
    handler.flush()
    lines = [ln for ln in stream.getvalue().splitlines() if ln]
    assert lines == ["alpha"]  # nosec B101 - ensures single emission


def test_child_logger_respects_warning_level() -> None:
    """Validate that INFO logs are suppressed when the base level is WARNING."""

    logger = get_logger(name="providers.test.levels", json_mode=False)
    base_logger = logging.getLogger("providers")
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(logging.Formatter("%(message)s"))
    setattr(handler, "_providers_console_handler", True)
    handler.setLevel(base_logger.level)
    base_logger.handlers[:] = [handler]

    configure_logger(level=logging.WARNING)
    stream.truncate(0)
    stream.seek(0)

    logger.info("hidden")
    handler.flush()
    assert stream.getvalue() == ""  # nosec B101 - INFO suppressed

    logger.error("visible")
    handler.flush()
    lines = [ln for ln in stream.getvalue().splitlines() if ln]
    assert lines == ["visible"]  # nosec B101 - ERROR allowed
