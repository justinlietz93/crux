"""Ollama CLI helpers for model discovery.

Purpose
    Provide secure utilities for resolving and invoking the trusted local
    ``ollama`` executable as part of the model refresh workflow.

External Dependencies
    * Local ``ollama`` CLI binary executed via :mod:`subprocess`.

Fallback Semantics
    Errors are propagated to callers so they can perform structured logging and
    engage HTTP or cache fallbacks.

Timeout Strategy
    Callers must supply explicit timeout values that align with
    :func:`crux_providers.base.timeouts.get_timeout_config`.
"""

from __future__ import annotations

import os
import shutil
import stat
import subprocess  # nosec B404 - required for invoking trusted local 'ollama' CLI (fixed arg list)
from typing import List


def _validate_executable(path: str) -> None:
    """Validate the resolved ``ollama`` executable path.

    Parameters
    ----------
    path: str
        Absolute path returned by :func:`shutil.which`.

    Raises
    ------
    RuntimeError
        If the executable fails security validation checks.
    """

    base = os.path.basename(path)
    if base != "ollama":  # pragma: no cover - safety guard
        error = RuntimeError(
            f"resolved executable basename mismatch (expected 'ollama'): {path}"
        )
        setattr(error, "path", path)
        raise error

    try:
        stat_result = os.stat(path)
    except OSError as exc:  # pragma: no cover - unexpected I/O failure
        error = RuntimeError(f"cannot stat ollama executable {path}: {exc}")
        setattr(error, "path", path)
        raise error from exc

    if not stat.S_ISREG(stat_result.st_mode):  # pragma: no cover - defensive guard
        error = RuntimeError(f"ollama executable is not a regular file: {path}")
        setattr(error, "path", path)
        raise error

    if not os.access(path, os.X_OK):  # pragma: no cover - defensive guard
        error = RuntimeError(f"ollama executable not user-executable: {path}")
        setattr(error, "path", path)
        raise error

    if stat_result.st_mode & 0o022:
        error = RuntimeError(
            f"ollama executable has insecure write permissions (group/other writable): {path}"
        )
        setattr(error, "path", path)
        raise error


def resolve_ollama_executable() -> str:
    """Return the absolute path to the validated ``ollama`` executable.

    Returns
    -------
    str
        Absolute, validated path to the ``ollama`` executable.

    Raises
    ------
    FileNotFoundError
        If the executable cannot be located on ``PATH``.
    RuntimeError
        If validation fails (e.g., wrong permissions or unexpected file type).
    """

    exe_path = shutil.which("ollama")
    if not exe_path:
        raise FileNotFoundError("'ollama' executable not found on PATH")

    abs_path = os.path.abspath(exe_path)
    _validate_executable(abs_path)
    return abs_path


def build_ollama_list_cmd(exe_path: str, json_output: bool) -> List[str]:
    """Construct a secure ``ollama list`` command vector.

    Parameters
    ----------
    exe_path: str
        Validated executable path returned by :func:`resolve_ollama_executable`.
    json_output: bool
        Indicates whether ``--json`` should be appended.

    Returns
    -------
    List[str]
        Argument vector suitable for :func:`subprocess.run` with ``shell=False``.
    """

    cmd: List[str] = [exe_path, "list"]
    if json_output:
        cmd.append("--json")
    return cmd


def run_ollama_command(cmd: List[str], timeout: int) -> str:
    """Execute an ``ollama`` command and return its stdout payload.

    Parameters
    ----------
    cmd: List[str]
        Whitelisted command arguments produced by :func:`build_ollama_list_cmd`.
    timeout: int
        Timeout in seconds applied to the CLI invocation.

    Returns
    -------
    str
        Captured standard output from the command execution.

    Raises
    ------
    subprocess.SubprocessError
        If the command exits unsuccessfully or exceeds the timeout.
    """

    completed = subprocess.run(  # nosec B603 - fixed, validated arg list; no user input; shell=False
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
        timeout=timeout,
    )
    return completed.stdout


__all__ = [
    "resolve_ollama_executable",
    "build_ollama_list_cmd",
    "run_ollama_command",
]
