from __future__ import annotations

import os
import time
from contextlib import suppress
from typing import Any, Dict, Optional, Tuple
from crux_providers.base.interfaces_parts.response_meta import (
    HasMetaExtra,
    HasExtra,
)
from datetime import datetime, timezone

from crux_providers.base.models import ChatRequest
from crux_providers.persistence.interfaces.repos import (
    IUnitOfWork,
    MetricEntry,
)

from . import db as svcdb
from crux_providers.config.env import (
    ENV_MAP,
    is_placeholder,
    get_env_var_name,
    resolve_provider_key,
    set_canonical_env_if_missing,
)
# Input-size guard logic now lives in chat_request_build; no direct helpers here.
from .chat_request_build import to_messages, build_chat_request


_DOTENV_LOADED: bool = False


def _env_has_valid_key(env_key: Optional[str]) -> bool:
    """Return True if the given environment variable is set to a non-placeholder value.

    Parameters
    ----------
    env_key: Optional[str]
        The name of the environment variable to inspect. ``None`` short-circuits to ``False``.

    Returns
    -------
    bool
        ``True`` when the variable exists and is not a placeholder token; otherwise ``False``.
    """
    if not env_key:
        return False
    val = os.environ.get(env_key)
    return bool(val) and not is_placeholder(val)


def _promote_alias_if_present(provider: str) -> bool:
    """Promote an alias env var to the canonical provider env name if found.

    This inspects alias environment variable names for the provider using
    ``resolve_provider_key`` and, if present, ensures the canonical variable is
    set via ``set_canonical_env_if_missing``.

    Parameters
    ----------
    provider: str
        Provider identifier (case-insensitive).

    Returns
    -------
    bool
        ``True`` if an alias key was found and promoted; otherwise ``False``.
    """
    key_from_env, _ = resolve_provider_key(provider)
    if key_from_env:
        set_canonical_env_if_missing(provider, key_from_env)
        return True
    return False


def _load_key_from_uow(provider: str, uow: Optional[IUnitOfWork]) -> Optional[str]:
    """Attempt to fetch the provider API key via the supplied UnitOfWork.

    Parameters
    ----------
    provider: str
        Provider identifier.
    uow: Optional[IUnitOfWork]
        Unit of work that exposes a ``keys`` repository.

    Returns
    -------
    Optional[str]
        The key if available; otherwise ``None``. Exceptions are suppressed to
        keep this a best-effort helper.
    """
    if uow is None:
        return None
    with suppress(Exception):
        return uow.keys.get_api_key(provider.lower()) or uow.keys.get_api_key(provider)
    return None


def _load_legacy_key(provider: str) -> Optional[str]:
    """Best-effort read of legacy key from the SQLite helper without forcing init.

    Parameters
    ----------
    provider: str
        Provider identifier.

    Returns
    -------
    Optional[str]
        The key if found; otherwise ``None``. Any exceptions are suppressed.
    """
    with suppress(Exception):
        keys = svcdb.load_keys()
        return keys.get(provider.lower()) or keys.get(provider)
    return None


def _try_load_dotenv() -> None:
    """Load a simple ``.env`` file into ``os.environ`` if present.

    This lightweight loader avoids adding a new dependency. It supports basic
    ``KEY=VALUE`` pairs and quoted values. It is intentionally conservative:
    - Ignores blank lines and lines starting with ``#``.
    - Does not perform variable interpolation.
    - Does not override variables that are already set in the environment.

    Search order:
    1) Current working directory (recommended to run CLI from repo root)
    2) One level up from CWD (useful when invoked from a subfolder)

    The loader is idempotent — it runs at most once per process.
    """
    global _DOTENV_LOADED
    if _DOTENV_LOADED:
        return
    candidates = [
        os.path.join(os.getcwd(), ".env"),
        os.path.abspath(os.path.join(os.getcwd(), "..", ".env")),
    ]
    for path in candidates:
        try:
            if not os.path.isfile(path):
                continue
            with open(path, "r", encoding="utf-8") as fh:
                for raw_line in fh:
                    line = raw_line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, val = line.split("=", 1)
                    key = key.strip()
                    val = val.strip().strip("'\"")
                    # Overwrite if not set or a placeholder value is present
                    if key and (key not in os.environ or is_placeholder(os.environ.get(key))):
                        os.environ[key] = val
            _DOTENV_LOADED = True
            return
        except Exception:
            # Silent best-effort; loading .env must never break execution
            _DOTENV_LOADED = True
            return


