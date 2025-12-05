"""
OpenAI models fetcher.

DB-first: lists models via the OpenAI SDK, normalizes, and persists to the
SQLite model registry. Falls back to cached registry rows when online refresh
fails; no JSON registries are used.
"""

from __future__ import annotations

import io
import json
import os
import sys
from contextlib import suppress
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from openai import OpenAI  # openai>=1.0.0
except Exception:  # pragma: no cover - SDK may be absent in some envs
    OpenAI = None  # type: ignore

from ..base.capabilities import merge_capabilities, normalize_modalities
from ..base.get_models_base import load_cached_models, save_provider_models
from ..base.interfaces_parts.has_data import HasData
from ..base.logging import LogContext, get_logger, normalized_log_event
from ..base.models import ModelInfo
from ..base.repositories.keys import KeysRepository
from ..base.timeouts import get_timeout_config, operation_timeout

PROVIDER = "openai"
_logger = get_logger("providers.openai.models")
OBSERVED_CAPS_PATH = Path(__file__).resolve().parent / "openai-observed-capabilities.json"

# Force UTF-8 to avoid UnicodeEncodeError on Windows consoles.
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
os.environ.setdefault("PYTHONUTF8", "1")
try:
    if sys.stdout and hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    if sys.stderr and hasattr(sys.stderr, "buffer"):
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
except Exception:
    pass


def _load_observed_fallback() -> List[Dict[str, Any]]:
    try:
        with OBSERVED_CAPS_PATH.open("r", encoding="utf-8") as f:
            data = json.load(f) or {}
        return [{"id": mid, "name": mid} for mid in data.keys()]
    except Exception:
        return []


def _persist_fallback(models: List[Dict[str, Any]], source: str) -> None:
    if not models:
        return
    save_provider_models(
        PROVIDER,
        [ModelInfo(id=m["id"], name=m["name"], provider=PROVIDER) for m in models],
        fetched_via=source,
        metadata={"source": source},
    )


def _fetch_via_sdk(api_key: str) -> List[Any]:
    if not OpenAI:
        raise RuntimeError("openai SDK not available")
    client = OpenAI(api_key=api_key)
    resp = client.models.list()
    if isinstance(resp, HasData):
        data = resp.data  # type: ignore[assignment]
    elif isinstance(resp, dict):
        data = resp.get("data", [])
    else:
        data = getattr(resp, "data", None)
    return list(data or [])


def _resolve_key() -> Optional[str]:
    return KeysRepository().get_api_key(PROVIDER)


def run() -> List[Dict[str, Any]]:
    key = _resolve_key()
    if not key:
        normalized_log_event(
            _logger,
            "models.list.fallback",
            LogContext(provider=PROVIDER, model="models"),
            phase="start",
            attempt=None,
            error_code=None,
            emitted=False,
            provider=PROVIDER,
            operation="fetch_models",
            stage="start",
            failure_class="MissingAPIKey",
            fallback_used=True,
        )
        cached = _cached_models()
        if cached:
            return cached
        observed = _load_observed_fallback()
        _persist_fallback(observed, source="observed_fallback_missing_key")
        return observed

    online = _refresh_online(key)
    if online:
        return online
    cached = _cached_models()
    if cached:
        return cached
    observed = _load_observed_fallback()
    _persist_fallback(observed, source="observed_fallback_sdk_missing")
    return observed


# -------------------- Helpers --------------------

def _cached_models() -> List[Dict[str, Any]]:
    snap = load_cached_models(PROVIDER)
    cached = [{"id": m.id, "name": m.name} for m in snap.models]
    if cached:
        return cached
    observed = _load_observed_fallback()
    if observed:
        _persist_fallback(observed, source="observed_fallback_cache_miss")
    return observed


