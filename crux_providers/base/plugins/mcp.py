"""Model Context Protocol (MCP) plugin support.

Provides MCP-compatible plugin interface for external context sources.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from .base import Plugin, PluginMetadata


class MCPPlugin:
    """Base implementation for MCP-compatible plugins.

    MCP plugins provide external context (memory, documents, APIs) to LLMs
    following the Model Context Protocol specification.

    Attributes:
        _metadata: Plugin metadata.
        _initialized: Initialization status.
        _config: Plugin configuration.
    """

    def __init__(
        self,
        name: str,
        version: str,
        capabilities: list[str] | None = None,
    ) -> None:
        """Initialize an MCP plugin.

        Args:
            name: Unique plugin identifier.
            version: Plugin version string.
            capabilities: List of MCP capabilities provided.
        """
        self._metadata = PluginMetadata(
            name=name,
            version=version,
            capabilities=capabilities or ["mcp"],
            author="",
            description=f"MCP plugin: {name}",
        )
        self._initialized = False
        self._config: Dict[str, Any] = {}

    @property
    def metadata(self) -> PluginMetadata:
        """Get plugin metadata."""
        return self._metadata

    def initialize(self, config: Optional[Dict[str, Any]] = None) -> None:
        """Initialize the MCP plugin.

        Args:
            config: Optional configuration dictionary.

        Raises:
            RuntimeError: If initialization fails.
        """
        self._config = config or {}
        self._initialized = True

    def shutdown(self) -> None:
        """Shutdown the plugin and release resources."""
        self._initialized = False
        self._config = {}

    def provides_capability(self, capability: str) -> bool:
        """Check if plugin provides a specific capability.

        Args:
            capability: Capability identifier to check.

        Returns:
            bool: True if plugin provides this capability.
        """
        return capability in self._metadata.capabilities

    def query_context(self, query: str) -> Dict[str, Any]:
        """Query the MCP plugin for context.

        Args:
            query: Context query string.

        Returns:
            Dict containing context data.

        Raises:
            NotImplementedError: Must be overridden by subclasses.
        """
        raise NotImplementedError("Subclasses must implement query_context")

    def update_context(self, data: Dict[str, Any]) -> bool:
        """Update the MCP plugin's context.

        Args:
            data: Context data to update.

        Returns:
            bool: True if update successful.

        Raises:
            NotImplementedError: Must be overridden by subclasses.
        """
        raise NotImplementedError("Subclasses must implement update_context")


__all__ = ["MCPPlugin"]
