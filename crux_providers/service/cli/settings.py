"""Persistent CLI settings management for the developer shell.

Purpose
-------
Provide a small, dependency-free settings layer for the interactive CLI shell
that persists user preferences across sessions (verbosity, log file output).
Settings are stored under the user's configuration directory using the XDG
spec where available, falling back to ``~/.config/crux_providers/cli.json``.
Log files default to the XDG state directory (``$XDG_STATE_HOME``) or
``~/.local/state/crux_providers`` to avoid cluttering the config directory.

Public API
----------
- ``CLISettings``: Dataclass-like container for settings.
- ``load_settings()``: Load settings from disk (or defaults on first run).
- ``save_settings(settings)``: Persist settings atomically to disk.
- ``apply_logging(settings)``: Apply logging configuration immediately using
  the base logging facilities (level and optional file handler).

Notes
-----
- No hard-coded numeric timeouts or I/O tricks; simple JSON read/write.
- All functions include descriptive docstrings per project policy.
"""


from __future__ import annotations

import contextlib
import json
import logging
import os
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Tuple

from ...base.logging import get_logger, log_event  # reuse configured logger + structured API
from ...base import logging as base_logging


CONFIG_DIR_NAME = "crux_providers"
CONFIG_FILE_NAME = "cli.json"
DEFAULT_LOG_FILE = "crux_dev.log"
DEFAULT_META_LOG_FILE = "crux_dev_metadata.log"
HISTORY_FILE_NAME = "cli_history"


def _xdg_config_dir() -> Path:
    """Return the XDG-compliant configuration directory for this app.

    Resolution order follows the XDG spec: use the ``XDG_CONFIG_HOME`` environment
    variable if set and non-empty; otherwise fall back to ``~/.config``. The final
    directory path is ``<config_root>/crux_providers``.
    """

    root = os.environ.get("XDG_CONFIG_HOME")
    base = Path(root).expanduser() if root else Path.home() / ".config"
    return base / CONFIG_DIR_NAME


def _config_file_path() -> Path:
    """Compute the full path to the CLI settings JSON file."""

    return _xdg_config_dir() / CONFIG_FILE_NAME


def _xdg_state_dir() -> Path:
    """Return the XDG-compliant state directory for this app.

    Resolution order: use ``XDG_STATE_HOME`` when set, otherwise
    ``~/.local/state``. The final directory path is
    ``<state_root>/crux_providers``.
    """

    root = os.environ.get("XDG_STATE_HOME")
    base = Path(root).expanduser() if root else Path.home() / ".local" / "state"
    return base / CONFIG_DIR_NAME


@dataclass
class CLISettings:
    """Container for CLI user preferences.

    Attributes
    ----------
    verbosity: str
        Logging level name, e.g., ``"INFO"``, ``"DEBUG"``, ``"WARNING"``.
    log_to_file: bool
        When ``True``, also write logs to a file in addition to stderr.
    log_file_path: str
        Absolute or user-relative path to the desired log file. The default
        resolves under the application's config directory.
    meta_display: str
        Preferred metadata presentation mode (``json``, ``table``, or ``off``).
    meta_log_to_file: bool
        When ``True``, append rendered metadata to a companion log file.
    meta_log_file_path: str
        Destination path for metadata log output when enabled.
    """

    verbosity: str = "INFO"
    log_to_file: bool = False
    log_file_path: str = str(_xdg_state_dir() / DEFAULT_LOG_FILE)
    meta_display: str = "json"
    meta_log_to_file: bool = False
    meta_log_file_path: str = str(_xdg_state_dir() / DEFAULT_META_LOG_FILE)
    # UI conveniences
    ui_colors: bool = True
    ui_readline: bool = True
    ui_completions: bool = True
    history_file_path: str = str(_xdg_state_dir() / HISTORY_FILE_NAME)
    # Last session values (persist stream/live/provider/model)
    last_provider: str | None = None
    last_model: str | None = None
    last_stream: bool = False
    last_live: bool = False


