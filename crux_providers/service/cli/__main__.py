"""CLI package executable module.

Allows running the CLI via:

    python -m crux_providers.service.cli [args]

This module simply forwards to ``main`` defined in the package.
"""

from __future__ import annotations

from . import main


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
