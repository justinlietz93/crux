"""Plugin registry for managing and discovering plugins.

Provides centralized plugin lifecycle management, dependency resolution,
and capability queries.
"""

from __future__ import annotations

from typing import Any, Dict, FrozenSet, List, Optional, Set

from .base import Plugin, PluginMetadata
from ..logging import get_logger


class PluginRegistry:
    """Central registry for managing plugins.

    This registry provides:
    - Plugin registration and discovery
    - Dependency resolution
    - Lifecycle management (initialize/shutdown)
    - Capability queries

    Attributes:
        plugins: Mapping of plugin name to plugin instance.
        logger: Structured logger instance.
    """

    def __init__(self) -> None:
        """Initialize an empty plugin registry."""
        self.plugins: Dict[str, Plugin] = {}
        self._initialized: Set[str] = set()
        self.logger = get_logger("plugin_registry")

    def register(
        self,
        plugin: Plugin,
        config: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Register and initialize a plugin.

        Args:
            plugin: Plugin instance to register.
            config: Optional plugin configuration.

        Raises:
            ValueError: If plugin name already registered.
            RuntimeError: If plugin initialization fails.
        """
        meta = plugin.metadata
        
        if meta.name in self.plugins:
            raise ValueError(f"Plugin '{meta.name}' already registered")

        # Check dependencies
        missing = self._check_dependencies(meta.dependencies)
        if missing:
            raise ValueError(
                f"Plugin '{meta.name}' missing dependencies: {missing}"
            )

        # Register plugin
        self.plugins[meta.name] = plugin
        
        # Initialize plugin
        try:
            plugin.initialize(config)
            self._initialized.add(meta.name)
            self.logger.info(
                "Plugin registered",
                extra={
                    "plugin": meta.name,
                    "version": meta.version,
                    "capabilities": meta.capabilities,
                },
            )
        except Exception as e:
            # Rollback registration on initialization failure
            del self.plugins[meta.name]
            self.logger.error(
                "Plugin initialization failed",
                extra={"plugin": meta.name, "error": str(e)},
            )
            raise RuntimeError(
                f"Failed to initialize plugin '{meta.name}': {e}"
            ) from e

    def unregister(self, name: str) -> None:
        """Unregister and shutdown a plugin.

        Args:
            name: Plugin name to unregister.

        Raises:
            KeyError: If plugin not found.
        """
        if name not in self.plugins:
            raise KeyError(f"Plugin '{name}' not found")

        plugin = self.plugins[name]
        
        # Shutdown plugin
        try:
            plugin.shutdown()
        except Exception as e:  # pragma: no cover
            self.logger.warning(
                "Plugin shutdown failed",
                extra={"plugin": name, "error": str(e)},
            )
        
        # Remove from registry
        del self.plugins[name]
        self._initialized.discard(name)
        
        self.logger.info("Plugin unregistered", extra={"plugin": name})

    def get(self, name: str) -> Optional[Plugin]:
        """Get a plugin by name.

        Args:
            name: Plugin name.

        Returns:
            Plugin instance or None if not found.
        """
        return self.plugins.get(name)

    def list_plugins(self) -> List[PluginMetadata]:
        """List all registered plugins.

        Returns:
            List of plugin metadata.
        """
        return [plugin.metadata for plugin in self.plugins.values()]

    def find_by_capability(self, capability: str) -> List[Plugin]:
        """Find all plugins providing a specific capability.

        Args:
            capability: Capability identifier.

        Returns:
            List of plugins providing the capability.
        """
        return [
            plugin
            for plugin in self.plugins.values()
            if plugin.provides_capability(capability)
        ]

    def get_capabilities(self) -> FrozenSet[str]:
        """Get all capabilities provided by registered plugins.

        Returns:
            Set of capability identifiers.
        """
        caps: Set[str] = set()
        for plugin in self.plugins.values():
            caps.update(plugin.metadata.capabilities)
        return frozenset(caps)

    def shutdown_all(self) -> None:
        """Shutdown all plugins and clear registry."""
        for name in list(self.plugins.keys()):
            try:
                self.unregister(name)
            except Exception as e:  # pragma: no cover
                self.logger.error(
                    "Failed to unregister plugin",
                    extra={"plugin": name, "error": str(e)},
                )

    def _check_dependencies(self, dependencies: List[str]) -> List[str]:
        """Check if dependencies are satisfied.

        Args:
            dependencies: List of required plugin names.

        Returns:
            List of missing dependencies.
        """
        return [dep for dep in dependencies if dep not in self.plugins]


__all__ = ["PluginRegistry"]
