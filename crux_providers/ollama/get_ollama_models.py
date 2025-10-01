"""
Ollama: get models

Behavior
- Attempts to fetch locally installed models via the 'ollama list' CLI.
- Persists the normalized snapshot to SQLite via ``save_provider_models``
    (DB-first; no JSON cache file is written).
- If the CLI is unavailable or fails, falls back to the cached snapshot from
    SQLite (no network).

Entry points recognized by the ModelRegistryRepository:
- run()  (preferred)
- get_models()/fetch_models()/update_models()/refresh_models() also provided for convenience
"""

from __future__ import annotations

import json
import logging
import subprocess  # nosec B404 - required for invoking trusted local 'ollama' CLI (fixed arg list)
import shutil
import os
import stat
from typing import Any, Dict, List
import re
from ..base.logging import get_logger, log_event, LogContext

from ..base.get_models_base import save_provider_models, load_cached_models
from ..base.http import get_httpx_client
from ..base.timeouts import get_timeout_config, operation_timeout
from ..config import get_provider_config
from ..config.defaults import OLLAMA_DEFAULT_HOST

PROVIDER = "ollama"

_logger = get_logger("ollama.models")


def _validate_executable(path: str) -> None:
    """Defensively validate the resolved 'ollama' executable path.

    Requirements:
      * Basename exactly 'ollama'
      * Regular file & user executable
      * Not group/other writable (reduces tampering risk)
    Raises RuntimeError on any violation to allow caller to log & fallback.
    """
    base = os.path.basename(path)
    if base != "ollama":  # pragma: no cover - safety
        raise RuntimeError("resolved executable basename mismatch (expected 'ollama')")
    try:
        st = os.stat(path)
    except OSError as e:  # pragma: no cover - unlikely
        raise RuntimeError(f"cannot stat ollama executable: {e}") from e
    if not stat.S_ISREG(st.st_mode):  # pragma: no cover
        raise RuntimeError("ollama executable is not a regular file")
    if not os.access(path, os.X_OK):  # pragma: no cover
        raise RuntimeError("ollama executable not user-executable")
    if st.st_mode & 0o022:  # group/other write bits
        raise RuntimeError("ollama executable has insecure write permissions (group/other writable)")


def _resolve_ollama_executable() -> str:
    """Resolve and validate the absolute path to the ``ollama`` executable.

    This function performs a secure lookup using ``shutil.which`` and applies
    strict file validations via :func:`_validate_executable`. Any validation
    failure is logged with structured context and re-raised to allow upstream
    fallback handling.

    Returns
    -------
    str
        Absolute, validated path to the ``ollama`` executable.

    Raises
    ------
    FileNotFoundError
        If the ``ollama`` executable cannot be located on PATH.
    RuntimeError
        If validation fails (e.g., permissions, not executable).
    """
    exe_path = shutil.which("ollama")
    if not exe_path:
        raise FileNotFoundError("'ollama' executable not found on PATH")
    abs_path = os.path.abspath(exe_path)
    try:
        _validate_executable(abs_path)
    except Exception as e:  # structured log then propagate
        log_event(
            _logger,
            "ollama.exe.validation_failed",
            LogContext(provider="ollama", model="models"),
            error=str(e),
            path=abs_path,
            operation="list",
            stage="start",
        )
        raise
    return abs_path


def _build_ollama_list_cmd(exe_path: str, json_output: bool) -> List[str]:
    """Construct a whitelisted ``ollama list`` command.

    Parameters
    ----------
    exe_path: str
        Absolute path to the validated ``ollama`` executable.
    json_output: bool
        Whether to include ``--json`` for machine-readable output.

    Returns
    -------
    List[str]
        Command argument vector safe for ``subprocess.run(shell=False)``.
    """
    cmd: List[str] = [exe_path, "list"]
    if json_output:
        cmd.append("--json")
    return cmd


