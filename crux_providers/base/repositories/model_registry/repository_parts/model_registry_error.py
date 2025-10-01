"""Model registry domain errors.

Defines the exception type used by the model registry repository. Kept in a
dedicated module to satisfy one-class-per-file governance while retaining a
stable import surface via re-exports in ``repository.py``.
"""

from __future__ import annotations


class ModelRegistryError(Exception):
    """Raised when a provider model registry refresh or access fails.

    Failure modes include missing provider-specific refresh entry points, CLI
    failures (e.g., ollama), or unexpected parsing errors. Callers typically
    catch this and fall back to cached snapshots.
    """

__all__ = ["ModelRegistryError"]