def load_settings() -> CLISettings:
    """Load CLI settings from disk or return defaults if absent.

    Returns
    -------
    CLISettings
        The loaded or default settings instance.
    """

    cfg_path = _config_file_path()
    with contextlib.suppress(Exception):
        if cfg_path.is_file():
            data = json.loads(cfg_path.read_text(encoding="utf-8"))
            # Canonicalize verbosity on load to ensure persistence stability
            raw_v = str(data.get("verbosity", "INFO"))
            canon_v = raw_v.strip().upper()
            if canon_v not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
                canon_v = "INFO"
            meta_mode_raw = str(data.get("meta_display", "json")).strip().lower()
            if meta_mode_raw not in {"json", "table", "off"}:
                meta_mode_raw = "json"
            meta_log_path = str(data.get("meta_log_file_path", str(_xdg_state_dir() / DEFAULT_META_LOG_FILE)))
            return CLISettings(
                verbosity=canon_v,
                log_to_file=bool(data.get("log_to_file", False)),
                # Default log file under state dir, not config dir
                log_file_path=str(data.get("log_file_path", str(_xdg_state_dir() / DEFAULT_LOG_FILE))),
                meta_display=meta_mode_raw,
                meta_log_to_file=bool(data.get("meta_log_to_file", False)),
                meta_log_file_path=meta_log_path,
                ui_colors=bool(data.get("ui_colors", True)),
                ui_readline=bool(data.get("ui_readline", True)),
                ui_completions=bool(data.get("ui_completions", True)),
                history_file_path=str(data.get("history_file_path", str(_xdg_state_dir() / HISTORY_FILE_NAME))),
                last_provider=(str(data.get("last_provider")) if data.get("last_provider") is not None else None),
                last_model=(str(data.get("last_model")) if data.get("last_model") is not None else None),
                last_stream=bool(data.get("last_stream", False)),
                last_live=bool(data.get("last_live", False)),
            )
    return CLISettings()


def save_settings(settings: CLISettings) -> Tuple[bool, str | None]:
    """Persist CLI settings to disk atomically.

    Parameters
    ----------
    settings: CLISettings
        Settings to serialize and save.

    Returns
    -------
    (ok, error)
        Tuple indicating success and optional error message.
    """

    try:
        cfg_dir = _xdg_config_dir()
        cfg_dir.mkdir(parents=True, exist_ok=True)
        cfg_path = _config_file_path()
        tmp_path = cfg_path.with_suffix(".tmp")
        tmp_path.write_text(json.dumps(asdict(settings), ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp_path, cfg_path)
        return True, None
    except Exception as exc:  # pragma: no cover - defensive, environment-specific
        return False, str(exc)


def apply_logging(settings: CLISettings) -> None:
    """Apply logging configuration based on provided settings.

    This function reconfigures the shared providers logger to the desired level
    and attaches or removes a file handler according to ``settings.log_to_file``.

    Notes
    -----
    - Uses the project's base logging module to ensure consistent JSON formatting.
    - Handler configuration is idempotent per invocation.
    """

    level = getattr(logging, settings.verbosity.upper(), logging.INFO)
    # Normalize file path when file logging is enabled (handles directory inputs)
    file_path_str: str | None = None
    if settings.log_to_file:
        normalized = normalize_log_path(settings.log_file_path)
        if normalized != settings.log_file_path:
            settings.log_file_path = normalized
            with contextlib.suppress(Exception):
                save_settings(settings)
        log_file = Path(os.path.expanduser(settings.log_file_path)).resolve()
        # Ensure parent directory exists
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_path_str = str(log_file)
    # Delegate to base logging helper for consistent handler setup
    base_logging.configure_logger(level=level, file_path=file_path_str)
    # Emit a structured event without double-encoding to avoid backslashes
    logger = get_logger()
    log_event(
        logger,
        event="cli.options.apply_logging",
        ctx=None,
        verbosity=settings.verbosity,
        log_to_file=settings.log_to_file,
        log_file_path=settings.log_file_path if settings.log_to_file else None,
    )


__all__ = [
    "CLISettings",
    "load_settings",
    "save_settings",
    "apply_logging",
    "normalize_log_path",
]


def normalize_log_path(raw_path: str) -> str:
    """Normalize a user-provided log path to a concrete file path.

    If ``raw_path`` refers to an existing directory, append the default
    log filename (``crux_dev.log``). If the path does not exist and has no
    file suffix, treat it as a directory and append the default log filename.
    Otherwise, return the expanded absolute file path as-is.

    Parameters
    ----------
    raw_path: str
        A user-provided path that may be a directory or a file path.

    Returns
    -------
    str
        Normalized absolute file path suitable for the file handler.
    """
    p = Path(os.path.expanduser(raw_path))
    # Existing directory → append default filename
    if p.is_dir():
        return str((p / DEFAULT_LOG_FILE).resolve())
    # Non-existent path without suffix → treat as directory
    if not p.exists() and not p.suffix:
        return str(((p / DEFAULT_LOG_FILE)).resolve())
    return str(p.resolve())