def _run_ollama_command(cmd: List[str], timeout: int) -> str:
    """Execute the provided ``ollama`` command securely and return stdout.

    Uses ``subprocess.run`` with a fixed, validated argument vector, ensuring
    no shell is involved and standard streams are captured to prevent leakage.

    Parameters
    ----------
    cmd: List[str]
        Fully constructed command vector.
    timeout: int
        Timeout in seconds to apply to the process.

    Returns
    -------
    str
        The captured stdout content.
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


def _invoke_ollama_list(json_output: bool, timeout: int) -> str:
    """Invoke the local, trusted ``ollama list`` command and return stdout.

    Enforces secure resolution, fixed argument construction, and safe process
    execution. Honors the caller-supplied timeout to align with the unified
    timeout configuration policy.
    """
    exe = _resolve_ollama_executable()
    cmd = _build_ollama_list_cmd(exe, json_output)
    return _run_ollama_command(cmd, timeout)


def _fetch_via_cli() -> List[Dict[str, Any]]:
    """
    Fetch model listings using 'ollama list' command.
    Tries JSON output first; falls back to parsing table output.
    Returns a list of dicts with at least {'id', 'name'} keys.
    """
    # Try JSON output first (supported on modern ollama)
    cfg = get_timeout_config()
    eff_timeout = int(cfg.start_timeout_seconds)
    try:
        return _fetch_ollama_models_json(eff_timeout)
    except Exception as e:  # log & fallback to table parsing
        logging.getLogger(__name__).warning(
            "ollama list --json failed; falling back to table parse: %s", e, exc_info=True
        )
    # Fallback to parsing table output using a resilient parser
    out = _invoke_ollama_list(json_output=False, timeout=eff_timeout)
    return _parse_ollama_list_table(out)


def _normalize_http_entry(entry: Dict[str, Any]) -> Dict[str, Any]:
    """Return a normalized mapping containing ``id``/``name`` keys.

    Parameters
    ----------
    entry:
        Raw mapping returned by the Ollama HTTP API. Accepts flexible key
        shapes across versions (``name``/``model``/``id``).

    Returns
    -------
    Dict[str, Any]
        Copy of ``entry`` guaranteed to expose ``id`` and ``name`` fields.
    """

    normalized: Dict[str, Any] = dict(entry)
    candidate = (
        entry.get("name")
        or entry.get("model")
        or entry.get("id")
        or entry.get("tag")
        or entry.get("digest")
    )
    text = str(candidate) if candidate is not None else json.dumps(entry, ensure_ascii=False)
    normalized["id"] = text
    normalized["name"] = text
    return normalized


def _fetch_via_http_api() -> List[Dict[str, Any]]:
    """Fetch Ollama models via the local HTTP API fallback.

    Returns a list of normalized model entries when the daemon responds. The
    function reuses the shared pooled HTTP client, applies the standardized
    timeout configuration, and raises any HTTP or parsing errors to allow the
    caller to record structured fallback logs.
    """

    cfg = get_timeout_config()
    host = get_provider_config(PROVIDER).get("host") or OLLAMA_DEFAULT_HOST
    client = get_httpx_client(host, purpose="ollama.models")
    with operation_timeout(cfg.start_timeout_seconds):
        response = client.get("/api/tags")
    response.raise_for_status()
    payload = response.json()
    raw_items = payload.get("models", payload) if isinstance(payload, dict) else payload
    items: List[Dict[str, Any]] = []
    for raw in raw_items or []:
        if isinstance(raw, dict):
            items.append(_normalize_http_entry(raw))
        else:
            text = str(raw)
            items.append({"id": text, "name": text})
    return items


def _log_fetch_event(
    event: str,
    *,
    stage: str,
    fallback_used: bool,
    failure_class: str | None,
    **extra: Any,
) -> None:
    """Emit a structured log entry for model refresh operations."""

    log_event(
        _logger,
        event,
        LogContext(provider=PROVIDER, model=None),
        operation="models.refresh",
        stage=stage,
        fallback_used=fallback_used,
        failure_class=failure_class or "None",
        **extra,
    )


def _split_table_columns(line: str) -> List[str]:
    """Split a table line by two-or-more spaces preserving token groups.

    The ``ollama list`` table pads columns with at least two spaces, while
    column values themselves may contain single spaces (e.g., ``"2 weeks ago"``).
    Using ``\\s{2,}`` yields robust column segmentation across environments.

    Parameters
    ----------
    line: str
        Single line from the table output.

    Returns
    -------
    List[str]
        Segmented column values with surrounding whitespace trimmed.
    """
    return [c.strip() for c in re.split(r"\s{2,}", line.strip()) if c.strip()]


def _parse_header_map(header_line: str) -> tuple[bool, Dict[str, int]]:
    """Return (has_header, column_index_map) from the header line.

    When headers are present, typical columns are ``NAME``, ``ID``, ``SIZE``,
    and ``MODIFIED``. The returned mapping is uppercased for stable lookup.
    """
    cols = _split_table_columns(header_line)
    has_header = any(col.upper() == "NAME" for col in cols)
    return has_header, {col.upper(): idx for idx, col in enumerate(cols)} if has_header else ({}, {})[1]


def _entry_from_columns(cols: List[str], col_index: Dict[str, int]) -> Dict[str, Any]:
    """Build a normalized entry dict from split columns and optional header map.

    Ensures ``id`` and ``name`` are included. Optionally adds ``id_digest``,
    ``size``, and ``modified`` when the corresponding headers are available.
    """
    if col_index and "NAME" in col_index and len(cols) > col_index["NAME"]:
        name = cols[col_index["NAME"]]
    else:
        name = cols[0]

    entry: Dict[str, Any] = {"id": name, "name": name}
    if col_index:
        if "ID" in col_index and len(cols) > col_index["ID"]:
            entry["id_digest"] = cols[col_index["ID"]]
        if "SIZE" in col_index and len(cols) > col_index["SIZE"]:
            entry["size"] = cols[col_index["SIZE"]]
        if "MODIFIED" in col_index and len(cols) > col_index["MODIFIED"]:
            entry["modified"] = cols[col_index["MODIFIED"]]
    return entry


def _parse_ollama_list_table(output: str) -> List[Dict[str, Any]]:
    """Parse human-readable ``ollama list`` table output into model entries.

    Delegates to focused helpers to keep complexity and LOC low while being
    resilient to spacing variations and optional columns.
    """
    lines = [ln.rstrip() for ln in (output or "").splitlines() if ln.strip()]
    if not lines:
        return []

    has_header, col_index = _parse_header_map(lines[0])
    data_lines = lines[1:] if has_header else lines

    items: List[Dict[str, Any]] = []
    for ln in data_lines:
        cols = _split_table_columns(ln)
        if not cols:
            continue
        items.append(_entry_from_columns(cols, col_index))

    return items


def _fetch_ollama_models_json(eff_timeout: int) -> List[Dict[str, Any]]:
    """Return models parsed from `ollama list --json` output.

    Parameters
    ----------
    eff_timeout: int
        Timeout (seconds) applied to the subprocess invocation.

    Returns
    -------
    List[Dict[str, Any]]
        Normalized model entries each containing at least 'id' and 'name'.
    """
    out = _invoke_ollama_list(json_output=True, timeout=eff_timeout)
    data = json.loads(out)
    raw = data.get("models", data) if isinstance(data, dict) else data
    items: List[Dict[str, Any]] = []
    for it in raw or []:
        if isinstance(it, dict):
            name = it.get("name") or it.get("model") or str(it)
            items.append({"id": name, "name": name, **it})
        else:
            items.append({"id": str(it), "name": str(it)})
    return items


def run() -> List[Dict[str, Any]]:
    """Return the freshest available Ollama model listing.

    The function prefers the local CLI, falls back to the HTTP API when the CLI
    is missing/unavailable, and ultimately returns the cached snapshot if both
    live strategies fail. Successful live refreshes persist the normalized
    snapshot via :func:`save_provider_models` for reuse.
    """

    try:
        cli_items = _fetch_via_cli()
    except Exception as exc:  # pragma: no cover - defensive logging path
        _log_fetch_event(
            "ollama.models.cli_failed",
            stage="start",
            fallback_used=True,
            failure_class=exc.__class__.__name__,
            error=str(exc),
        )
        cli_items = []
    else:
        if cli_items:
            save_provider_models(
                PROVIDER,
                cli_items,
                fetched_via="ollama_list",
                metadata={"source": "ollama_cli"},
            )
            _log_fetch_event(
                "ollama.models.cli_success",
                stage="finalize",
                fallback_used=False,
                failure_class="None",
                fetched=len(cli_items),
            )
            return cli_items
        _log_fetch_event(
            "ollama.models.cli_empty",
            stage="start",
            fallback_used=True,
            failure_class="None",
            fetched=0,
        )

    try:
        http_items = _fetch_via_http_api()
    except Exception as exc:  # pragma: no cover - defensive logging path
        _log_fetch_event(
            "ollama.models.http_failed",
            stage="start",
            fallback_used=True,
            failure_class=exc.__class__.__name__,
            error=str(exc),
        )
    else:
        if http_items:
            save_provider_models(
                PROVIDER,
                http_items,
                fetched_via="ollama_http",
                metadata={"source": "ollama_http"},
            )
            _log_fetch_event(
                "ollama.models.http_success",
                stage="finalize",
                fallback_used=True,
                failure_class="None",
                fetched=len(http_items),
            )
            return http_items
        _log_fetch_event(
            "ollama.models.http_empty",
            stage="finalize",
            fallback_used=True,
            failure_class="None",
            fetched=0,
        )

    snap = load_cached_models(PROVIDER)
    cached = [m.to_dict() for m in snap.models]
    _log_fetch_event(
        "ollama.models.cache_used",
        stage="finalize",
        fallback_used=True,
        failure_class="None",
        fetched=len(cached),
    )
    return cached


# Aliases for repository compatibility
def get_models() -> List[Dict[str, Any]]:
    """
    Gets the list of available Ollama models.

    This function invokes the preferred entrypoint to retrieve and return the current model list.
    """
    return run()


def fetch_models() -> List[Dict[str, Any]]:
    """
    Fetches the list of available Ollama models.

    This function invokes the preferred entrypoint to retrieve and return the current model list.
    """
    return run()


def update_models() -> List[Dict[str, Any]]:
    """
    Updates the list of available Ollama models.

    This function invokes the preferred entrypoint to refresh and return the current model list.
    """
    return run()


def refresh_models() -> List[Dict[str, Any]]:
    """
    Refreshes the list of available Ollama models.

    This function calls the preferred entrypoint to update and return the current model list.
    """
    return run()


if __name__ == "__main__":
    models = run()
    print(f"[ollama] loaded {len(models)} models")
