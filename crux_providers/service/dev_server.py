from __future__ import annotations

import uvicorn


def main() -> None:
    """Start the development server for the providers FastAPI app.

    Runs the app with Uvicorn on localhost:8091 with auto-reload enabled.
    """
    uvicorn.run(
    "crux_providers.service.app:app",
        host="127.0.0.1",
        port=8091,
        reload=True,
    )


if __name__ == "__main__":
    main()
