"""JSON logging formatter used by provider logging setup.

This module defines :class:`JsonFormatter`, a minimal JSON formatter that
serializes standard logging fields and merges non-internal extra attributes
from the ``LogRecord``. It is framework-agnostic and intentionally small.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
import contextlib

ISO = "%Y-%m-%dT%H:%M:%S.%fZ"


class JsonFormatter(logging.Formatter):
    """Lightweight JSON formatter for structured logs.

    The formatter includes a timestamp, level, logger name, and message. It
    also merges any extra attributes added to the log record (excluding
    private fields and logging internals) into the output JSON object.
    """

    def format(self, record: logging.LogRecord) -> str:  # pragma: no cover - trivial formatting
        base = {
            "ts": datetime.now(timezone.utc).strftime(ISO),
            "level": record.levelname,
            "logger": record.name,
        }
        # If the message is a JSON string, parse it and hoist keys to top-level
        # so logs do not contain a double-encoded JSON string with backslashes.
        # This preserves caplog behavior (rec.getMessage() remains the raw string)
        # while making the emitted line significantly easier to read and grep.
        msg_text = record.getMessage()
        base["msg"] = msg_text
        with contextlib.suppress(Exception):
            parsed = json.loads(msg_text)
            if isinstance(parsed, dict):
                # Hoist parsed keys to top-level for structured readability
                base.update(parsed)
                # Suppress the original JSON string in 'msg' for CLI events to
                # avoid noisy backslash-escaped output in the developer shell.
                ev = parsed.get("event")
                if isinstance(ev, str) and ev.startswith("cli."):
                    base.pop("msg", None)
        for k, v in record.__dict__.items():
            if k.startswith("_"):
                continue
            if k in (
                "msg",
                "args",
                "levelname",
                "levelno",
                "name",
                "pathname",
                "filename",
                "module",
                "exc_info",
                "exc_text",
                "stack_info",
                "lineno",
                "funcName",
                "created",
                "msecs",
                "relativeCreated",
                "thread",
                "threadName",
                "processName",
                "process",
            ):
                continue
            if k not in base:
                base[k] = v
        return json.dumps(base, ensure_ascii=False)


__all__ = ["JsonFormatter", "ISO"]
