"""Base plugin abstractions for the provider framework.

Defines the core plugin interface and metadata structure for extensibility.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable


@dataclass
class PluginMetadata:
    """Metadata describing a plugin.

    Attributes:
        name: Unique plugin identifier.
        version: Plugin version string.
        author: Plugin author/maintainer.
        description: Human-readable plugin description.
        capabilities: List of capability identifiers this plugin provides.
        dependencies: List of plugin names this plugin depends on.
        config: Plugin-specific configuration dictionary.
    """

    name: str
    version: str
    author: str = ""
    description: str = ""
    capabilities: List[str] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)
    config: Dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class Plugin(Protocol):
    """Base protocol for all plugins.

    Plugins extend provider capabilities by registering tools, interceptors,
    or other functionality. All plugins must provide metadata and lifecycle hooks.
    """

    @property
    def metadata(self) -> PluginMetadata:
        """Get plugin metadata.

        Returns:
            PluginMetadata: Plugin identification and configuration.
        """
        ...

    def initialize(self, config: Optional[Dict[str, Any]] = None) -> None:
        """Initialize the plugin with optional configuration.

        Called when the plugin is loaded by the registry.

        Args:
            config: Optional configuration dictionary.

        Raises:
            RuntimeError: If initialization fails.
        """
        ...

    def shutdown(self) -> None:
        """Shutdown the plugin and release resources.

        Called when the plugin is unloaded or system shuts down.
        """
        ...

    def provides_capability(self, capability: str) -> bool:
        """Check if plugin provides a specific capability.

        Args:
            capability: Capability identifier to check.

        Returns:
            bool: True if plugin provides this capability.
        """
        ...


__all__ = ["Plugin", "PluginMetadata"]
