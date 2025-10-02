"""Base structured logging utilities for provider layer.

Rationale:
- Central place to configure consistent JSON (or plain) logging.
- Avoid sprinkling ad-hoc logger setup across adapters.
- Keep file small (<500 LOC rule) and dependency-free.

Normalization additions (issues #11 / #49):
This module now provides ``normalized_log_event`` which wraps ``log_event`` and injects
canonical structured keys across providers: ``structured`` (bool), ``phase`` (str),
``attempt`` (int|None), ``error_code`` (str|None), ``emitted`` (bool|None), ``tokens``
(mapping|None placeholder). Existing call sites can migrate incrementally; the legacy
API remains for backward compatibility.
"""
from __future__ import annotations

import logging
import json
import sys
import os
import contextlib
from logging.handlers import RotatingFileHandler
from typing import Any, Dict, Mapping, Optional

from .log_support import JsonFormatter, LogContext


_BASE_LOGGER_ATTR = "_providers_logger_initialized"
_CHILD_LOGGER_ATTR = "_providers_child_configured"
_CONSOLE_HANDLER_ATTR = "_providers_console_handler"


def _ensure_base_logger(json_mode: bool, level: int) -> logging.Logger:
    """Initialize and return the shared ``providers`` logger."""

    logger = logging.getLogger("providers")
    desired_level = _parse_level(os.getenv("PROVIDERS_LOG_LEVEL"), default=level)
    if getattr(logger, _BASE_LOGGER_ATTR, False):
        if logger.level != desired_level:
            logger.setLevel(desired_level)
        for existing in list(logger.handlers):
            if not getattr(existing, _CONSOLE_HANDLER_ATTR, False):
                continue
            stream_obj = getattr(existing, "stream", None)
            if stream_obj is None or getattr(stream_obj, "closed", False):
                logger.removeHandler(existing)
                with contextlib.suppress(Exception):
                    existing.close()
                replacement = logging.StreamHandler(sys.stderr)
                replacement.setLevel(desired_level)
                if json_mode:
                    replacement.setFormatter(JsonFormatter())
                else:
                    replacement.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
                setattr(replacement, _CONSOLE_HANDLER_ATTR, True)
                logger.addHandler(replacement)
                continue
            existing.setLevel(desired_level)
            if hasattr(existing, "setStream"):
                with contextlib.suppress(Exception):
                    existing.setStream(sys.stderr)
            if json_mode and not isinstance(existing.formatter, JsonFormatter):
                existing.setFormatter(JsonFormatter())
            elif not json_mode and isinstance(existing.formatter, JsonFormatter):
                existing.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
        return logger

    env_level = desired_level
    logger.setLevel(env_level)
    handler = logging.StreamHandler(sys.stderr)
    handler.setLevel(env_level)
    if json_mode:
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    setattr(handler, _CONSOLE_HANDLER_ATTR, True)
    logger.handlers[:] = [handler]
    logger.propagate = False
    setattr(logger, _BASE_LOGGER_ATTR, True)
    logger._configured_base_logger = True  # type: ignore[attr-defined]
    return logger


def _parse_level(value: str | None, default: int = logging.INFO) -> int:
    """Parse a logging level string into an integer constant.

    Accepts common names (DEBUG, INFO, WARNING, ERROR, CRITICAL) case-insensitively.
    Falls back to ``default`` on unknown values.
    """
    if not value:
        return default
    mapping = {
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "WARN": logging.WARNING,
        "WARNING": logging.WARNING,
        "ERROR": logging.ERROR,
        "CRITICAL": logging.CRITICAL,
    }
    return mapping.get(value.strip().upper(), default)


def get_logger(name: str = "providers", json_mode: bool = True, level: int = logging.INFO) -> logging.Logger:
    base_logger = _ensure_base_logger(json_mode=json_mode, level=level)
    if name == "providers":
        return base_logger

    logger = logging.getLogger(name)
    # Drop previously managed console handlers to avoid duplicate emissions.
    for handler in list(logger.handlers):
        if getattr(handler, _CONSOLE_HANDLER_ATTR, False):
            logger.removeHandler(handler)
            with contextlib.suppress(Exception):
                handler.close()
    logger.setLevel(logging.NOTSET)
    logger.propagate = True
    setattr(logger, _CHILD_LOGGER_ATTR, True)
    logger._configured_base_logger = True  # type: ignore[attr-defined]
    return logger