def _truthy(val: Optional[str]) -> bool:
    """Return True when an environment-like string represents a truthy value.

    Accepts common boolean encodings: "1", "true", "yes", "on" (case-insensitive).
    This helper avoids sprinkling string normalization logic across the module.
    """
    return str(val or "").strip().lower() in {"1", "true", "yes", "on"}


def _should_load_dotenv() -> bool:
    """Determine whether .env autoload should occur in this process.

    Rules (in priority order):
    - If ``CRUX_PROVIDERS_ENABLE_DOTENV`` is truthy → allow.
    - Else if running under pytest (``PYTEST_CURRENT_TEST`` present) → skip, to honor
      tests that explicitly clear API key env vars and expect a failure path.
    - Else if ``CRUX_PROVIDERS_DISABLE_DOTENV`` is truthy → skip.
    - Otherwise → allow.
    """
    if _truthy(os.environ.get("CRUX_PROVIDERS_ENABLE_DOTENV")):
        return True
    if "PYTEST_CURRENT_TEST" in os.environ:
        return False
    if _truthy(os.environ.get("CRUX_PROVIDERS_DISABLE_DOTENV")):
        return False
    return True


def set_env_for_provider(provider: str, uow: Optional[IUnitOfWork] = None) -> None:
    """Resolve and export provider API key without requiring DB setup.

    Behavior (short-circuit on first success):
    1) If the canonical env var is already set to a non-placeholder, stop.
    2) Attempt a lightweight ``.env`` load, then re-check (1).
    3) Promote any alias env var to the canonical name if present.
    4) Consult the provided UnitOfWork's keys repo.
    5) Fallback to legacy SQLite helper (best-effort; no forced init).

    Parameters
    ----------
    provider: str
        Provider identifier (case-insensitive).
    uow: Optional[IUnitOfWork]
        Unit of work supplying key repository.
    """
    env_key = get_env_var_name(provider)
    if not env_key:
        return

    # 1) Already set in environment (non-placeholder)
    if _env_has_valid_key(env_key):
        return

    # 2) Try loading from .env then re-check (gated for test environments)
    if _should_load_dotenv():
        _try_load_dotenv()
    if _env_has_valid_key(env_key):
        return

    # 3) Promote alias to canonical if found
    if _promote_alias_if_present(provider):
        return

    def _should_use_db_fallback() -> bool:
        """Return True if DB-based key lookups should be attempted.

        Disabled by default under pytest to keep tests deterministic. Can be
        explicitly enabled or disabled via environment flags.
        """
        if _truthy(os.environ.get("CRUX_PROVIDERS_ENABLE_DB_FALLBACK")):
            return True
        if "PYTEST_CURRENT_TEST" in os.environ:
            return False
        if _truthy(os.environ.get("CRUX_PROVIDERS_DISABLE_DB_FALLBACK")):
            return False
        return True

    if _should_use_db_fallback():
        # 4) UoW-backed lookup
        key = _load_key_from_uow(provider, uow)
        if key:
            set_canonical_env_if_missing(provider, key)
            return

        # 5) Legacy helper fallback (best-effort)
        key = _load_legacy_key(provider)
        if key:
            set_canonical_env_if_missing(provider, key)


# build_chat_request and to_messages are re-exported from chat_request_build


def extract_tokens(meta_extra: Any) -> Tuple[Optional[int], Optional[int]]:
    """Extract token usage counts from metadata.

    Retrieves the number of input and output tokens from a metadata dictionary, supporting multiple possible key names.

    Args:
        meta_extra: Metadata dictionary potentially containing token usage information.

    Returns:
        Tuple[Optional[int], Optional[int]]: A tuple containing the input and output token counts, or None if unavailable.
    """
    extra = meta_extra if isinstance(meta_extra, dict) else {}
    usage = extra.get("usage") if isinstance(extra.get("usage"), dict) else None
    if usage:
        tokens_in = usage.get("prompt_tokens") or usage.get("input_tokens")
        tokens_out = usage.get("completion_tokens") or usage.get("output_tokens")
    else:
        tokens_in = extra.get("tokens_prompt")
        tokens_out = extra.get("tokens_completion")
    ti = tokens_in if isinstance(tokens_in, int) else None
    to = tokens_out if isinstance(tokens_out, int) else None
    return ti, to


