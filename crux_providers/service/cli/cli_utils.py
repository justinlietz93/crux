"""CLI utility helpers for the developer terminal.

This module groups small, reusable helpers to keep the interactive shell
implementation focused and under the 500 LOC policy limit.

Functions
---------
- ``parse_verbosity(value)``: Map user strings and synonyms to a canonical
  logging level name.
- ``suppress_console_logs()``: Context manager to temporarily silence console
  StreamHandlers while preserving file handlers, avoiding interleaved JSON logs
  during streaming output.
"""

from __future__ import annotations

import contextlib
import logging
from typing import Optional, Iterator


def parse_verbosity(value: str) -> Optional[str]:
    """Parse a user-provided verbosity string into a canonical level.

    Accepted values (case-insensitive):
    - Canonical: DEBUG, INFO, WARNING, ERROR, CRITICAL
    - Synonyms: verbose→DEBUG; low→INFO; med/medium/warn→WARNING;
      high/error/err/quiet→ERROR; critical/crit/silent→CRITICAL

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


@contextlib.contextmanager
def suppress_console_logs() -> Iterator[None]:
    """Temporarily raise console ``StreamHandler`` levels to silence log spam.

    Summary
    -------
    Some providers emit frequent INFO-level structured logs during streaming
    (e.g., decode events). This context manager temporarily raises the level of
    any console ``StreamHandler`` attached to the shared ``providers`` logger
    and its children (e.g., ``providers.openrouter``) so those logs do not
    interleave with streamed token output in the interactive shell. File logging
    remains unaffected.

    Behavior
    --------
    - Only console handlers (stderr) are affected.
    - Managed file handlers (tagged with ``_providers_file_handler``) are left
      untouched.
    - Previous levels are restored on exit.
    """
    handlers_prev: list[tuple[logging.Handler, int]] = []
    propagate_prev: list[tuple[logging.Logger, bool]] = []
    try:
        # Consider the base logger and common child names; walk existing
        # loggers to catch dynamically created per-provider loggers.
        target_loggers: list[logging.Logger] = []
        base = logging.getLogger("providers")
        target_loggers.append(base)
        # Include known child namespaces if present
        for name, logger in list(getattr(logging.Logger.manager, "loggerDict", {}).items()):  # type: ignore[attr-defined]
            # Skip placeholders and unrelated loggers; avoid try/except/continue pattern
            if not isinstance(name, str):
                continue
            # Some entries may be PlaceHolder; skip safely
            if getattr(logging, "PlaceHolder", None) is not None and isinstance(logger, logging.PlaceHolder):  # type: ignore[attr-defined]
                continue
            if name.startswith("providers"):
                target_loggers.append(logging.getLogger(name))
        # Deduplicate
        seen = set()
        unique_loggers = []
        for lg in target_loggers:
            if lg.name in seen:
                continue
            seen.add(lg.name)
            unique_loggers.append(lg)

        for lg in unique_loggers:
            # Disable propagation so records don't reach root handlers
            propagate_prev.append((lg, lg.propagate))
            lg.propagate = False
            for h in list(lg.handlers):
                if getattr(h, "_providers_file_handler", False):
                    continue
                if isinstance(h, logging.StreamHandler):
                    prev_level = h.level if hasattr(h, "level") else lg.level
                    handlers_prev.append((h, prev_level))
                    h.setLevel(logging.CRITICAL + 1)
        yield
    finally:
        for lg, prev_prop in propagate_prev:
            with contextlib.suppress(Exception):
                lg.propagate = prev_prop
        for h, prev in handlers_prev:
            with contextlib.suppress(Exception):
                h.setLevel(prev)


__all__ = ["parse_verbosity", "suppress_console_logs"]