def configure_logger(
    *,
    level: int | str | None = None,
    file_path: Optional[str] = None,
    json_mode: bool = True,
    logger_name: str = "providers",
) -> logging.Logger:
    """Reconfigure the shared providers logger at runtime.

    Summary
    -------
    Adjust the logger level and attach or remove a file handler without requiring
    process restart. This keeps the logging configuration centralized and
    consistent across modules.

    Parameters
    ----------
    level: int | str | None
        Desired logging level. Accepts numeric levels or names (e.g., "DEBUG").
        When ``None``, the current level is preserved.
    file_path: Optional[str]
        When provided, a file handler is attached (created if missing) writing
        JSON or plain logs to ``file_path``. When ``None``, any previously
        attached file handler managed by this module is removed.
    json_mode: bool
        Whether to use the JSON formatter (recommended) or a human-readable
        plain text formatter for the added handler(s).
    logger_name: str
        Name of the logger to configure. Defaults to the shared "providers" logger.

    Returns
    -------
    logging.Logger
        The configured logger instance.

    Notes
    -----
    - File handler is tagged with ``_providers_file_handler = True`` to allow
      idempotent updates and safe removal without touching user-attached handlers.
    - This function preserves any existing non-managed handlers.
    """
    logger = logging.getLogger(logger_name)
    # Ensure base configuration exists
    if not getattr(logger, "_configured_base_logger", False):  # pragma: no cover - init path
        _ = get_logger(logger_name, json_mode=json_mode)
        logger = logging.getLogger(logger_name)

    # Update level if requested
    if level is not None:
        if isinstance(level, str):
            logger.setLevel(_parse_level(level, default=logger.level))
        else:
            logger.setLevel(level)
        for h in logger.handlers:
            h.setLevel(logger.level)

    # Manage file handler
    # Remove existing managed file handlers if file_path is None
    managed_handlers = [h for h in logger.handlers if getattr(h, "_providers_file_handler", False)]
    if file_path is None:
        for h in managed_handlers:
            logger.removeHandler(h)
            with contextlib.suppress(Exception):  # pragma: no cover - defensive
                h.close()
        return logger

    # Ensure directory exists
    try:
        abs_path = os.path.abspath(os.path.expanduser(file_path))
        os.makedirs(os.path.dirname(abs_path), exist_ok=True)
    except Exception:  # pragma: no cover - environment specific
        abs_path = os.path.abspath(os.path.expanduser(file_path))

    # Reuse existing managed handler if pointing to same path; otherwise replace
    existing: Optional[logging.FileHandler] = None
    for h in managed_handlers:
        if isinstance(h, logging.FileHandler) and getattr(h, "baseFilename", None) == abs_path:
            existing = h
        else:
            logger.removeHandler(h)
            with contextlib.suppress(Exception):  # pragma: no cover - defensive
                h.close()

    if existing is None:
        # Use a rotating file handler to avoid unbounded growth (10MB x 5 backups)
        fh = RotatingFileHandler(abs_path, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8")
        fh._providers_file_handler = True  # type: ignore[attr-defined]
        fh.setLevel(logger.level)
        if json_mode:
            fh.setFormatter(JsonFormatter())
        else:
            fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
        logger.addHandler(fh)
    else:
        # Make sure formatter and level reflect current preferences
        if json_mode:
            existing.setFormatter(JsonFormatter())
        else:
            existing.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
        existing.setLevel(logger.level)

    return logger


def log_event(
    logger: logging.Logger,
    event: str,
    ctx: LogContext | None = None,
    *,
    keep_none: bool = False,
    **fields: Any,
) -> None:
    """Emit a structured log event with optional ``None`` preservation.

    Summary
    -------
    Base primitive for emitting structured log payloads. By default, this function
    drops keys whose values are ``None`` to keep logs concise. When ``keep_none`` is
    ``True``, keys with ``None`` values are preserved in the payload (encoded as JSON
    ``null``). This is leveraged by ``normalized_log_event`` to guarantee presence of
    required schema keys even if their values are unknown.

    Parameters
    ----------
    logger: logging.Logger
        Logger instance (should be JSON formatted by ``get_logger``).
    event: str
        Event name (e.g. ``stream.start``).
    ctx: LogContext | None
        Provider/model context; merged shallowly.
    keep_none: bool
        When ``True``, preserve keys whose values are ``None``; otherwise drop them.
    **fields: Any
        Arbitrary serializable key/value pairs.

    Side Effects
    ------------
    Writes a single line JSON payload to the configured logger handler.
    """
    payload = {"event": event}
    if ctx:
        payload |= ctx.to_dict()
    if keep_none:
        payload.update(fields)
    else:
        payload.update({k: v for k, v in fields.items() if v is not None})
    logger.info(json.dumps(payload, ensure_ascii=False))


# ---------------------- Normalization Layer ---------------------------------
REQUIRED_NORMALIZED_KEYS = (
    "structured",
    "phase",
    "attempt",
    "error_code",
    "emitted",
    "tokens",
)


def _coerce_tokens(tokens: Any) -> Any:
    """Coerce arbitrary token usage info into a stable JSON-friendly form.

    Accepts None (placeholder), mapping-like objects, or sequence of key/value tuples.
    Falls back to ``{"value": repr(obj)}`` for opaque values.
    """
    if tokens is None:
        return None
    if isinstance(tokens, Mapping):
        return dict(tokens.items())
    if isinstance(tokens, (list, tuple)):
        try:
            return dict(tokens)
        except Exception:  # pragma: no cover - defensive
            return {"value": repr(tokens)}
    return {"value": repr(tokens)}


def normalized_log_event(  # noqa: PLR0913,C901  # pylint: disable=too-many-arguments,too-many-branches
    # deviation: style-params reason=Stable public log API requires explicit fields for clarity; reducing params would hurt callsites. revisit=2025-12
    logger: logging.Logger,
    event: str,
    ctx: LogContext | None = None,
    *,
    phase: str,
    attempt: int | None = None,
    error_code: str | None = None,
    emitted: bool | None = None,
    tokens: Any = None,
    structured: bool = True,
    include_raw_code_alias: bool = True,
    **extra_fields: Any,
) -> None:
    """Emit a normalized structured log event with required keys.

    The normalized schema guarantees the presence of canonical keys enabling
    downstream aggregation and filtering regardless of provider implementation.

        Parameters mirror the required field set; any additional ``extra_fields`` are merged
        without overwriting explicitly provided normalized values.

        Notes
        -----
        - Keys in the normalized schema are guaranteed to be present, with one exception:
            ``error_code`` is omitted when ``None`` to reflect "no error" more naturally
            and remain compatible with legacy expectations in unit tests.
    """
    base_fields: Dict[str, Any] = {
        "structured": structured,
        "phase": phase,
        "attempt": attempt,
        "error_code": error_code,
        "emitted": emitted,
        "tokens": _coerce_tokens(tokens),
    }
    if include_raw_code_alias and error_code is not None and "code" not in extra_fields:
        # Backward compatibility alias for legacy dashboards expecting "code"
        base_fields["code"] = error_code
    # Drop error_code when None while preserving other None-valued required keys
    if error_code is None:
        base_fields.pop("error_code", None)
    for k, v in extra_fields.items():
        if v is None:
            continue
        if k in base_fields and base_fields[k] is not None:
            continue  # do not clobber normalized values
        base_fields[k] = v
    # Preserve None values (except error_code which was stripped above) to ensure
    # required normalized keys are present for downstream consumers.
    log_event(logger, event, ctx, keep_none=True, **base_fields)


__all__ = [
    "LogContext",
    "get_logger",
    "configure_logger",
    "log_event",
    "normalized_log_event",
    "REQUIRED_NORMALIZED_KEYS",
]