def record_metric_safe(
    *,
    provider: str,
    model: str,
    duration_ms: int,
    status: str,
    error_type: Optional[str] = None,
    tokens_in: Optional[int] = None,
    tokens_out: Optional[int] = None,
    uow: Optional[IUnitOfWork] = None,
) -> None:
    """Record a metric entry using DI if available, else legacy DB helper.

    Parameters mirror legacy implementation; when a unit of work is supplied we
    translate the call into a `MetricEntry` and append it via `IMetricsRepo`.
    Any exception is suppressed to avoid impacting the critical path.
    """
    with suppress(Exception):
        if uow is not None:
            entry = MetricEntry(
                provider=provider,
                model=model,
                latency_ms=duration_ms,
                tokens_prompt=tokens_in,
                tokens_completion=tokens_out,
                success=(status == "ok"),
                error_code=error_type,
                # Use timezone-aware UTC now to avoid deprecated utcnow()
                created_at=datetime.now(timezone.utc),
            )
            uow.metrics.add_metric(entry)
        else:
            svcdb.record_metric(
                provider=provider,
                model=model,
                duration_ms=duration_ms,
                status=status,
                error_type=error_type,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
            )


def _get_meta_extra(resp: Any) -> Dict[str, Any]:
    """Safely retrieve ``resp.meta.extra`` as a dictionary.

    This helper removes the need for dynamic ``getattr`` access when extracting
    token usage from provider responses. It tolerates missing attributes and
    non-dict values, returning an empty dict in those cases.

    Parameters
    ----------
    resp: Any
        Provider response object that may contain a ``meta`` attribute with an
        ``extra`` dictionary.

    Returns
    -------
    Dict[str, Any]
        The extracted ``extra`` dictionary if present and well-formed; otherwise
        an empty dict.
    """
    try:
        # Prefer structural typing via Protocols to avoid getattr chains
        if isinstance(resp, HasMetaExtra):
            meta = resp.meta  # type: ignore[assignment]
        else:
            return {}

        if isinstance(meta, dict):
            extra = meta.get("extra", {})
        elif isinstance(meta, HasExtra):
            extra = meta.extra  # type: ignore[assignment]
        else:
            return {}

        return extra if isinstance(extra, dict) else {}
    except Exception:
        return {}


def chat_with_metrics(
    adapter: Any,
    req: ChatRequest,
    *,
    provider: str,
    model: str,
    uow: Optional[IUnitOfWork] = None,
):
    """Execute chat, record metrics, return (response, error).

    Accepts optional UnitOfWork for DI-based metrics persistence.
    """
    started = time.perf_counter()
    try:
        resp = adapter.chat(req)
        duration_ms = int((time.perf_counter() - started) * 1000)
        tokens_in, tokens_out = extract_tokens(_get_meta_extra(resp))
        record_metric_safe(
            provider=provider,
            model=model,
            duration_ms=duration_ms,
            status="ok",
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            uow=uow,
        )
        return resp, None
    except Exception as e:  # pragma: no cover
        duration_ms = int((time.perf_counter() - started) * 1000)
        record_metric_safe(
            provider=provider,
            model=model,
            duration_ms=duration_ms,
            status="error",
            error_type=type(e).__name__,
            uow=uow,
        )
        return None, e


def mask_keys_env(raw: Dict[str, str]) -> Dict[str, bool]:
    """Map provider environment keys to their presence status.

    Returns a dictionary indicating whether each provider's environment variable is set.

    Args:
        raw: A dictionary mapping environment variable names to their values.

    Returns:
        Dict[str, bool]: A dictionary mapping provider names to a boolean indicating if the key is set.
    """
    provider_to_env = {v.lower(): k for v, k in ENV_MAP.items()}
    return {
        provider_to_env[p.lower()]: bool(k)
        for p, k in raw.items()
        if provider_to_env.get(p.lower())
    }


__all__ = [
    "ENV_MAP",
    "set_env_for_provider",
    "to_messages",
    "build_chat_request",
    "extract_tokens",
    "record_metric_safe",
    "chat_with_metrics",
    "mask_keys_env",
]
