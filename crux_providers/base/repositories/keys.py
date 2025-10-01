"""
Keys Repository

Purpose
- Centralize API key and related credential resolution for providers.
- Prefer environment variables; optionally read from unified config when available.
- Keep logic contained in providers layer (no external writes).

Design
- Non-throwing accessors that return None if a key is not resolved.
- Simple, explicit env var map per provider.
- Optional config fallbacks via src.config_loader if present.

Usage
- repo = KeysRepository()
- key = repo.get_api_key("openai")
"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

# Optional unified config loader (do not fail if absent)
try:
    from src.config_loader import config_loader  # type: ignore
except Exception:
    config_loader = None  # type: ignore


@dataclass
class KeyResolution:
    provider: str
    api_key: Optional[str]
    source: str  # "env", "config", "none"
    extra: Dict[str, Any]


class KeysRepository:
    """
    Resolve provider credentials with a strict priority order:

    1) Environment variables (authoritative)
    2) Unified config.yaml (when available)
    3) None

    This repository only reads values; it does not mutate any external state.
    """

    # Centralized mapping is defined in crux_providers.config.env; keep a narrow
    # reference here to avoid duplication and drift.
    from crux_providers.config.env import (  # type: ignore
        ENV_MAP as ENV_MAP,  # re-export for legacy access patterns
        resolve_provider_key,
    )
    # Prevent method binding; use as a static utility function to avoid adding 'self'.
    resolve_provider_key = staticmethod(resolve_provider_key)  # type: ignore[assignment]

    def get_api_key(self, provider: str) -> Optional[str]:
        return self.get_resolution(provider).api_key

    def get_resolution(self, provider: str) -> KeyResolution:
        p = (provider or "").lower().strip()
        # Prefer environment variables (alias-aware via resolver)
        val, used = self.resolve_provider_key(p)
        if val:
            return KeyResolution(
                provider=p, api_key=val, source="env", extra={"env_var": used}
            )

        # 2) Unified config (best-effort)
        cfg_key, extra = self._from_config(p)

        if cfg_key:
            return KeyResolution(
                provider=p, api_key=cfg_key, source="config", extra=extra
            )

        # 3) Settings repository (SQLite) fallback
        # Only suppress import/runtime issues expected when optional settings module absent.
        with contextlib.suppress(ImportError, AttributeError, RuntimeError):
            from src.settings import get_settings_repo  # type: ignore
            repo = get_settings_repo()  # may raise if settings subsystem uninitialized
            if db_key := repo.get_api_key(p):  # type: ignore[attr-defined]
                return KeyResolution(
                    provider=p,
                    api_key=db_key,
                    source="settings_db",
                    extra={"repo": "sqlite"},
                )
        # 4) None
        return KeyResolution(provider=p, api_key=None, source="none", extra=extra)

    # -------------------- internal helpers --------------------

    def _from_config(self, provider: str) -> Tuple[Optional[str], Dict[str, Any]]:
        """
        Attempt to read API key equivalents from config.yaml via config_loader.
        Returns (key_or_none, meta).
        """
        meta: Dict[str, Any] = {}
        if not config_loader:
            meta["config_loader"] = "absent"
            return None, meta
        try:
            return self._read_config_key(provider, meta)
        except Exception as e:  # pragma: no cover - defensive
            meta["error"] = str(e)
            return None, meta

    def _read_config_key(
        self, provider: str, meta: Dict[str, Any]
    ) -> Tuple[Optional[str], Dict[str, Any]]:
        """Internal helper to locate a provider key in unified config.

        Checks standard field names first, then a fallback 'token'.
        Returns (key_or_none, meta).
        """
        api_cfg = config_loader.get_section("api") or {}
        prov_cfg = api_cfg.get(provider) or {}
        meta["has_api_section"] = bool(api_cfg)
        meta["has_provider_section"] = bool(prov_cfg)
        key = self._extract_field_from_provider_cfg(prov_cfg, meta)
        return key, meta

    @staticmethod
    def _extract_field_from_provider_cfg(
        prov_cfg: Dict[str, Any], meta: Dict[str, Any]
    ) -> Optional[str]:
        """Extract a plausible API key field from a provider config section.

        This helper inspects the given provider configuration mapping for
        conventional key fields in priority order and records which field
        matched in the ``meta`` dictionary for observability.

        Parameters
        - prov_cfg: Mapping of configuration values for a specific provider
            under the global ``api`` section (e.g., from ``config.yaml``).
        - meta: Mutable metadata dictionary to enrich with a ``field`` entry
            when a value is successfully extracted.

        Returns
        - The first non-empty string value found among the candidate fields,
            or ``None`` if none are present.

        Notes
        - Field candidates are checked in the following order: ``api_key``,
            ``resolved_key``, ``key``, ``token``.
        """
        for field in ("api_key", "resolved_key", "key", "token"):
            val = prov_cfg.get(field)
            if isinstance(val, str) and val:
                meta["field"] = field
                return val
        return None
