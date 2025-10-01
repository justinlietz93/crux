"""Errors parts package public surface.

Re-exports individual error taxonomy components for optional direct imports.
Prefer importing from `crux_providers.base.errors` for the stable surface.
"""

from .error_code import ErrorCode
from .provider_error import ProviderError
from .classification import classify_exception

__all__ = ["ErrorCode", "ProviderError", "classify_exception"]
