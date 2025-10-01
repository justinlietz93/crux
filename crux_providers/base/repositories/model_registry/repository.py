"""
Model Registry Repository

This shim module re-exports the public classes from the one-class-per-file
implementation under ``repository_parts`` to comply with governance rules
without breaking existing import paths.
"""

from .repository_parts.model_registry_error import ModelRegistryError
from .repository_parts.model_registry_repository import ModelRegistryRepository

__all__ = ["ModelRegistryRepository", "ModelRegistryError"]
