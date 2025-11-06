"""IPluginRegistry Protocol (single-class module).

Interface for plugin management and extensibility.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Protocol, runtime_checkable


@runtime_checkable
class IPluginRegistry(Protocol):
    """Interface for plugin registry and lifecycle management.

    Implementations handle:
    - Plugin discovery and loading
    - Lifecycle management (init, enable, disable)
    - Dependency resolution
    - Hook registration and execution
    """

    def register_plugin(
        self,
        plugin_id: str,
        plugin_class: type,
        config: Optional[Dict[str, Any]] = None,
    ) -> None:  # pragma: no cover - interface
        """Register a plugin with the system.
        
        Parameters
        ----------
        plugin_id:
            Unique plugin identifier.
        plugin_class:
            Plugin class to instantiate.
        config:
            Optional configuration for the plugin.
        """
        ...

    def enable_plugin(self, plugin_id: str) -> None:  # pragma: no cover - interface
        """Enable a registered plugin.
        
        Parameters
        ----------
        plugin_id:
            Plugin to enable.
            
        Raises
        ------
        PluginNotFoundError:
            When plugin is not registered.
        """
        ...

    def disable_plugin(self, plugin_id: str) -> None:  # pragma: no cover - interface
        """Disable an active plugin.
        
        Parameters
        ----------
        plugin_id:
            Plugin to disable.
        """
        ...

    def list_plugins(
        self,
        enabled_only: bool = False,
    ) -> List[Dict[str, Any]]:  # pragma: no cover - interface
        """List all registered plugins.
        
        Parameters
        ----------
        enabled_only:
            If True, only return enabled plugins.
            
        Returns
        -------
        List[Dict[str, Any]]
            Plugin metadata (id, name, version, status, etc.).
        """
        ...

    def register_hook(
        self,
        hook_name: str,
        callback: Callable[..., Any],
        priority: int = 0,
    ) -> None:  # pragma: no cover - interface
        """Register a hook callback.
        
        Parameters
        ----------
        hook_name:
            Hook point identifier (e.g., 'before_chat', 'after_stream').
        callback:
            Function to call at hook point.
        priority:
            Execution priority (higher executes first).
        """
        ...

    def execute_hook(
        self,
        hook_name: str,
        *args: Any,
        **kwargs: Any,
    ) -> List[Any]:  # pragma: no cover - interface
        """Execute all callbacks registered for a hook.
        
        Parameters
        ----------
        hook_name:
            Hook to execute.
        *args, **kwargs:
            Arguments passed to callbacks.
            
        Returns
        -------
        List[Any]
            Results from all callbacks.
        """
        ...

    def get_plugin(self, plugin_id: str) -> Optional[Any]:  # pragma: no cover - interface
        """Get a plugin instance by ID.
        
        Parameters
        ----------
        plugin_id:
            Plugin identifier.
            
        Returns
        -------
        Optional[Any]
            Plugin instance if registered and enabled, None otherwise.
        """
        ...
