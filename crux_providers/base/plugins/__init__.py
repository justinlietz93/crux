"""Plugin system for extensible provider capabilities.

Provides plugin registry, MCP support, and dynamic capability loading.
"""

from .registry import PluginRegistry
from .base import Plugin, PluginMetadata
from .mcp import MCPPlugin

__all__ = ["PluginRegistry", "Plugin", "PluginMetadata", "MCPPlugin"]
