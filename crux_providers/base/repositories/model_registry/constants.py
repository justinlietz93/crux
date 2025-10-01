"""Deprecated constants for legacy JSON cache paths.

The model registry no longer uses JSON cache files. This module remains only to
avoid import errors in external code until migrations complete. Do not depend
on these symbols in new code.
"""

# deviation: retained for backward compatibility; unused in DB-first code path.
JSON_CACHE_FILENAME = "model-registry.json"

__all__ = ["JSON_CACHE_FILENAME"]
