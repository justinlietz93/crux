"""Anthropic model listing fetcher.

Purpose:
    Fetches available models from Anthropic via the SDK when possible, then
    persists the results using the shared model registry helpers. When the SDK
    is unavailable, an API key is missing, or the fetch fails, the function
    falls back to the cached snapshot on disk (no network).

External dependencies:
    - ``anthropic`` Python SDK. No subprocess invocations are used.

Fallback semantics:
    - On any live fetch failure, return the cached snapshot via
      ``load_cached_models``. We emit a single fallback log event for traceability
      and do not mask the underlying exception class in logs.

Timeout strategy:
    - Uses ``get_timeout_config()`` and guards the blocking start phase of the
      SDK listing call with ``operation_timeout``. No hard-coded numeric literals
      are introduced.

Entry points recognized by the ``ModelRegistryRepository``:
    - ``run()`` (preferred)
    - ``get_models()`` / ``fetch_models()`` / ``update_models()`` / ``refresh_models()``

Note:
    Persistence is handled by ``save_provider_models`` which writes to the
    SQLite-backed model registry (DB-first; no JSON cache file is written).
"""


from __future__ import annotations

from typing import Any, Dict, List, Optional
from contextlib import suppress

try:
    import anthropic  # anthropic>=0.49.0 recommended
except Exception:
    anthropic = None  # type: ignore

from ..base.get_models_base import save_provider_models, load_cached_models
from ..base.interfaces_parts import HasData, HasId, HasName
from ..base.repositories.keys import KeysRepository
from ..base.logging import LogContext, get_logger, normalized_log_event
from ..base.resilience.retry import RetryConfig, retry
from ..base.errors import ErrorCode, classify_exception
from ..base.timeouts import get_timeout_config, operation_timeout
from ..config import get_provider_config


PROVIDER = "anthropic"
_LOGGER = get_logger("providers.anthropic.models")


def _as_id_and_name(item: Any) -> tuple[str, str]:
    """Project an arbitrary SDK item into ``(id, name)``.

    The function prefers structural Protocols first, then dictionary keys,
    and finally falls back to ``str(item)``. This removes brittle getattr
    chains while remaining resilient across SDK versions.

    Parameters:
        item: An SDK model descriptor (object or mapping).

    Returns:
        Tuple ``(id, name)`` where both are non-empty strings.
    """
    # Structural first (prefer id/name when available)
    if isinstance(item, HasId):
        iid = item.id
        nm = item.name if isinstance(item, HasName) else iid
        return (iid, nm)
    if isinstance(item, HasName):
        nm = item.name
        return (nm, nm)

    # Mapping fallback
    if isinstance(item, dict):
        iid = item.get("id") or item.get("name")
        nm = item.get("name") or iid
        s = str(item)
        return (str(iid or s), str(nm or s))

    # Last resort
    s = str(item)
    return (s, s)


def _fetch_via_sdk(api_key: str) -> List[Any]:
    """Fetch model listings using the Anthropic SDK.

    Parameters:
        api_key: Anthropic API key used to initialize the SDK client.

    Returns:
        A list of raw SDK items (objects or dicts) describing models.

    Raises:
        RuntimeError: If the SDK is missing or a listing method cannot be found.
    """
    if anthropic is None:
        raise RuntimeError("anthropic SDK not available")

    # Prefer modern initialization
    client = getattr(anthropic, "Anthropic", None)
    if client is None:
        raise RuntimeError("Anthropic.Anthropic class not found in SDK")

    client = client(api_key=api_key)  # type: ignore[call-arg]

    # Modern clients expose models.list()
    models_attr = getattr(client, "models", None)
    list_fn = getattr(models_attr, "list", None)
    if callable(list_fn):
        resp = list_fn()
        # Prefer structural ``HasData``; fallback to mapping
        if isinstance(resp, HasData):
            data = resp.data
        elif isinstance(resp, dict):
            data = resp.get("data", [])
        else:
            data = None
        return list(data or [])

    # Fallback: try attribute access commonly used in older SDKs
    models_attr = getattr(client, "models", None)
    if callable(models_attr):
        with suppress(Exception):  # graceful fallback if older SDK behavior differs
            resp = models_attr()  # type: ignore[call-arg]
            if isinstance(resp, HasData):
                data = resp.data
            elif isinstance(resp, dict):
                data = resp.get("data", [])
            else:
                data = None
            return list(data or [])

    raise RuntimeError("Anthropic SDK does not expose a models listing in this version")


