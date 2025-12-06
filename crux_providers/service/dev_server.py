from __future__ import annotations

import os
import uvicorn


def _parse_port(value: str | None, default: int) -> int:
    """Best-effort parse of a port from string, falling back to a sane default."""
    if not value:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def main() -> None:
    """Start the development server for the providers FastAPI app.

    When launched under the Void Genesis IDE, host/port and reload behavior are
    controlled via environment variables set by the Electron CruxSupervisor:

    - PROVIDER_SERVICE_HOST: interface to bind (default "127.0.0.1")
    - PROVIDER_SERVICE_PORT: port to bind (default 8091)
    - PROVIDER_SERVICE_RELOAD: "true"/"false" to toggle auto-reload
      (default True for direct CLI usage, False when set by the IDE).
    """
    host = os.getenv("PROVIDER_SERVICE_HOST", "127.0.0.1")
    port = _parse_port(os.getenv("PROVIDER_SERVICE_PORT"), 8091)

    reload_env = os.getenv("PROVIDER_SERVICE_RELOAD")
    if reload_env is None:
        # Default behavior for direct CLI usage: enable reload.
        reload_enabled = True
    else:
        # When launched from the IDE, CruxSupervisor sets PROVIDER_SERVICE_RELOAD
        # explicitly (typically "false" to avoid multi-process uvicorn).
        reload_enabled = reload_env.lower() == "true"

    uvicorn.run(
        "crux_providers.service.app:app",
        host=host,
        port=port,
        reload=reload_enabled,
    )


if __name__ == "__main__":
    main()
