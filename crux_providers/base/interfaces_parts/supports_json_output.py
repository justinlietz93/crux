"""SupportsJSONOutput Protocol (single-class module).

Capability marker for providers that can request JSON-native responses.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class SupportsJSONOutput(Protocol):
    """Capability for providers that support native JSON output."""

    def supports_json_output(self) -> bool:  # pragma: no cover - trivial
        """Return True if the provider supports native JSON output."""
        return True