def _build_retry_config(ctx: LogContext) -> RetryConfig:
    """Construct a retry configuration for the models fetch path.

    Parameters:
        ctx: ``LogContext`` carrying provider/model identifiers for logs.

    Returns:
        A ``RetryConfig`` with attempt logging that emits normalized events.
    """
    retry_cfg_raw = {}
    try:
        retry_cfg_raw = get_provider_config(PROVIDER).get("retry", {}) or {}
    except Exception:
        retry_cfg_raw = {}

    max_attempts = int(retry_cfg_raw.get("max_attempts", 3))
    delay_base = float(retry_cfg_raw.get("delay_base", 2.0))

    def _attempt_logger(*, attempt: int, max_attempts: int, delay, error):  # type: ignore[override]
        normalized_log_event(
            _LOGGER,
            "retry.attempt",
            ctx,
            phase="start",
            attempt=attempt,
            max_attempts=max_attempts,
            delay=delay,
            error_code=(getattr(error, "code", None).value if getattr(error, "code", None) else None),
            will_retry=bool(error and delay is not None),
            tokens=None,
            emitted=None,
        )

    return RetryConfig(max_attempts=max_attempts, delay_base=delay_base, attempt_logger=_attempt_logger)


def _resolve_key() -> Optional[str]:
    """Resolve the Anthropic API key from the keys repository.

    Returns:
        Optional[str]: The API key or ``None`` if not configured.
    """
    return KeysRepository().get_api_key(PROVIDER)


def run() -> List[Dict[str, Any]]:  # sourcery skip: none-compare
    """Preferred entrypoint for retrieving Anthropic model listings.

    Behavior:
        - Attempts online fetch using the Anthropic SDK, guarded by start-phase
          timeout and retry.
        - On success: persists the raw items to the provider cache and returns a
          list of simple dicts with ``id`` and ``name`` keys.
        - On any failure (missing SDK/key, timeout, transient errors): falls back
          to returning the cached snapshot, emitting a single fallback log event.

    Returns:
        List[Dict[str, Any]]: Simplified list of models suitable for registry use.
    """
    ctx = LogContext(provider=PROVIDER, model="model-listing")
    normalized_log_event(
        _LOGGER,
        "models.start",
        ctx,
        phase="start",
        fallback_used=False,
        tokens=None,
        emitted=None,
        attempt=None,
        error_code=None,
    )

    key = _resolve_key()
    if not key or anthropic is None:
        reason = "anthropic_sdk_unavailable" if key else "missing_api_key"
        normalized_log_event(
            _LOGGER,
            "models.error",
            ctx,
            phase="start",
            error=reason,
            error_code=(
                None
                if key
                else ErrorCode.AUTH.value
            ),
            tokens=None,
            emitted=None,
            attempt=None,
        )
        snap = load_cached_models(PROVIDER)
        normalized_log_event(
            _LOGGER,
            "models.fallback",
            ctx,
            phase="finalize",
            fallback_used=True,
            cached_count=len(snap.models),
            error_code=None,
        )
        return [{"id": m.id, "name": m.name} for m in snap.models]

    retry_cfg = _build_retry_config(ctx)
    timeout_cfg = get_timeout_config()
    try:
        def _do_fetch():
            with operation_timeout(timeout_cfg.start_timeout_seconds):
                return _fetch_via_sdk(key)

        items = retry(retry_cfg)(_do_fetch)()
        save_provider_models(PROVIDER, items, fetched_via="api", metadata={"source": "anthropic_sdk"})
        out: List[Dict[str, Any]] = []
        for it in items:
            mid, name = _as_id_and_name(it)
            out.append({"id": mid, "name": name})
        normalized_log_event(
            _LOGGER,
            "models.end",
            ctx,
            phase="finalize",
            fetched_count=len(out),
            fallback_used=False,
            error_code=None,
        )
        return out
    except Exception as e:
        code = classify_exception(e)
        normalized_log_event(
            _LOGGER,
            "models.error",
            ctx,
            phase="finalize",
            error=str(e),
            failure_class=e.__class__.__name__,
            error_code=code.value,
        )
        snap = load_cached_models(PROVIDER)
        normalized_log_event(
            _LOGGER,
            "models.fallback",
            ctx,
            phase="finalize",
            fallback_used=True,
            cached_count=len(snap.models),
            error_code=None,
        )
        return [{"id": m.id, "name": m.name} for m in snap.models]


# Aliases for repository compatibility
def get_models() -> List[Dict[str, Any]]:
    return run()


def fetch_models() -> List[Dict[str, Any]]:
    return run()


def update_models() -> List[Dict[str, Any]]:
    return run()


def refresh_models() -> List[Dict[str, Any]]:
    return run()


if __name__ == "__main__":
    models = run()
    print(f"[anthropic] loaded {len(models)} models")
