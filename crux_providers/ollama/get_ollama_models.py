"""Crux Ollama model discovery utilities.

Purpose
    Provide a deterministic entrypoint for refreshing the Ollama provider's
    locally available model metadata that remains compatible with the
    model-registry repository helpers.

External Dependencies
    * Local ``ollama`` CLI binary accessed through ``subprocess``.
    * Local Ollama HTTP API served at ``/api/tags`` via ``get_httpx_client``.

Fallback Semantics
    1. Invoke ``ollama list --json`` and normalize the response.
    2. On JSON failure, retry with table parsing of ``ollama list`` output.
    3. If the CLI is unavailable or produces no entries, query the HTTP API.
    4. Persist successful live refreshes and otherwise return the cached
       snapshot from SQLite storage.

Timeout Strategy
    All blocking operations reuse ``get_timeout_config().start_timeout_seconds``
    and enforce it via ``operation_timeout`` as well as the subprocess timeout
    argument to ensure consistent cancellation semantics across fallbacks.
"""

from __future__ import annotations

import json
import math
from typing import Any, Dict, List
from ..base.logging import get_logger, log_event, LogContext

from ..base.get_models_base import save_provider_models, load_cached_models
from ..base.http import get_httpx_client
from ..base.timeouts import get_timeout_config, operation_timeout
from ..config import get_provider_config
from ..config.defaults import OLLAMA_DEFAULT_HOST
from ._cli import build_ollama_list_cmd, resolve_ollama_executable, run_ollama_command
from ._table_parser import parse_ollama_list_table as _parse_ollama_list_table

PROVIDER = "ollama"

_logger = get_logger("ollama.models")


def _invoke_ollama_list(json_output: bool, timeout: int) -> str:
    """Invoke the trusted ``ollama list`` command and return stdout.

    Parameters
    ----------
    json_output: bool
        Whether to request machine-readable JSON (`True`) or table output.
    timeout: int
        Timeout in seconds applied to the CLI invocation.

    Returns
    -------
    str
        Raw stdout produced by the ``ollama list`` command.

    Raises
    ------
    RuntimeError
        If the resolved executable fails security validation checks.
    FileNotFoundError
        If the executable cannot be located on ``PATH``.
    subprocess.SubprocessError
        If the command exits with a non-zero code or times out.
    """

    try:
        exe = resolve_ollama_executable()
    except RuntimeError as exc:
        log_event(
            _logger,
            "ollama.exe.validation_failed",
            LogContext(provider=PROVIDER, model="models"),
            error=str(exc),
            path=getattr(exc, "path", "<unresolved>"),
            operation="list",
            stage="start",
        )
        raise

    cmd = build_ollama_list_cmd(exe, json_output)
    return run_ollama_command(cmd, timeout)


def _fetch_via_cli() -> List[Dict[str, Any]]:
    """Return model listings discovered via the trusted local CLI.

    The helper retrieves the effective timeout configuration once, enforces it
    with :func:`operation_timeout`, and performs a JSON-first discovery
    followed by a table-parse fallback. Structured logging captures any JSON
    failure so that the caller can make an informed decision before querying
    secondary channels.

    Returns
    -------
    List[Dict[str, Any]]
        Normalized model metadata containing at least ``id`` and ``name``.

    Raises
    ------
    Exception
        Propagates subprocess or parsing errors that occur during the table
        fallback so the caller can record the failure and continue to other
        strategies.
    """

    cfg = get_timeout_config()
    timeout_seconds = float(cfg.start_timeout_seconds)
    subprocess_timeout = max(1, int(math.ceil(timeout_seconds)))

    try:
        with operation_timeout(timeout_seconds):
            return _fetch_ollama_models_json(subprocess_timeout)
    except Exception as exc:
        _log_fetch_event(
            "ollama.models.cli_json_failed",
            stage="mid_stream",
            fallback_used=True,
            failure_class=exc.__class__.__name__,
            error=str(exc),
        )

    with operation_timeout(timeout_seconds):
        output = _invoke_ollama_list(json_output=False, timeout=subprocess_timeout)
    return _parse_ollama_list_table(output)


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


def _fetch_ollama_models_json(eff_timeout: int) -> List[Dict[str, Any]]:
    """Return models parsed from ``ollama list --json`` output.

    Parameters
    ----------
    eff_timeout: int
        Timeout (seconds) applied to the subprocess invocation.

    Returns
    -------
    List[Dict[str, Any]]
        Normalized model entries each containing at least ``id`` and ``name``.

    Raises
    ------
    json.JSONDecodeError
        If the CLI returns malformed JSON that cannot be parsed.
    subprocess.SubprocessError
        If the CLI invocation fails or times out before producing output.
    """

    with operation_timeout(eff_timeout):
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
    """Return the available Ollama models.

    Returns
    -------
    List[Dict[str, Any]]
        Normalized model records supplied by :func:`run`.

    Notes
    -----
    Delegates to :func:`run` to ensure consistent fallback handling and
    persistence side effects.
    """
    return run()


def fetch_models() -> List[Dict[str, Any]]:
    """Fetch and return the available Ollama models.

    Returns
    -------
    List[Dict[str, Any]]
        Normalized model records supplied by :func:`run`.

    Notes
    -----
    Exists for compatibility with legacy repository interfaces that expect a
    ``fetch_models`` symbol.
    """
    return run()


def update_models() -> List[Dict[str, Any]]:
    """Refresh the Ollama model snapshot and return the entries.

    Returns
    -------
    List[Dict[str, Any]]
        Normalized model records supplied by :func:`run`.

    Notes
    -----
    Provided to accommodate historical call sites that invoke
    ``update_models`` explicitly.
    """
    return run()


def refresh_models() -> List[Dict[str, Any]]:
    """Refresh and return the Ollama model metadata.

    Returns
    -------
    List[Dict[str, Any]]
        Normalized model records supplied by :func:`run`.

    Notes
    -----
    Maintains compatibility with provider registries that reference a
    ``refresh_models`` helper.
    """
    return run()


if __name__ == "__main__":
    models = run()
    print(f"[ollama] loaded {len(models)} models")
