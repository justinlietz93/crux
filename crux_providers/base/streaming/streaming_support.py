"""Unified helper for determining streaming capability.

Relocated into the streaming package for cohesion.
"""
from __future__ import annotations

from typing import Any, Callable, Optional

__all__ = ["streaming_supported"]


def streaming_supported(
    sdk_obj: Any,
    *,
    require_api_key: bool,
    api_key_getter: Callable[[], Optional[str]],
    allow_sdk_absent_if_no_key_required: bool = True,
) -> bool:
    """Determine whether streaming is supported under current runtime conditions."""
    if (
        sdk_obj is None
        and not (
            (not require_api_key and allow_sdk_absent_if_no_key_required)
        )
    ):
        return False
    if require_api_key:
        key = api_key_getter() or ""
        if not key.strip():
            return False
    return True
