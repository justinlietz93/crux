"""ModelListingProvider Protocol (single-class module).

Interface for providers that can materialize a model registry snapshot.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..models import ModelRegistrySnapshot


@runtime_checkable
class ModelListingProvider(Protocol):
    """Interface to obtain a snapshot of known models for a provider."""

    def list_models(self, refresh: bool = False) -> ModelRegistrySnapshot:
        """Return a snapshot of known models for this provider.

        When ``refresh=True``, implementations should re-fetch from source
        and persist the provider's registry; when ``False``, they may return a cached snapshot.
        """
        ...
