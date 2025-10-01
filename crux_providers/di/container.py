"""Minimal dependency injection container for providers.

Goals:
- Centralize construction of shared repositories/services.
- Decouple upstream code from direct factory calls (optionally remove ProviderFactory later).
- Keep zero external dependencies per architecture rules.

This can evolve to include caching, tracing, metrics, etc., without touching
adapter call sites.
"""

from __future__ import annotations

from typing import Any, Dict

from ..base.factory import ProviderFactory
from ..base.repositories.model_registry.repository import ModelRegistryRepository


class ProvidersContainer:
    """Dependency injection container for provider-related services and singletons.

    This class centralizes the construction and caching of shared repositories and provider instances, decoupling upstream code from direct factory calls.
    """

    def __init__(self, config: Dict[str, Any] | None = None) -> None:
        """Initialize the ProvidersContainer with optional configuration.

        Args:
            config: Optional dictionary of configuration values for providers and services.
        """
        self._config = config or {}
        self._singletons: Dict[str, Any] = {}
        self._providers: Dict[str, Any] = {}

    # ---- Shared singletons ----
    def model_registry(self) -> ModelRegistryRepository:
        """Return a shared instance of the ModelRegistryRepository.

        This method ensures a singleton instance of the model registry is reused across the container.

        Returns:
            ModelRegistryRepository: The shared model registry repository instance.
        """
        if "model_registry" not in self._singletons:
            self._singletons["model_registry"] = ModelRegistryRepository()
        return self._singletons["model_registry"]

    # ---- Providers ----
    def provider(self, name: str):  # returns LLMProvider (duck-typed)
        """Return a provider instance by name, creating and caching it if necessary.

        This method ensures that each provider is instantiated only once and reused for subsequent requests.

        Args:
            name: The name of the provider to retrieve.

        Returns:
            The provider instance corresponding to the given name.
        """
        key = name.lower()
        if key not in self._providers:
            self._providers[key] = ProviderFactory.create(
                key, registry=self.model_registry()
            )
        return self._providers[key]

    def clear(self):  # testing convenience
        """Clear all cached providers and singletons from the container.

        This method is primarily intended for testing and resets the container's internal state.
        """
        self._providers.clear()
        self._singletons.clear()


def build_container(config: Dict[str, Any] | None = None) -> ProvidersContainer:
    """Construct and return a new ProvidersContainer instance.

    This function creates a ProvidersContainer with the given configuration.

    Args:
        config: Optional dictionary of configuration values for providers and services.

    Returns:
        ProvidersContainer: The initialized providers container.
    """
    return ProvidersContainer(config=config)


__all__ = ["ProvidersContainer", "build_container"]
