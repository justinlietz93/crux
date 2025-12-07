"""Model registry repository implementation.

This module contains the ``ModelRegistryRepository`` class split from the
original multi-class file to comply with one-class-per-file governance. The
public API remains unchanged via re-exports in ``repository.py``.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ....models import ModelInfo, ModelRegistrySnapshot
from .. import db_store, parsing, refreshers
from ....capabilities import merge_capabilities, load_observed, apply_void_enrichment
from .model_registry_error import ModelRegistryError


class ModelRegistryRepository:
    """Manage model registry snapshots for providers.

    Reads from SQLite exclusively. Optional refresh uses provider-specific
    modules or the `ollama` CLI. Does not import cloud SDKs directly.
    """

    def __init__(self, providers_root: Optional[Path] = None) -> None:
        """Initialize the repository.

        Args:
            providers_root: Root directory for provider data. Defaults to the
                repository root's providers directory if not provided.
        """
        # This file lives under .../crux_providers/base/repositories/model_registry/repository_parts/
        # The providers root is one level above 'base', i.e., parents[4].
        self.providers_root = providers_root or Path(__file__).resolve().parents[4]

    # Public API
    def list_models(self, provider: str, refresh: bool = False) -> ModelRegistrySnapshot:
        """Return the snapshot of models for the given provider.

        Args:
            provider: Provider name.
            refresh: When True, attempt to refresh models before load.
        """
        provider = provider.lower().strip()
        if refresh:
            self._try_refresh(provider)
        db_snap = self._snapshot_from_db(provider)
        if db_snap is not None:
            self._apply_observed(provider, db_snap.models)
            self._apply_void_profile(provider, db_snap.models)
            return db_snap
        # DB-first policy: if no snapshot is found in SQLite, return an empty snapshot.
        # Callers that desire population should pass refresh=True.
        return ModelRegistrySnapshot(
            provider=provider,
            models=[],
            fetched_via=None,
            fetched_at=None,
            metadata={},
        )

    def list_providers(self) -> List[Dict[str, Any]]:
        """Return normalized provider descriptors from the registry.

        Each descriptor includes:

        - ``id``: Provider key.
        - ``display_name``: Human-friendly name (defaults to the provider id).
        - ``aliases``: List of alias strings.
        - ``model_count``: Number of models recorded for this provider.
        - ``enabled``: Optional enabled flag from metadata (defaults to True).
        - ``metadata``: Raw metadata mapping from the registry.
        """
        rows = db_store.list_providers_from_db() or []
        providers: List[Dict[str, Any]] = []
        for row in rows:
            provider = row.get("provider")
            if not provider:
                continue
            metadata = row.get("metadata") or {}
            if not isinstance(metadata, dict):
                metadata = {"raw": metadata}
            display_name = metadata.get("display_name") or provider
            aliases_raw = metadata.get("aliases")
            aliases = aliases_raw if isinstance(aliases_raw, list) else []
            try:
                model_count = int(row.get("model_count") or 0)
            except Exception:  # pragma: no cover - defensive
                model_count = 0
            enabled = bool(metadata.get("enabled", True))
            providers.append(
                {
                    "id": provider,
                    "display_name": display_name,
                    "aliases": aliases,
                    "model_count": model_count,
                    "enabled": enabled,
                    "metadata": metadata,
                }
            )
        return providers

    def _apply_observed(self, provider: str, models: List[ModelInfo]) -> None:
        """Merge observed capability flags into each model's capabilities."""
        observed = load_observed(provider, self.providers_root)
        if not observed:
            return
        for m in models or []:
            caps_old = getattr(m, "capabilities", {}) or {}
            if caps_obs := observed.get(m.id) or {}:
                m.capabilities = merge_capabilities(caps_old, caps_obs)

    def _apply_void_profile(self, provider: str, models: List[ModelInfo]) -> None:
        """Apply Void-oriented capability enrichment to model capabilities.

        This uses :func:`apply_void_enrichment` to fill in missing high-level
        fields such as ``tool_format`` and ``system_message`` in a
        non-destructive way (existing capability keys always win).
        """
        for m in models or []:
            caps_old = getattr(m, "capabilities", {}) or {}
            m.capabilities = apply_void_enrichment(provider, m.id, caps_old)

    def save_snapshot(self, snapshot: ModelRegistrySnapshot) -> None:
        """Persist the given snapshot to SQLite only (DB-first policy).

        Summary:
            Serializes the provided :class:`ModelRegistrySnapshot` and writes it
            to the authoritative SQLite store. JSON cache files are no longer
            produced to avoid dual sources of truth.

        Parameters:
            snapshot: The snapshot to persist.

        Returns:
            None. Callers should obtain snapshots via :meth:`list_models`.
        """
        payload: Dict[str, Any] = {
            "provider": snapshot.provider,
            "models": [m.to_dict() for m in snapshot.models],
            "fetched_at": snapshot.fetched_at or parsing.now_iso(),
            "fetched_via": snapshot.fetched_via or "local",
            "metadata": snapshot.metadata,
        }
        db_store.save_snapshot_to_db(
            snapshot.provider,
            payload["models"],
            fetched_at=payload["fetched_at"],
            fetched_via=payload["fetched_via"],
            metadata=payload["metadata"],
        )
        # DB-first: no JSON cache write; single source of truth is SQLite.

    # Refresh strategies
    def _refresh_provider_models(self, provider: str) -> None:
        """Try provider-specific refresh; supports ollama CLI fallback."""
        if provider == "ollama":
            if self._try_provider_refresh_module(provider):
                return
            try:
                self._refresh_via_ollama_cli()
                return
            except Exception as e:
                raise ModelRegistryError(f"Ollama refresh failed: {e}") from e
        ok = self._try_provider_refresh_module(provider)
        if not ok:
            raise ModelRegistryError(f"No refresh entry point found for provider '{provider}'")

    def _try_provider_refresh_module(self, provider: str) -> bool:
        """Import and invoke a provider-specific refresh function when available."""
        mod = refreshers.import_provider_module(provider)
        if mod is None:
            return False
        fn = refreshers.find_refresh_function(mod)
        if fn is not None:
            result = fn()
            self._persist_result_if_returned(provider, result)
            return True
        return False

    def _persist_result_if_returned(self, provider: str, result: Any) -> None:
        """Persist list/dict results returned from provider refresh helpers."""
        models, meta = parsing.normalize_result(provider, result)
        if models:
            snapshot = ModelRegistrySnapshot(
                provider=provider,
                models=models,
                fetched_via=meta.get("fetched_via"),
                fetched_at=meta.get("fetched_at"),
                metadata={},
            )
            self.save_snapshot(snapshot)

    def _refresh_via_ollama_cli(self) -> None:
        """Populate a minimal registry using `ollama list` when present."""
        try:
            models: List[ModelInfo] = refreshers.refresh_via_ollama_cli()
        except Exception as e:
            raise RuntimeError(f"ollama list failed: {e}") from e
        snapshot = ModelRegistrySnapshot(
            provider="ollama",
            models=models,
            fetched_via="ollama_list",
            fetched_at=parsing.now_iso(),
            metadata={"source": "ollama_cli"},
        )
        self.save_snapshot(snapshot)

    # Parsing helpers
    def _parse_models(self, provider: str, data: Dict[str, Any]) -> Tuple[List[ModelInfo], Dict[str, Any]]:
        """Parse provider model data from dict or list into typed models and metadata."""
        meta, raw = parsing.extract_meta_and_raw(data)
        models = [parsing.coerce_to_model(provider, it) for it in raw]
        return models, meta

    def _model_from_dict(self, provider: str, d: Dict[str, Any]) -> ModelInfo:
        """Normalize a model dictionary into a ``ModelInfo`` instance."""
        return parsing.model_from_dict(provider, d)

    # Internal helpers
    def _try_refresh(self, provider: str) -> None:
        """Attempt a refresh; log to stderr and continue on failure."""
        try:
            self._refresh_provider_models(provider)
        except Exception as e:
            print(
                f"[ModelRegistry] Refresh failed for {provider}: {e}. Falling back to cache.",
                file=sys.stderr,
            )

    def _snapshot_from_db(self, provider: str) -> Optional[ModelRegistrySnapshot]:
        """Load a snapshot from SQLite when available; return None on miss."""
        snap = db_store.load_snapshot_from_db(provider)
        if snap and isinstance(snap.get("models"), list):
            models = [self._model_from_dict(provider, m) for m in snap["models"]]
            return ModelRegistrySnapshot(
                provider=provider,
                models=models,
                fetched_via=snap.get("fetched_via"),
                fetched_at=snap.get("fetched_at"),
                metadata=snap.get("metadata") or {},
            )
        return None


__all__ = ["ModelRegistryRepository"]
