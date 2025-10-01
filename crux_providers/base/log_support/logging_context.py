"""Structured logging context object for providers.

This module defines :class:`LogContext`, a dataclass used to carry common
fields for provider logging events (provider name, model, request/response
IDs, and extra metadata). It offers a ``to_dict`` helper that merges the
``extra`` mapping and prunes ``None`` values for clean structured output.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict, field
from typing import Any, Dict, Optional


@dataclass
class LogContext:
    """Structured context for provider logging events."""

    provider: Optional[str] = None
    model: Optional[str] = None
    request_id: Optional[str] = None
    response_id: Optional[str] = None
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        extra = data.pop("extra", {}) or {}
        data.update({k: v for k, v in extra.items() if v is not None})
        return {k: v for k, v in data.items() if v is not None}


__all__ = ["LogContext"]
