# -*- coding: utf-8 -*-
"""Utility helpers shared by the CLI developer shell.

This module groups small, reusable helpers to keep the interactive shell
implementation focused and under the 500 LOC policy limit.

Functions
---------
- ``parse_verbosity(value)``: Map user strings and synonyms to a canonical
  logging level name.
- ``suppress_console_logs()``: Context manager to temporarily detach console
  handlers while preserving file handlers, avoiding interleaved JSON logs
  during streaming output.
- ``format_metadata(meta, mode)``: Render provider metadata in JSON or
  tabular form for terminal display or file logging.
"""

from __future__ import annotations

import contextlib
import json
import logging
from typing import Any, Dict, Iterator, List, Optional, Tuple


def parse_verbosity(value: str) -> Optional[str]:
    """Parse a user-provided verbosity string into a canonical level.

    Accepted values (case-insensitive):
    - Canonical: DEBUG, INFO, WARNING, ERROR, CRITICAL
    - Synonyms: verbose->DEBUG; low->INFO; med/medium/warn->WARNING;
      high/error/err/quiet->ERROR; critical/crit/silent->CRITICAL

    Parameters
    ----------
    value: str
        User-provided verbosity string (e.g., "info", "verbose").

    Returns
    -------
    Optional[str]
        Canonical upper-cased level, or ``None`` if invalid.
    """
    v = value.strip().lower()
    mapping = {
        "debug": "DEBUG",
        "verbose": "DEBUG",
        "info": "INFO",
        "low": "INFO",
        "warning": "WARNING",
        "warn": "WARNING",
        "medium": "WARNING",
        "med": "WARNING",
        "error": "ERROR",
        "err": "ERROR",
        "high": "ERROR",
        "quiet": "ERROR",
        "critical": "CRITICAL",
        "crit": "CRITICAL",
        "silent": "CRITICAL",
    }
    if v in mapping:
        return mapping[v]
    canon = value.strip().upper()
    if canon in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
        return canon
    return None


def _normalize_metadata_input(meta: Any) -> Dict[str, Any]:
    """Coerce metadata objects or dictionaries into a plain mapping."""
    if meta is None:
        return {}
    if hasattr(meta, "to_dict"):
        try:
            candidate = meta.to_dict()  # type: ignore[call-arg]
        except Exception:
            candidate = None
        if isinstance(candidate, dict):
            return candidate
    if isinstance(meta, dict):
        return dict(meta)
    return {}


def _stringify_metadata_value(value: Any) -> str:
    """Return a human-friendly string representation for metadata values."""
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def _flatten_metadata_rows(data: Dict[str, Any]) -> List[Tuple[str, str]]:
    """Flatten metadata dictionary entries into displayable key/value rows."""
    rows: List[Tuple[str, str]] = []
    for key, value in data.items():
        if key == "extra" and isinstance(value, dict):
            for extra_key, extra_val in value.items():
                rows.append((f"extra.{extra_key}", _stringify_metadata_value(extra_val)))
            continue
        rows.append((key, _stringify_metadata_value(value)))
    return rows


def format_metadata(meta: Any, *, mode: str = "json") -> str:
    """Format provider metadata for terminal or file output.

    Parameters
    ----------
    meta: Any
        Metadata object (``ProviderMetadata`` or ``dict``) to render.
    mode: str, default "json"
        Display mode: ``"json"`` (pretty-printed JSON), ``"table"``
        (two-column table), or ``"off"`` (return empty string).

    Returns
    -------
    str
        Rendered metadata string. Empty string indicates nothing should be
        displayed.

    Notes
    -----
    - Non-dictionary inputs are coerced via ``to_dict`` when available.
    - Nested ``extra`` values are flattened into dotted keys for table mode.
    """
    normalized = _normalize_metadata_input(meta)
    if not normalized:
        return ""
    effective_mode = (mode or "json").strip().lower()
    if effective_mode == "off":
        return ""
    if effective_mode == "table":
        rows = _flatten_metadata_rows(normalized)
        if not rows:
            return ""
        width = max(len(key) for key, _ in rows)
        return "\n".join(f"{key.ljust(width)} : {value}" for key, value in rows)
    # Default to JSON output for unrecognized modes for resilience
    return json.dumps(normalized, ensure_ascii=False, indent=2)


@contextlib.contextmanager
def suppress_console_logs() -> Iterator[None]:
    """Temporarily detach console handlers to silence log spam.

    Summary
    -------
    Some providers emit frequent INFO-level structured logs during streaming
    (e.g., decode events). This context manager temporarily removes console
    handlers attached to the shared ``providers`` logger and its children so
    those logs do not interleave with streamed token output in the interactive
    shell. File logging remains unaffected.

    Behavior
    --------
    - Only console handlers (stderr/stdout) are affected.
    - Managed file handlers (tagged with ``_providers_file_handler``) are left
      untouched.
    - Original handlers and propagation flags are restored on exit.
    """
    propagate_prev: List[Tuple[logging.Logger, bool]] = []
    detached: List[Tuple[logging.Logger, logging.Handler, int]] = []
    try:
        target_loggers: List[logging.Logger] = []
        base = logging.getLogger("providers")
        target_loggers.append(base)
        for name, logger in list(getattr(logging.Logger.manager, "loggerDict", {}).items()):  # type: ignore[attr-defined]
            if not isinstance(name, str):
                continue
            placeholder = getattr(logging, "PlaceHolder", None)
            if placeholder is not None and isinstance(logger, placeholder):
                continue
            if name.startswith("providers"):
                target_loggers.append(logging.getLogger(name))
        seen = set()
        unique_loggers: List[logging.Logger] = []
        for lg in target_loggers:
            if lg.name in seen:
                continue
            seen.add(lg.name)
            unique_loggers.append(lg)

        for lg in unique_loggers:
            propagate_prev.append((lg, lg.propagate))
            lg.propagate = False
            for handler in list(lg.handlers):
                if getattr(handler, "_providers_file_handler", False):
                    continue
                if isinstance(handler, logging.StreamHandler) or hasattr(handler, "stream"):
                    try:
                        handler.flush()
                    except Exception:
                        pass
                    detached.append((lg, handler, handler.level if hasattr(handler, "level") else lg.level))
                    lg.removeHandler(handler)
        yield
    finally:
        for lg, previous in propagate_prev:
            with contextlib.suppress(Exception):
                lg.propagate = previous
        for lg, handler, level in detached:
            with contextlib.suppress(Exception):
                handler.setLevel(level)
                lg.addHandler(handler)


__all__ = ["parse_verbosity", "suppress_console_logs", "format_metadata"]
