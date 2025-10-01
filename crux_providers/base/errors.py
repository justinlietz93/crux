"""Unified provider error taxonomy public surface.

This module re-exports the one-class-per-file implementations under
``crux_providers.base.errors_parts`` to maintain a stable import path while
enforcing the one-class-per-file governance rule.
"""

from .errors_parts.error_code import ErrorCode
from .errors_parts.provider_error import ProviderError
from .errors_parts.classification import classify_exception

__all__ = ["ErrorCode", "ProviderError", "classify_exception"]