def _refresh_online(api_key: str) -> Optional[List[Dict[str, Any]]]:
    if not OpenAI:
        normalized_log_event(
            _logger,
            "models.list.fallback",
            LogContext(provider=PROVIDER, model="models"),
            phase="start",
            attempt=None,
            error_code=None,
            emitted=False,
            provider=PROVIDER,
            operation="fetch_models",
            stage="start",
            failure_class="SDKUnavailable",
            fallback_used=True,
        )
        return None

    items: Optional[List[Any]] = None
    attempts = 0
    while attempts < 2:
        attempts += 1
        try:
            timeout_cfg = get_timeout_config()
            with operation_timeout(timeout_cfg.start_timeout_seconds):
                items = _fetch_via_sdk(api_key)
            break
        except UnicodeEncodeError:
            try:
                if sys.stdout and hasattr(sys.stdout, "buffer"):
                    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
                if sys.stderr and hasattr(sys.stderr, "buffer"):
                    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
            except Exception:
                pass
            if attempts >= 2:
                normalized_log_event(
                    _logger,
                    "models.list.error",
                    LogContext(provider=PROVIDER, model="models"),
                    phase="start",
                    attempt=None,
                    error_code=None,
                    emitted=False,
                    provider=PROVIDER,
                    operation="fetch_models",
                    stage="start",
                    failure_class="UnicodeEncodeError",
                    fallback_used=True,
                )
                return None
            continue
        except Exception as e:  # noqa: BLE001
            normalized_log_event(
                _logger,
                "models.list.error",
                LogContext(provider=PROVIDER, model="models"),
                phase="start",
                attempt=None,
                error_code=None,
                emitted=False,
                provider=PROVIDER,
                operation="fetch_models",
                stage="start",
                failure_class=e.__class__.__name__,
                fallback_used=True,
            )
            return None

    if not items:
        return None

    cached = load_cached_models(PROVIDER)
    cached_caps: Dict[str, Dict[str, Any]] = {m.id: (m.capabilities or {}) for m in cached.models}

    client = OpenAI(api_key=api_key)
    enriched: List[ModelInfo] = []
    for it in items:
        mi = _enrich_item_to_modelinfo(it, client, cached_caps)
        if mi is not None:
            enriched.append(mi)

    save_provider_models(
        PROVIDER,
        enriched,
        fetched_via="api",
        metadata={
            "source": "openai_sdk_enriched",
            "capability_policy": "modalities+cached_merge",
        },
    )
    normalized_log_event(
        _logger,
        "models.list.ok",
        LogContext(provider=PROVIDER, model="models"),
        phase="finalize",
        attempt=None,
        error_code=None,
        emitted=True,
        provider=PROVIDER,
        operation="fetch_models",
        stage="finalize",
        count=len(enriched),
    )
    return [{"id": it.id, "name": it.name} for it in enriched]


def _enrich_item_to_modelinfo(
    it: Any, client: Any, cached_caps: Dict[str, Dict[str, Any]]
) -> Optional[ModelInfo]:
    mid = _first_attr(it, ("id", "model", "name"))
    if not mid:
        return None
    name = _first_attr(it, ("name", "id")) or str(mid)

    det = None
    with suppress(Exception):
        det = client.models.retrieve(str(mid))  # type: ignore[assignment]

    modalities = _first_attr(det, ("modalities",)) or _first_attr(it, ("modalities",))
    input_token_limit = (
        _first_attr(det, ("input_token_limit", "context_window"))
        or _first_attr(it, ("input_token_limit",))
    )
    created = _first_attr(det, ("created",)) or _first_attr(it, ("created",))
    context_length = (
        _first_attr(det, ("context_length",))
        or _first_attr(it, ("context_length", "max_context"))
    )

    if context_length is None and input_token_limit is not None:
        context_length = input_token_limit

    caps = normalize_modalities(modalities)
    prior = cached_caps.get(str(mid)) or {}
    caps = merge_capabilities(prior, caps)
    caps.setdefault("json_output", True)

    ctx_int: Optional[int] = None
    if context_length is not None:
        with suppress(Exception):
            ctx_int = int(context_length)

    mi = ModelInfo(
        id=str(mid),
        name=str(name),
        provider=PROVIDER,
        family=None,
        context_length=ctx_int,
        capabilities=caps,
        updated_at=None,
    )
    if isinstance(created, (int, float)):
        with suppress(Exception):
            mi.updated_at = None
    return mi


def _first_attr(obj: Any, names) -> Any:
    if obj is None:
        return None
    for n in names:
        try:
            val = getattr(obj, n, None)
        except Exception:
            val = None
        if val is not None:
            return val
        if isinstance(obj, dict) and n in obj:
            return obj.get(n)
    return None


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
    print(f"[openai] loaded {len(models)} models")
