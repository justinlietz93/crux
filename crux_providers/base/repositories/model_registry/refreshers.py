"""Refresh strategies for model registry.

This module discovers and invokes provider-specific model refreshers
and offers an Ollama CLI-based fallback.
"""

from __future__ import annotations

import json
import os
from importlib import import_module
from types import ModuleType
from typing import Any, Callable, Dict, List, Optional
from urllib import error as _urlerr
from urllib import request as _urlreq
from urllib.parse import urlparse

from ...models import ModelInfo
from ...timeouts import get_timeout_config
from ....config.defaults import OLLAMA_DEFAULT_HOST


def import_provider_module(provider: str) -> Optional[ModuleType]:
    """
    Locate a provider refresher module. Preference order:
    1) src.infrastructure.providers.<provider>.get_<provider>_models
    2) crux_providers.<provider>.get_<provider>_models
    3) package-relative to crux_providers (for embedded installs)
    """
    candidates = [
        f"src.infrastructure.providers.{provider}.get_{provider}_models",
        f"crux_providers.{provider}.get_{provider}_models",
    ]
    for module_name in candidates:
        try:
            return import_module(module_name)
        except Exception:
            continue
    # Final relative attempt for embedded package usage
    try:
        module_name_local = f".{provider}.get_{provider}_models"
        return import_module(module_name_local, package="crux_providers")
    except Exception:
        return None


def find_refresh_function(mod: ModuleType) -> Optional[Callable]:
    candidates = [
        "refresh_models",
        "update_models",
        "fetch_models",
        "get_models",
        "run",
        "main",
    ]
    for name in candidates:
        fn = getattr(mod, name, None)
        if callable(fn):
            return fn
    return None


def refresh_via_ollama_cli(timeout: int | None = None) -> List[ModelInfo]:
    """Return models listed by a local Ollama daemon via its HTTP API.

    Parameters
    ----------
    timeout: int | None
        Optional override in seconds; defaults to unified provider start timeout.
    """
    cfg = get_timeout_config()
    eff_timeout = timeout if timeout is not None else int(cfg.start_timeout_seconds)
    payload = _fetch_ollama_tags(timeout=eff_timeout)
    return _models_from_ollama_payload(payload)


def _ollama_base() -> str:
    """Return validated base URL for a local Ollama daemon.

    Only http/https schemes are permitted to avoid unsafe schemes (Bandit B310).
    If no scheme is provided, http:// is assumed. Raises RuntimeError on invalid scheme.
    """
    raw = (os.getenv("OLLAMA_HOST", OLLAMA_DEFAULT_HOST) or OLLAMA_DEFAULT_HOST).strip()
    parsed = urlparse(raw)
    # If user supplied host without scheme, assume http
    if not parsed.scheme:
        raw = f"http://{raw}"
        parsed = urlparse(raw)
    if parsed.scheme not in ("http", "https"):
        raise RuntimeError(
            f"Invalid OLLAMA_HOST scheme '{parsed.scheme}'. Only http/https allowed."
        )
    return raw.rstrip("/")


def _fetch_ollama_tags(timeout: int) -> Dict[str, Any]:
    """Fetch and decode the Ollama /api/tags JSON payload."""
    base = _ollama_base()  # validated (http/https only)
    url = f"{base}/api/tags"
    # Extra defensive check (Bandit B310) – base already validated but keep explicit guard
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise RuntimeError("Refusing to open non-http(s) URL for Ollama tags")
    req = _urlreq.Request(url, method="GET")
    try:
        # Safe: scheme explicitly limited to http/https above
        with _urlreq.urlopen(req, timeout=timeout) as resp:  # nosec B310
            if getattr(resp, "status", 200) != 200:
                raise RuntimeError(
                    f"ollama tags HTTP {getattr(resp, 'status', 'unknown')}"
                )
            raw = resp.read()
    except (
        _urlerr.URLError,
        _urlerr.HTTPError,
        TimeoutError,
    ) as e:  # pragma: no cover - environment specific
        raise RuntimeError(f"ollama tags request failed: {e}") from e

    try:
        payload = json.loads(raw.decode("utf-8"))
    except Exception as e:
        raise RuntimeError(f"ollama tags response parse error: {e}") from e
    return payload if isinstance(payload, dict) else {}


def _models_from_ollama_payload(payload: Dict[str, Any]) -> List[ModelInfo]:
    items = payload.get("models") if isinstance(payload, dict) else []
    models: List[ModelInfo] = []
    for it in items if isinstance(items, list) else []:
        name = it.get("name") if isinstance(it, dict) else (str(it) if it else None)
        if name:
            models.append(ModelInfo(id=name, name=name, provider="ollama"))
    return models


__all__ = ["import_provider_module", "find_refresh_function", "refresh_via_ollama_cli"]
